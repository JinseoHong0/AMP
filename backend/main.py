"""AMP FastAPI 앱 진입점.

실행 (backend/ 에서):
    python -m venv .venv && .venv\\Scripts\\activate      # macOS·Linux: source .venv/bin/activate
    pip install -r requirements.txt
    python seed.py                     # 엑셀 데이터셋 적재 (--demo: 가상 DEMO 시드, --reset 재생성)
    uvicorn main:app --reload --host 127.0.0.1 --port 8000
    python -m pytest                   # 테스트 (가짜 Gemini 사용, 실제 키로 외부 호출하지 않음)

모듈 구성 (docs/DEVELOPMENT.md §3):
    main.py      앱 생성, CORS, 공통 오류 핸들러, /api/health, /media
    database.py  설정(.env), SQLite 연결/스키마·마이그레이션, 요청 의존성(get_db, require_admin)
    models.py    도메인 상수·오류, KST↔UTC, 가격 산출, row→JSON, 번역 지문, 하드 필터 쿼리
    schemas.py   Pydantic 요청/응답, ApiError
    seed.py      데이터 적재 (엑셀 / DEMO)
    routers/     events(+등록·번역 재시도) · venues · recommend · posters(포스터 분석)
    services/    intent(AI 도구 호출 검색·추천) · ranker · reason(Gemini 호출·이유·등록 번역)
                 · poster_parser(Vision 추출+업로드) · venue_matcher

AI (Google Gemini, `.env` 의 LLM_PROVIDER=gemini · LLM_MODEL · LLM_API_KEY, docs/AI.md):
    - 추천: 자연어 query → AI 가 search_events/get_event_details 도구로 조회·재조회 후 최대 3개 제출,
      서버가 ID·필수 조건·근거를 검증. AI 실패 시 503 AI_UNAVAILABLE (필터 결과로 대체하지 않음).
      query 없이 필터만 → AI 없이 시간순 + used_fallback=true
    - 등록 번역: POST /api/events 저장 전 원문 4필드 → 영문 자동 생성(15초·재시도 1회). 실패해도 201 + failed,
      POST /api/events/{id}/translate 로 재시도
    - 포스터: POST /api/posters/parse → Vision 추출, 공연장은 서버가 이름 정규화로 매칭. 실패 시 503 → 수동 등록
    - 공급자 일시 장애(429·500·503)는 추천·포스터에서 각 시간 한도 안에서만 짧게 재시도한다.
"""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from database import APP_NAME, APP_VERSION, get_settings, init_db
from routers import events, posters, recommend, venues
from schemas import ApiError, error_body

logger = logging.getLogger("amp")

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_HTTP_CODES = {
    400: ("INVALID_QUERY", "요청을 확인해 주세요."),
    401: ("UNAUTHORIZED", "관리자 인증이 필요합니다."),
    403: ("FORBIDDEN", "접근 권한이 없습니다."),
    404: ("NOT_FOUND", "요청한 리소스를 찾을 수 없습니다."),
    405: ("METHOD_NOT_ALLOWED", "허용되지 않은 메서드입니다."),
    413: ("FILE_TOO_LARGE", "파일이 너무 큽니다."),
    415: ("UNSUPPORTED_FILE_TYPE", "지원하지 않는 파일 형식입니다."),
}


def _field_of(err: dict[str, Any]) -> str:
    loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header", "form")]
    return ".".join(loc)


def register_error_handlers(app: FastAPI) -> None:
    """모든 오류를 `{"error": {...}}` 형식으로. FastAPI 기본 422 도 변환한다."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        details: dict[str, Any] = {"field": _field_of(first)} if first else {}
        if len(errors) > 1:
            details["fields"] = sorted({_field_of(e) for e in errors})
        return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", "요청 값을 확인해 주세요.", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_CODES.get(exc.status_code, ("HTTP_ERROR", "요청을 처리할 수 없습니다."))
        return JSONResponse(status_code=exc.status_code, content=error_body(code, message))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # 키/비밀 데이터가 노출되지 않도록 상세 내용은 서버 로그에만 남긴다.
        logger.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", "서버 오류가 발생했습니다."))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AMP API", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(events.router)
    app.include_router(venues.router)
    app.include_router(recommend.router)
    app.include_router(posters.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        # 서버 상태만 표시한다. AI 공급자 연결 상태를 보장하지 않는다.
        return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}

    @app.get("/media/{kind}/{filename}", tags=["media"], include_in_schema=False)
    def media(kind: str, filename: str) -> FileResponse:
        """로컬 정적 미디어. 업로드 폴더 → 저장소 assets 폴더 순서로 찾는다."""
        if kind not in ("posters", "entrances") or not _SAFE_FILENAME.fullmatch(filename) or ".." in filename:
            raise ApiError(404, "NOT_FOUND", "파일을 찾을 수 없습니다.")
        s = get_settings()
        for base in (s.upload_dir / kind, s.assets_dir / kind):
            path = (base / filename).resolve()
            if path.is_file() and path.parent == base.resolve():
                return FileResponse(path)
        raise ApiError(404, "NOT_FOUND", "파일을 찾을 수 없습니다.")

    return app


app = create_app()
