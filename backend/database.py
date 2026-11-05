"""설정(환경 변수) · SQLite 연결/스키마 · 요청 의존성(get_db, require_admin).

- 설정은 테스트에서 환경 변수를 바꿔 끼울 수 있도록 호출 시점마다 읽는다.
- 스키마는 DATABASE.md §6 DDL 그대로. 연결마다 `PRAGMA foreign_keys=ON`.
- 관리자 API 보호 (API.md §0: posters/parse, translate, POST /api/events):
  * `ADMIN_API_KEY` 가 설정되면 `X-Admin-Key` 헤더가 일치해야 한다 (불일치 401).
  * 키가 없으면 `DEMO_MODE=true` 일 때 **loopback(127.0.0.1/::1) 요청만** 허용한다 (그 외 403).
  * 키도 없고 DEMO_MODE=false 이면 관리자 API 를 비활성화한다 (403).
  공개 배포(리버스 프록시 뒤 등)에서는 반드시 ADMIN_API_KEY 또는 별도 인증을 적용한다.
"""
from __future__ import annotations

import hmac
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from schemas import ApiError

try:  # .env 는 선택 사항 (없어도 동작)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

APP_NAME = "amp-api"
APP_VERSION = "1.1.0"
# 프런트 개발 서버(`npm run dev` = vite --host 127.0.0.1)와 문서 예시(localhost) 둘 다 허용
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@dataclass(frozen=True)
class Settings:
    database_path: Path
    upload_dir: Path
    assets_dir: Path
    cors_origins: list[str]
    max_poster_bytes: int
    demo_mode: bool
    admin_api_key: str | None
    llm_provider: str
    llm_model: str
    llm_api_key: str
    fixed_now_utc: str | None


def get_settings() -> Settings:
    db_url = os.getenv("DATABASE_URL", "sqlite:///./data/amp.db")
    db_path_str = db_url.removeprefix("sqlite:///") if db_url.startswith("sqlite:///") else db_url
    max_mb = float(os.getenv("MAX_POSTER_MB", "5") or 5)
    return Settings(
        database_path=_resolve(db_path_str),
        upload_dir=_resolve(os.getenv("UPLOAD_DIR", "./uploads")),
        assets_dir=_resolve(os.getenv("ASSETS_DIR", str(PROJECT_DIR / "assets"))),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",") if o.strip()],
        max_poster_bytes=int(max_mb * 1024 * 1024),
        demo_mode=_bool(os.getenv("DEMO_MODE"), True),
        admin_api_key=os.getenv("ADMIN_API_KEY") or None,
        llm_provider=os.getenv("LLM_PROVIDER", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        fixed_now_utc=os.getenv("FIXED_NOW_UTC") or None,
    )


# ---------------------------------------------------------------------------
# 스키마 / 연결
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    area TEXT NOT NULL CHECK (area IN ('sinchon','hongdae')),
    address TEXT,
    floor TEXT,
    entrance_image_path TEXT,
    entrance_hint_ko TEXT,
    entrance_hint_en TEXT,
    description_ko TEXT,
    description_en TEXT,
    default_seating_type TEXT CHECK (default_seating_type IS NULL OR default_seating_type IN ('standing','seated','mixed')),
    default_drink_policy TEXT,
    source_url TEXT,
    verified_at_utc TEXT,
    data_origin TEXT NOT NULL CHECK (data_origin IN ('verified','demo'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    title TEXT NOT NULL,
    starts_at_utc TEXT NOT NULL,
    ends_at_utc TEXT,
    doors_open_at_utc TEXT,
    price_krw INTEGER CHECK (price_krw IS NULL OR price_krw >= 0),
    price_basis TEXT CHECK (price_basis IS NULL OR price_basis IN ('advance','door','general')),
    advance_price_krw INTEGER CHECK (advance_price_krw IS NULL OR advance_price_krw >= 0),
    door_price_krw INTEGER CHECK (door_price_krw IS NULL OR door_price_krw >= 0),
    booking_url TEXT,
    lineup_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(lineup_json)),
    genre TEXT,
    mood_tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(mood_tags_json)),
    solo_friendly INTEGER CHECK (solo_friendly IS NULL OR solo_friendly IN (0,1)),
    seating_type TEXT CHECK (seating_type IS NULL OR seating_type IN ('standing','seated','mixed')),
    seat_assignment TEXT CHECK (seat_assignment IS NULL OR seat_assignment IN ('assigned','unassigned')),
    drink_policy TEXT,
    description_ko TEXT,
    description_en TEXT,
    admission_notes_ko TEXT,
    admission_notes_en TEXT,
    poster_image_path TEXT,
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft','published','cancelled')),
    data_origin TEXT NOT NULL CHECK (data_origin IN ('verified','demo')),
    source_url TEXT,
    verified_at_utc TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    CHECK ((price_krw IS NULL AND price_basis IS NULL) OR (price_krw IS NOT NULL AND price_basis IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_events_status_start ON events(status, starts_at_utc);
CREATE INDEX IF NOT EXISTS idx_events_venue ON events(venue_id);
CREATE INDEX IF NOT EXISTS idx_events_price ON events(price_krw);
CREATE INDEX IF NOT EXISTS idx_events_seating ON events(seating_type);
CREATE INDEX IF NOT EXISTS idx_venues_area ON venues(area);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """연결마다 `PRAGMA foreign_keys=ON` 적용."""
    path = db_path or get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# FastAPI 요청 의존성
# ---------------------------------------------------------------------------
def get_db() -> Iterator[sqlite3.Connection]:
    """요청마다 새 연결."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def require_admin(request: Request) -> None:
    settings = get_settings()
    if settings.admin_api_key:
        given = request.headers.get("X-Admin-Key", "")
        if not hmac.compare_digest(given.encode(), settings.admin_api_key.encode()):
            raise ApiError(401, "UNAUTHORIZED", "관리자 인증이 필요합니다.")
        return
    host = request.client.host if request.client else ""
    if not settings.demo_mode or host not in _LOOPBACK:
        raise ApiError(403, "FORBIDDEN", "관리자 기능은 로컬 데모 환경에서만 사용할 수 있습니다.")
