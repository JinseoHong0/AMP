import os
import sqlite3
import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import ApiError
from backend.main import create_app
from backend.poster_schemas import VenueSummary
from backend.services.poster_parser import review_extraction
from backend.services.poster_uploads import MAX_FILE_BYTES
from backend.services.venue_matcher import match_venue


@pytest.mark.parametrize(
    "format_name,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_upload_contract_and_no_event_write(client, app, image_bytes, format_name, mime):
    content = image_bytes(format_name)
    response = client.post("/api/posters/parse", files={"file": ("../../evil.png", content, mime)})
    assert response.status_code == 200, response.text
    result = response.json()
    assert str(UUID(result["upload_id"])) == result["upload_id"]
    assert set(result) == {"upload_id", "extracted", "venue_match", "needs_review", "warnings"}
    assert result["venue_match"]["status"] == "matched"
    assert result["venue_match"]["venue_id"] == 1
    assert result["extracted"]["price_krw"] == 18000
    assert result["extracted"]["doors_open_at_local"] is None
    assert "doors_open_at_local" in result["needs_review"]
    assert app.state.upload_store.resolve(result["upload_id"]).read_bytes() == content
    app.state.poster_client.extract.assert_awaited_once_with(content, mime)
    with sqlite3.connect(app.state.venue_repository.path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("venues",)]


@pytest.mark.parametrize(
    "body,mime,status,code",
    [
        (b"%PDF-1.7", "application/pdf", 415, "UNSUPPORTED_FILE_TYPE"),
        (b"not an image", "image/png", 400, "INVALID_IMAGE"),
        (b"\x89PNG\r\n\x1a\n", "image/png", 400, "INVALID_IMAGE"),
        (b"", "image/png", 400, "INVALID_IMAGE"),
        (b"a" * (MAX_FILE_BYTES + 1), "image/png", 413, "FILE_TOO_LARGE"),
    ],
)
def test_bad_uploads_do_not_call_ai(client, app, body, mime, status, code):
    response = client.post("/api/posters/parse", files={"file": ("poster", body, mime)})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    app.state.poster_client.extract.assert_not_awaited()
    assert not app.state.upload_store.root.exists()


def test_mime_spoof_and_missing_file(client, image_bytes):
    response = client.post(
        "/api/posters/parse", files={"file": ("x.png", image_bytes("JPEG"), "image/png")}
    )
    assert response.status_code == 400
    missing = client.post("/api/posters/parse")
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "VALIDATION_ERROR"


def test_total_request_limit_before_multipart_parse(client, app):
    response = client.post("/api/posters/parse", content=b"x" * (MAX_FILE_BYTES + 65537))
    assert response.status_code == 413
    app.state.poster_client.extract.assert_not_awaited()


@pytest.mark.parametrize(
    "names,status",
    [
        ([], "not_found"),
        (["Sample Club"], "matched"),
        (["Sample Club", "ＳＡＭＰＬＥ   ＣＬＵＢ"], "ambiguous"),
    ],
)
def test_matching_is_unique_normalized_exact_only(names, status):
    venues = [VenueSummary(id=i + 1, name=name, area="hongdae") for i, name in enumerate(names)]
    match = match_venue("sample club", venues)
    assert match.status == status
    assert (match.venue_id is not None) == (status == "matched")
    assert match_venue(None, venues).status == "no_name"
    assert match_venue("Sample Klub", venues).status == "not_found"


@pytest.mark.parametrize("flag", ["date_has_explicit_year", "multiple_schedules"])
def test_year_missing_or_multiple_dates_not_guessed(vision_result, flag):
    setattr(vision_result, flag, flag == "multiple_schedules")
    fields, review, warnings = review_extraction(vision_result)
    assert fields.starts_at_local is None
    assert fields.doors_open_at_local is None
    assert "starts_at_local" in review
    assert warnings


def test_invalid_readings_remain_reviewable_and_free_not_unknown(vision_result):
    vision_result.extracted.starts_at_local = "2026-02-30T19:00:00"
    vision_result.extracted.advance_price_krw = -100
    vision_result.extracted.door_price_krw = 0
    fields, review, warnings = review_extraction(vision_result)
    assert fields.starts_at_local is None
    assert fields.advance_price_krw is None
    assert fields.price_krw == 0
    assert "advance_price_krw" in review
    assert any("-100" in warning for warning in warnings)
    vision_result.extracted.price_krw = None
    vision_result.extracted.advance_price_krw = None
    vision_result.extracted.door_price_krw = None
    assert review_extraction(vision_result)[0].price_krw is None


def test_unknown_venue_returns_review_not_new_venue(client, app, image_bytes, vision_result):
    vision_result.extracted.venue_name = "없는 장소"
    response = client.post(
        "/api/posters/parse", files={"file": ("x.png", image_bytes(), "image/png")}
    )
    assert response.status_code == 200
    assert response.json()["venue_match"] == {
        "status": "not_found",
        "venue_id": None,
        "candidates": [],
    }
    assert "venue_id" in response.json()["needs_review"]
    assert len(app.state.venue_repository.list_venues()) == 1


def test_missing_db_is_not_silently_empty(client, app, image_bytes):
    app.state.venue_repository.path.unlink()
    response = client.post(
        "/api/posters/parse", files={"file": ("x.png", image_bytes(), "image/png")}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "VENUE_DB_UNAVAILABLE"
    app.state.poster_client.extract.assert_not_awaited()
    assert not app.state.venue_repository.path.exists()


def test_ai_failure_does_not_leave_upload(client, app, image_bytes):
    app.state.poster_client.extract.side_effect = ApiError(503, "AI_UNAVAILABLE", "AI 오류")
    response = client.post(
        "/api/posters/parse", files={"file": ("x.png", image_bytes(), "image/png")}
    )
    assert response.status_code == 503
    assert not app.state.upload_store.root.exists()


def test_local_only_and_cors(app, client, image_bytes):
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("203.0.113.1", 123)) as remote:
        assert remote.post("/api/posters/parse").status_code == 403
    response = client.post("/api/posters/parse", headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403
    response = client.options(
        "/api/posters/parse",
        headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    disabled = create_app(Settings(_env_file=None, local_demo=False))
    with TestClient(disabled, base_url="http://127.0.0.1", client=("127.0.0.1", 123)) as local:
        assert local.post("/api/posters/parse").status_code == 403


def test_upload_expiry_and_traversal(client, app, image_bytes):
    result = client.post(
        "/api/posters/parse", files={"file": ("x.png", image_bytes(), "image/png")}
    ).json()
    store = app.state.upload_store
    with pytest.raises(ApiError):
        store.resolve("../../.env")
    directory = store.resolve(result["upload_id"]).parent
    old = time.time() - 25 * 3600
    os.utime(directory, (old, old))
    with pytest.raises(ApiError):
        store.resolve(result["upload_id"])
    store.cleanup()
    assert not directory.exists()
