"""4단계: 공연장 매칭, POST /api/posters/parse, POST /api/events, 관리자 접근 제한.

Vision AI 는 공란이므로 성공 경로는 services.poster_parser.call_llm_poster 를 가짜로 바꿔 검증한다.
"""
from __future__ import annotations

import pytest

from services import poster_parser

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64

DOC_EXTRACTION = {
    "title": "토요일 인디 라이브",
    "starts_at_local": "2026-11-07T20:00:00",
    "doors_open_at_local": None,
    "venue_name": "샘플 라이브 클럽",
    "price_krw": 18000,
    "advance_price_krw": 18000,
    "door_price_krw": 22000,
    "lineup": ["Sample Band A", "Sample Band B"],
    "genre": None,
}


@pytest.fixture()
def fake_vision(monkeypatch):
    state = {"payload": dict(DOC_EXTRACTION)}

    def _fake(image_bytes, mime_type):
        if isinstance(state["payload"], Exception):
            raise state["payload"]
        return state["payload"]

    monkeypatch.setattr(poster_parser, "call_llm_poster", _fake)
    return state


def _upload(client, data=PNG, mime="image/png", name="poster.png", **kw):
    return client.post("/api/posters/parse", files={"file": (name, data, mime)}, **kw)


def _event_body(**overrides):
    body = {
        "upload_id": None,
        "venue_id": 1,
        "title": "토요일 인디 라이브",
        "starts_at_local": "2026-11-07T20:00:00",
        "ends_at_local": None,
        "doors_open_at_local": None,
        "price_krw": 18000,
        "advance_price_krw": 18000,
        "door_price_krw": 22000,
        "booking_url": None,
        "lineup": ["Sample Band A", "Sample Band B"],
        "genre": "indie",
        "mood_tags": ["energetic"],
        "solo_friendly": None,
        "seating_type": None,
        "seat_assignment": None,
        "drink_policy": None,
        "description_ko": None,
        "description_en": None,
        "admission_notes_ko": None,
        "admission_notes_en": None,
        "source_url": None,
        "data_origin": "demo",
        "review_confirmed": True,
    }
    body.update(overrides)
    return body


def _err(res):
    return res.json()["error"]


# ---------- venue_matcher ----------
def test_normalize_name():
    from services.venue_matcher import normalize_name

    assert normalize_name("  샘플  라이브·클럽! ") == normalize_name("샘플 라이브 클럽")
    assert normalize_name("ＡＭＰ Hall") == normalize_name("amp hall")  # NFKC + casefold
    assert normalize_name(None) == "" and normalize_name("   ") == ""


def test_match_statuses(db):
    from services.venue_matcher import match_venue

    m = match_venue(db, "샘플 라이브 클럽")
    assert m == {"status": "matched", "venue_id": 1,
                 "candidates": [{"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"}]}
    assert match_venue(db, "샘플라이브클럽")["status"] == "matched"
    # 유사 문자열은 확정하지 않는다
    assert match_venue(db, "샘플 라이브")["status"] == "not_found"
    assert match_venue(db, "없는 공연장") == {"status": "not_found", "venue_id": None, "candidates": []}
    assert match_venue(db, None) == {"status": "no_name", "venue_id": None, "candidates": []}
    assert match_venue(db, "  ")["status"] == "no_name"

    db.execute("INSERT INTO venues (name, area, data_origin) VALUES ('샘플 라이브-클럽', 'hongdae', 'demo')")
    db.commit()
    amb = match_venue(db, "샘플 라이브 클럽")
    assert amb["status"] == "ambiguous" and amb["venue_id"] is None and len(amb["candidates"]) == 2


# ---------- POST /api/posters/parse ----------
def test_parse_doc_example(client, fake_vision, env):
    res = _upload(client)
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["extracted"] == DOC_EXTRACTION
    assert body["venue_match"]["status"] == "matched" and body["venue_match"]["venue_id"] == 1
    assert body["needs_review"] == ["doors_open_at_local"]
    assert body["warnings"] == ["입장 시작 시각은 포스터에서 확인되지 않았습니다."]
    assert poster_parser.is_valid_upload_id(body["upload_id"])
    assert (env / "uploads" / "tmp" / f"{body['upload_id']}.png").is_file()


def test_parse_creates_no_event(client, fake_vision, db):
    before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    _upload(client)
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before


@pytest.mark.parametrize("data, mime", [(JPEG, "image/jpeg"), (WEBP, "image/webp"), (PNG, "image/png")])
def test_parse_accepts_formats(client, fake_vision, data, mime):
    assert _upload(client, data, mime).status_code == 200


def test_parse_not_found_and_no_name_need_venue_review(client, fake_vision):
    fake_vision["payload"] = {**DOC_EXTRACTION, "venue_name": "어딘가 클럽"}
    body = _upload(client).json()
    assert body["venue_match"] == {"status": "not_found", "venue_id": None, "candidates": []}
    assert "venue_id" in body["needs_review"]

    fake_vision["payload"] = {**DOC_EXTRACTION, "venue_name": None}
    body = _upload(client).json()
    assert body["venue_match"]["status"] == "no_name" and "venue_id" in body["needs_review"]


def test_parse_does_not_guess_values(client, fake_vision):
    # 연도 누락 등으로 AI 가 null 을 준 경우: 값을 채우지 않고 검수 요청
    fake_vision["payload"] = {"title": None, "starts_at_local": None, "venue_name": "데모 스테이지",
                              "price_krw": None, "lineup": [], "genre": None}
    body = _upload(client).json()
    ex = body["extracted"]
    assert ex["starts_at_local"] is None and ex["doors_open_at_local"] is None and ex["price_krw"] is None
    assert set(body["needs_review"]) == {"title", "starts_at_local", "doors_open_at_local", "price_krw"}


def test_parse_normalizes_bad_ai_values(client, fake_vision):
    fake_vision["payload"] = {**DOC_EXTRACTION, "price_krw": 22000, "door_price_krw": -1,
                              "starts_at_local": "11월 7일 8시", "doors_open_at_local": "2026-11-07T21:00:00",
                              "lineup": ["A", "", 3, " B "], "venue_id": 99}
    body = _upload(client).json()
    ex = body["extracted"]
    assert ex["door_price_krw"] is None
    assert ex["price_krw"] == 18000  # 구분 가격 최저값으로 보정
    assert ex["starts_at_local"] is None and "starts_at_local" in body["needs_review"]
    assert ex["lineup"] == ["A", "B"]
    assert "venue_id" not in ex  # AI 가 준 venue_id 는 무시
    assert "price_krw" in body["needs_review"]


def test_parse_ai_unavailable_is_503(client):
    res = _upload(client)
    assert res.status_code == 503 and _err(res)["code"] == "AI_UNAVAILABLE"


def test_parse_ai_unexpected_error_is_503_without_leak(client, fake_vision):
    fake_vision["payload"] = RuntimeError("secret-key-sk-123")
    res = _upload(client)
    assert res.status_code == 503 and "secret" not in res.text


def test_parse_file_validation(client, fake_vision, monkeypatch):
    assert _err(_upload(client, PDF, "application/pdf", "a.pdf"))["code"] == "UNSUPPORTED_FILE_TYPE"
    assert _upload(client, PDF, "application/pdf", "a.pdf").status_code == 415
    # 확장자/MIME 은 이미지인데 실제 내용이 PDF·손상
    res = _upload(client, PDF, "image/png")
    assert res.status_code == 400 and _err(res)["code"] == "INVALID_IMAGE"
    assert _upload(client, b"", "image/png").status_code == 400
    assert _upload(client, JPEG, "image/png").status_code == 400  # 시그니처 불일치
    # 5MB 초과
    big = PNG + b"\x00" * (5 * 1024 * 1024)
    res = _upload(client, big, "image/png")
    assert res.status_code == 413 and _err(res)["code"] == "FILE_TOO_LARGE"
    # file 필드 누락
    res = client.post("/api/posters/parse", data={})
    assert res.status_code == 422 and _err(res)["code"] == "VALIDATION_ERROR"


# ---------- POST /api/events ----------
def test_register_doc_example_and_reflected_in_list(client):
    res = client.post("/api/events", json=_event_body())
    assert res.status_code == 201, res.json()
    body = res.json()
    assert body["status"] == "published" and body["poster_url"] is None
    assert body["message"] == "공연이 등록되었습니다."
    # 프런트 CreatedEvent 계약: 번역 상태와 경고 (AI 번역 미연결 → not_requested)
    assert body["translation"] == {"status": "not_requested", "generated_at": None}
    assert body["warnings"] == ["공연은 등록되었으나 영어 번역은 아직 준비되지 않았습니다."]

    detail = client.get(f"/api/events/{body['id']}").json()
    assert detail["starts_at"] == "2026-11-07T11:00:00Z"  # KST 20:00 → UTC 11:00
    assert detail["doors_open_at"] is None
    assert (detail["price_krw"], detail["price_basis"]) == (18000, "advance")
    assert detail["data_origin"] == "demo" and detail["verified_at"] is None

    listed = client.get("/api/events", params={"date": "2026-11-07", "area": "sinchon"}).json()
    assert body["id"] in [i["id"] for i in listed["items"]]


def test_register_appears_in_recommend_only_when_matching(client):
    new_id = client.post("/api/events", json=_event_body()).json()["id"]
    hit = client.post("/api/recommend", json={"filters": {"date": "2026-11-07", "area": "sinchon",
                                                          "max_price_krw": 20000, "mood_tags": ["energetic"]}})
    ids = [i["event"]["id"] for i in hit.json()["items"]]
    assert new_id in ids
    miss = client.post("/api/recommend", json={"filters": {"date": "2026-11-07", "area": "sinchon",
                                                           "seating_requirement": "seated"}})
    assert new_id not in [i["event"]["id"] for i in miss.json()["items"]]  # seating_type=null


def test_register_with_upload_and_duplicate(client, fake_vision, env):
    upload_id = _upload(client).json()["upload_id"]
    res = client.post("/api/events", json=_event_body(upload_id=upload_id))
    assert res.status_code == 201
    event_id = res.json()["id"]
    assert res.json()["poster_url"] == f"/media/posters/{event_id}.png"
    assert (env / "uploads" / "posters" / f"{event_id}.png").is_file()
    assert client.get(res.json()["poster_url"]).status_code == 200

    dup = client.post("/api/events", json=_event_body(upload_id=upload_id))
    assert dup.status_code == 409 and _err(dup)["code"] == "UPLOAD_ALREADY_USED"


@pytest.mark.parametrize("upload_id", ["../../etc/passwd", "not-a-uuid", "00000000-0000-4000-8000-000000000000"])
def test_register_invalid_upload_id(client, upload_id):
    res = client.post("/api/events", json=_event_body(upload_id=upload_id))
    assert res.status_code == 422 and _err(res)["details"]["field"] == "upload_id"


@pytest.mark.parametrize("venue_id", [None, 0, -1, 999])
def test_register_requires_existing_venue(client, db, venue_id):
    before = db.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
    res = client.post("/api/events", json=_event_body(venue_id=venue_id))
    assert res.status_code == 422 and _err(res)["code"] == "VENUE_REQUIRED"
    assert db.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == before


def test_register_requires_review_confirmed(client, db):
    before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    for value in (False, None):
        body = _event_body(review_confirmed=value)
        if value is None:
            body.pop("review_confirmed")
        res = client.post("/api/events", json=body)
        assert res.status_code == 422 and _err(res)["details"]["field"] == "review_confirmed"
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before


@pytest.mark.parametrize(
    "prices, expected",
    [
        ({"price_krw": None, "advance_price_krw": 20000, "door_price_krw": 25000}, (20000, "advance")),
        ({"price_krw": None, "advance_price_krw": None, "door_price_krw": 25000}, (25000, "door")),
        ({"price_krw": 15000, "advance_price_krw": None, "door_price_krw": None}, (15000, "general")),
        ({"price_krw": 0, "advance_price_krw": None, "door_price_krw": None}, (0, "general")),
        ({"price_krw": None, "advance_price_krw": None, "door_price_krw": None}, (None, None)),
        ({"price_krw": None, "advance_price_krw": 20000, "door_price_krw": 20000}, (20000, "advance")),
    ],
)
def test_register_price_rules(client, prices, expected):
    res = client.post("/api/events", json=_event_body(**prices))
    assert res.status_code == 201, res.json()
    d = client.get(f"/api/events/{res.json()['id']}").json()
    assert (d["price_krw"], d["price_basis"]) == expected


def test_register_price_mismatch_and_basis_input_rejected(client):
    res = client.post("/api/events", json=_event_body(price_krw=25000, advance_price_krw=20000, door_price_krw=25000))
    assert res.status_code == 422 and _err(res)["details"]["field"] == "price_krw"
    res = client.post("/api/events", json={**_event_body(), "price_basis": "general"})
    assert res.status_code == 422 and _err(res)["details"]["field"] == "price_basis"
    res = client.post("/api/events", json=_event_body(door_price_krw=-100))
    assert res.status_code == 422


def test_register_time_order(client):
    res = client.post("/api/events", json=_event_body(doors_open_at_local="2026-11-07T20:30:00"))
    assert res.status_code == 422 and _err(res)["details"]["field"] == "doors_open_at_local"
    res = client.post("/api/events", json=_event_body(ends_at_local="2026-11-07T19:00:00"))
    assert res.status_code == 422 and _err(res)["details"]["field"] == "ends_at_local"
    ok = client.post("/api/events", json=_event_body(doors_open_at_local="2026-11-07T19:30:00",
                                                     ends_at_local="2026-11-07T22:00:00"))
    assert ok.status_code == 201
    d = client.get(f"/api/events/{ok.json()['id']}").json()
    assert d["doors_open_at"] == "2026-11-07T10:30:00Z" and d["ends_at"] == "2026-11-07T13:00:00Z"


@pytest.mark.parametrize(
    "override, field",
    [
        ({"title": ""}, "title"),
        ({"title": "   "}, "title"),
        ({"title": "가" * 121}, "title"),
        ({"starts_at_local": None}, "starts_at_local"),
        ({"starts_at_local": "내일 저녁"}, "starts_at_local"),
        ({"seating_type": "vip"}, "seating_type"),
        ({"seat_assignment": "first_come"}, "seat_assignment"),
        ({"mood_tags": ["cozy"]}, "mood_tags.0"),
        ({"data_origin": "crawled"}, "data_origin"),
        ({"booking_url": "javascript:alert(1)"}, "booking_url"),
        ({"source_url": "ftp://x"}, "source_url"),
        ({"data_origin": "verified"}, "source_url"),
    ],
)
def test_register_field_validation(client, override, field):
    res = client.post("/api/events", json=_event_body(**override))
    assert res.status_code == 422, res.json()
    assert _err(res)["details"]["field"] == field


def test_register_verified_with_source(client):
    res = client.post("/api/events", json=_event_body(data_origin="verified", source_url="https://example.com/a"))
    assert res.status_code == 201
    d = client.get(f"/api/events/{res.json()['id']}").json()
    assert d["data_origin"] == "verified" and d["verified_at"] == "2026-11-06T03:00:00Z"


def test_register_manual_when_ai_down(client):
    # AI 미연결 → 포스터 분석 503 이어도 수동 등록(upload_id=null)은 가능
    assert _upload(client).status_code == 503
    assert client.post("/api/events", json=_event_body(upload_id=None)).status_code == 201


# ---------- 관리자 접근 제한 ----------
def test_admin_endpoints_blocked_from_remote(remote_client):
    for res in (remote_client.post("/api/events", json=_event_body()),
                remote_client.post("/api/posters/parse", files={"file": ("p.png", PNG, "image/png")})):
        assert res.status_code == 403 and _err(res)["code"] == "FORBIDDEN"
    # 공개 GET 은 원격에서도 허용
    assert remote_client.get("/api/events").status_code == 200


def test_admin_api_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    res = client.post("/api/events", json=_event_body())
    assert res.status_code == 401 and _err(res)["code"] == "UNAUTHORIZED"
    res = client.post("/api/events", json=_event_body(), headers={"X-Admin-Key": "wrong"})
    assert res.status_code == 401
    res = client.post("/api/events", json=_event_body(), headers={"X-Admin-Key": "test-key"})
    assert res.status_code == 201


def test_admin_disabled_when_not_demo_and_no_key(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    assert client.post("/api/events", json=_event_body()).status_code == 403


def test_openapi_operations(client):
    paths = client.get("/openapi.json").json()["paths"]
    ops = {(p, m) for p, methods in paths.items() for m in methods}
    assert ops == {
        ("/api/health", "get"), ("/api/events", "get"), ("/api/events/{event_id}", "get"),
        ("/api/venues", "get"), ("/api/venues/{venue_id}", "get"), ("/api/recommend", "post"),
        ("/api/posters/parse", "post"), ("/api/events", "post"), ("/api/translate", "post"),
    }


def test_register_accepts_frontend_payload_and_4000_char_texts(client):
    """프런트 registrationPayload 와 같은 형태(영문·price_basis 없음), 원문 텍스트 4,000자까지 허용."""
    payload = {
        "title": "프런트 등록", "venue_id": 1, "upload_id": None,
        "starts_at_local": "2026-11-20T19:30:00", "ends_at_local": None, "doors_open_at_local": "2026-11-20T19:00:00",
        "price_krw": 20000, "advance_price_krw": 20000, "door_price_krw": 25000,
        "lineup": ["A", "B"], "genre": None, "mood_tags": [], "solo_friendly": None,
        "seating_type": None, "seat_assignment": None,
        "drink_policy": "가" * 4000, "description_ko": "나" * 4000, "admission_notes_ko": "다" * 4000,
        "booking_url": None, "source_url": None, "data_origin": "demo", "review_confirmed": True,
    }
    res = client.post("/api/events", json=payload)
    assert res.status_code == 201, res.json()
    detail = client.get(f"/api/events/{res.json()['id']}").json()
    assert len(detail["description_ko"]) == 4000 and detail["doors_open_at"] == "2026-11-20T10:00:00Z"
    too_long = client.post("/api/events", json={**payload, "drink_policy": "가" * 4001})
    assert too_long.status_code == 422 and _err(too_long)["details"]["field"] == "drink_policy"
