"""공통 픽스처: 임시 DB/업로드 폴더 + 고정 테스트 시계 + DEMO 시드 + 가짜 Gemini."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

import httpx
import pytest
from fastapi.testclient import TestClient

# 고정 시계: 2026-11-06 12:00 KST (= 03:00Z). 시드 기준일도 같은 날.
FIXED_NOW = "2026-11-06T03:00:00Z"
BASE_DATE = date(2026, 11, 6)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'amp.db').as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ASSETS_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("FIXED_NOW_UTC", FIXED_NOW)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    # 실제 .env 의 키로 외부 AI 를 부르지 않는다 (AI 는 gemini 픽스처로만 켠다)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    return tmp_path


@pytest.fixture()
def db(env):
    from database import connect, init_db
    from seed import seed

    init_db()
    conn = connect()
    seed(conn, base_date=BASE_DATE)
    yield conn
    conn.close()


@pytest.fixture()
def client(db):
    from main import create_app

    # 관리자 API 는 loopback 에서만 허용되므로 클라이언트 주소를 127.0.0.1 로 둔다.
    with TestClient(create_app(), client=("127.0.0.1", 50000)) as c:
        yield c


@pytest.fixture()
def remote_client(db):
    from main import create_app

    with TestClient(create_app(), client=("203.0.113.10", 50000)) as c:
        yield c


# ---------------------------------------------------------------------------
# 가짜 Gemini: 실제 gemini_generate(HTTP 본문·헤더 구성)를 그대로 거치고, 응답만 스크립트로 준다.
# ---------------------------------------------------------------------------
class FakeGemini:
    def __init__(self) -> None:
        self.script: list[Any] = []
        self.requests: list[dict[str, Any]] = []
        self.headers: list[httpx.Headers] = []
        self.urls: list[str] = []

    def add(self, *steps: Any) -> "FakeGemini":
        self.script.extend(steps)
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(request.headers)
        self.urls.append(str(request.url))
        if not self.script:
            raise AssertionError("FakeGemini: no scripted response left")
        step = self.script.pop(0)
        if callable(step):
            step = step(body)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, int):  # HTTP 오류 상태
            return httpx.Response(step, json={"error": {"code": step, "message": "fake", "status": "UNAVAILABLE"}})
        return httpx.Response(200, json={"candidates": [{"content": step}]})


def fc(name: str, args: dict[str, Any] | None = None, *more: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    """모델 함수 호출 턴 (여러 개면 병렬 호출)."""
    parts = [{"functionCall": {"name": name, "args": args or {}}, "thoughtSignature": "sig"}]
    parts += [{"functionCall": {"name": n, "args": a}} for n, a in more]
    return {"role": "model", "parts": parts}


def text(value: Any) -> dict[str, Any]:
    """모델 텍스트(JSON) 턴."""
    return {"role": "model", "parts": [{"text": value if isinstance(value, str) else json.dumps(value,
                                                                                                ensure_ascii=False)}]}


@pytest.fixture()
def gemini(env, monkeypatch) -> FakeGemini:
    from services import reason

    fake = FakeGemini()
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(reason, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(reason, "TRANSIENT_BACKOFF_S", 0.0)  # 일시 장애 재시도 대기 없이
    return fake


def function_responses(body: dict[str, Any]) -> list[dict[str, Any]]:
    """요청 본문 마지막 user 턴의 functionResponse 들."""
    return [p["functionResponse"] for p in body["contents"][-1]["parts"] if "functionResponse" in p]


Step = Callable[[dict[str, Any]], Any]
