"""공통 픽스처: 임시 DB/업로드 폴더 + 고정 테스트 시계 + DEMO 시드."""
from __future__ import annotations

from datetime import date

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
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
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
