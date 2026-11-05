"""1단계: 스키마·가격 산출·시간 변환·시드·health·오류 형식."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from conftest import BASE_DATE


# ---------- 가격 산출 (DATABASE.md §5) ----------
@pytest.mark.parametrize(
    "price, adv, door, expected",
    [
        (None, 20000, 25000, (20000, "advance")),
        (None, None, 25000, (25000, "door")),
        (15000, None, None, (15000, "general")),
        (0, None, None, (0, "general")),
        (None, None, None, (None, None)),
        (None, 20000, 20000, (20000, "advance")),  # 동가 → advance 우선
        (None, 25000, 20000, (20000, "door")),
        (18000, 18000, 22000, (18000, "advance")),  # 대표가 = 최저 → OK
    ],
)
def test_compute_price(price, adv, door, expected):
    from models import compute_price

    assert compute_price(price, adv, door) == expected


def test_compute_price_mismatch_and_negative():
    from models import PriceMismatchError, compute_price

    with pytest.raises(PriceMismatchError):
        compute_price(25000, 20000, 25000)
    with pytest.raises(ValueError):
        compute_price(-1, None, None)


# ---------- 시간 ----------
def test_time_conversion(env):
    from models import kst_day_range_utc, local_to_utc_str, now_utc, resolve_date_expression, today_kst

    assert local_to_utc_str(datetime(2026, 11, 7, 19, 0)) == "2026-11-07T10:00:00Z"
    assert kst_day_range_utc(date(2026, 11, 7)) == ("2026-11-06T15:00:00Z", "2026-11-07T15:00:00Z")
    assert now_utc().isoformat() == "2026-11-06T03:00:00+00:00"  # 고정 시계
    assert today_kst() == date(2026, 11, 6)
    assert resolve_date_expression("today") == date(2026, 11, 6)
    assert resolve_date_expression("tomorrow") == date(2026, 11, 7)
    assert resolve_date_expression("2026-11-09") == date(2026, 11, 9)
    assert resolve_date_expression(None) is None
    with pytest.raises(ValueError):
        resolve_date_expression("이번 주")
    with pytest.raises(ValueError):
        resolve_date_expression("20261107")


# ---------- 스키마 제약 ----------
def test_schema_constraints(db):
    db.execute("PRAGMA foreign_keys")  # 연결마다 ON
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    base = ("INSERT INTO events (venue_id, title, starts_at_utc, price_krw, price_basis, data_origin,"
            " created_at_utc, updated_at_utc) VALUES (?, 't', '2026-11-07T10:00:00Z', ?, ?, 'demo', 'x', 'x')")
    with pytest.raises(sqlite3.IntegrityError):  # 없는 venue FK
        db.execute(base, (9999, None, None))
    with pytest.raises(sqlite3.IntegrityError):  # price 있는데 basis 없음
        db.execute(base, (1, 1000, None))
    with pytest.raises(sqlite3.IntegrityError):  # 음수 가격
        db.execute(base, (1, -1, "general"))
    with pytest.raises(sqlite3.IntegrityError):  # 잘못된 area
        db.execute("INSERT INTO venues (name, area, data_origin) VALUES ('x', 'gangnam', 'demo')")
    db.rollback()


# ---------- 시드 ----------
def test_seed_minimums_and_demo_label(db):
    venues = db.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
    events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert venues >= 4 and events >= 20
    assert db.execute("SELECT COUNT(*) FROM events WHERE data_origin <> 'demo'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM venues WHERE data_origin <> 'demo'").fetchone()[0] == 0
    # 시연용 미래 공개 공연이 3개 이상
    future = db.execute(
        "SELECT COUNT(*) FROM events WHERE status='published' AND starts_at_utc >= '2026-11-06T03:00:00Z'"
    ).fetchone()[0]
    assert future >= 20
    # 예시 공연: KST 11/7 19:00 → UTC 10:00, 입장 18:30 KST
    row = db.execute("SELECT * FROM events WHERE title='밤의 산책'").fetchone()
    assert row["starts_at_utc"] == "2026-11-07T10:00:00Z"
    assert row["doors_open_at_utc"] == "2026-11-07T09:30:00Z"
    assert (row["price_krw"], row["price_basis"]) == (15000, "advance")


def test_seed_is_idempotent(db):
    from seed import seed

    before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    result = seed(db, base_date=BASE_DATE)
    assert result["inserted_events"] == 0
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before
    assert db.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 4
    result = seed(db, base_date=BASE_DATE, reset=True)
    assert result["events"] == before and result["inserted_events"] == before


# ---------- API ----------
def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "amp-api", "version": "1.1.0"}


def test_unknown_route_uses_common_error_shape(client):
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert set(res.json()["error"]) == {"code", "message", "details"}


def test_media_serving_and_path_traversal(client, env):
    posters = env / "uploads" / "posters"
    posters.mkdir(parents=True)
    (posters / "1.png").write_bytes(b"\x89PNG\r\n\x1a\nxx")
    assert client.get("/media/posters/1.png").status_code == 200
    assert client.get("/media/posters/..%2F..%2Famp.db").status_code == 404
    assert client.get("/media/secret/1.png").status_code == 404


def test_cors_restricted_origin(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_cors_default_allows_frontend_dev_origins(db, monkeypatch):
    """프런트 `npm run dev`(vite --host 127.0.0.1)와 localhost 둘 다 허용, 그 외는 차단."""
    from fastapi.testclient import TestClient

    from main import create_app

    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with TestClient(create_app()) as c:
        for origin in ("http://127.0.0.1:5173", "http://localhost:5173"):
            res = c.get("/api/health", headers={"Origin": origin})
            assert res.headers.get("access-control-allow-origin") == origin
        pre = c.options("/api/health", headers={"Origin": "http://127.0.0.1:5173",
                                                "Access-Control-Request-Method": "GET"})
        assert pre.status_code == 200
        assert "access-control-allow-origin" not in c.get(
            "/api/health", headers={"Origin": "http://evil.example"}).headers
