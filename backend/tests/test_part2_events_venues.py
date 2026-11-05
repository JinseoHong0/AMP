"""2단계: GET /api/events, /api/events/{id}, /api/venues, /api/venues/{id}."""
from __future__ import annotations

EVENT_SUMMARY_KEYS = {
    "id", "title", "starts_at", "price_krw", "price_basis", "advance_price_krw", "door_price_krw",
    "genre", "mood_tags", "seating_type", "poster_url", "venue", "data_origin",
}
EVENT_DETAIL_KEYS = {
    "id", "venue_id", "title", "starts_at", "ends_at", "doors_open_at", "price_krw", "price_basis",
    "advance_price_krw", "door_price_krw", "booking_url", "lineup", "genre", "mood_tags", "solo_friendly",
    "seating_type", "seat_assignment", "drink_policy", "description_ko", "description_en",
    "admission_notes_ko", "admission_notes_en", "poster_url", "status", "data_origin", "source_url",
    "verified_at",
}
VENUE_DETAIL_KEYS = {
    "id", "name", "area", "address", "floor", "entrance_image_url", "default_seating_type",
    "default_drink_policy", "entrance_hint_ko", "entrance_hint_en", "description_ko", "description_en",
    "source_url", "verified_at", "data_origin",
}


def _titles(res):
    return [i["title"] for i in res.json()["items"]]


def _event_id(db, title):
    return db.execute("SELECT id FROM events WHERE title = ?", (title,)).fetchone()["id"]


# ---------- GET /api/events ----------
def test_list_default_upcoming_published_only(client):
    res = client.get("/api/events")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 20 and body["limit"] == 20 and len(body["items"]) == 20
    titles = _titles(res)
    assert not {"지난 공연", "준비 중 공연", "취소된 공연"} & set(titles)
    assert set(body["items"][0]) == EVENT_SUMMARY_KEYS
    starts = [i["starts_at"] for i in body["items"]]
    assert starts == sorted(starts)


def test_list_upcoming_false_includes_past_but_not_draft_or_cancelled(client):
    titles = _titles(client.get("/api/events", params={"upcoming": "false", "limit": 50}))
    assert "지난 공연" in titles
    assert "준비 중 공연" not in titles and "취소된 공연" not in titles


def test_list_api_doc_example_filter(client):
    res = client.get("/api/events", params={"date": "2026-11-07", "area": "sinchon", "max_price_krw": 20000})
    assert res.status_code == 200
    assert set(_titles(res)) == {"밤의 산책", "어쿠스틱 선데이", "새벽 네온"}  # 가격 미확인 '모노 포크 나잇' 제외
    item = next(i for i in res.json()["items"] if i["title"] == "밤의 산책")
    assert item["starts_at"] == "2026-11-07T10:00:00Z"
    assert (item["price_krw"], item["price_basis"]) == (15000, "advance")
    assert (item["advance_price_krw"], item["door_price_krw"]) == (15000, 20000)
    assert item["venue"] == {"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"}
    assert item["mood_tags"] == ["calm", "acoustic"] and item["data_origin"] == "demo"


def test_list_kst_date_boundary(client):
    # KST 11/7 하루만. 11/6, 11/8 공연이 섞이지 않아야 한다.
    res = client.get("/api/events", params={"date": "2026-11-07"})
    assert res.json()["total"] == 8
    for item in res.json()["items"]:
        assert "2026-11-06T15:00:00Z" <= item["starts_at"] < "2026-11-07T15:00:00Z"


def test_list_seating_type_exact_event_value_only(client):
    res = client.get("/api/events", params={"date": "2026-11-07", "seating_type": "seated"})
    titles = set(_titles(res))
    assert titles == {"밤의 산책", "어쿠스틱 선데이", "모노 포크 나잇", "블루 재즈 데이트"}
    # 공연장 기본값이 seated 여도 이벤트 seating_type=null 이면 제외
    assert "라운지 언플러그드" not in titles


def test_list_free_only_with_zero_budget(client):
    res = client.get("/api/events", params={"max_price_krw": 0})
    assert set(_titles(res)) == {"라운지 언플러그드", "신인 밴드 경연"}
    assert all(i["price_krw"] == 0 for i in res.json()["items"])


def test_list_limit_and_total(client):
    body = client.get("/api/events", params={"limit": 3}).json()
    assert len(body["items"]) == 3 and body["total"] == 20 and body["limit"] == 3


def test_list_validation_errors(client):
    for params in ({"limit": 0}, {"limit": 51}, {"max_price_krw": -1}, {"area": "gangnam"},
                   {"date": "11/07"}, {"date": "2026-13-40"}, {"seating_type": "vip"}, {"locale": "jp"}):
        res = client.get("/api/events", params=params)
        assert res.status_code == 422, params
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"
        assert res.json()["error"]["details"]["field"] in params


# ---------- GET /api/events/{id} ----------
def test_detail_matches_contract(client, db):
    res = client.get(f"/api/events/{_event_id(db, '밤의 산책')}")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == EVENT_DETAIL_KEYS
    assert body["doors_open_at"] == "2026-11-07T09:30:00Z" and body["starts_at"] == "2026-11-07T10:00:00Z"
    assert body["ends_at"] == "2026-11-07T12:00:00Z"
    assert body["lineup"] == ["Sample Band A"] and body["solo_friendly"] is True
    assert body["seat_assignment"] == "unassigned" and body["status"] == "published"
    assert body["admission_notes_en"].startswith("Unassigned seating")


def test_detail_doors_unknown_is_not_copied_from_start(client, db):
    body = client.get(f"/api/events/{_event_id(db, '모노 포크 나잇')}").json()
    assert body["doors_open_at"] is None and body["starts_at"] is not None
    assert body["price_krw"] is None and body["price_basis"] is None


def test_detail_missing_english_stays_null(client, db):
    body = client.get(f"/api/events/{_event_id(db, '홍대 록 파티')}").json()
    assert body["admission_notes_ko"] and body["admission_notes_en"] is None
    assert body["description_en"] is None


def test_detail_draft_cancelled_missing_are_404(client, db):
    for title in ("준비 중 공연", "취소된 공연"):
        res = client.get(f"/api/events/{_event_id(db, title)}")
        assert res.status_code == 404 and res.json()["error"]["code"] == "EVENT_NOT_FOUND"
    res = client.get("/api/events/99999")
    assert res.status_code == 404 and res.json()["error"]["code"] == "EVENT_NOT_FOUND"
    assert client.get("/api/events/abc").status_code == 422


# ---------- GET /api/venues ----------
def test_venue_list_and_search(client):
    body = client.get("/api/venues").json()
    assert body["total"] == 4 and set(body["items"][0]) == {"id", "name", "area"}

    hongdae = client.get("/api/venues", params={"area": "hongdae"}).json()
    assert {v["name"] for v in hongdae["items"]} == {"데모 스테이지", "블루 앰프 라운지"}

    # 공백/대소문자/NFKC 정규화된 부분 검색
    found = client.get("/api/venues", params={"q": " 라이브  클럽"}).json()
    assert [v["name"] for v in found["items"]] == ["샘플 라이브 클럽"]

    none = client.get("/api/venues", params={"q": "없는공연장"}).json()
    assert none == {"items": [], "total": 0}

    limited = client.get("/api/venues", params={"limit": 2}).json()
    assert len(limited["items"]) == 2 and limited["total"] == 4


def test_venue_search_does_not_create(client, db):
    client.get("/api/venues", params={"q": "새 공연장"})
    assert db.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 4


def test_venue_list_validation(client):
    assert client.get("/api/venues", params={"q": "x" * 101}).status_code == 422
    assert client.get("/api/venues", params={"limit": 0}).status_code == 422
    assert client.get("/api/venues", params={"area": "busan"}).status_code == 422


# ---------- GET /api/venues/{id} ----------
def test_venue_detail(client):
    res = client.get("/api/venues/1")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == VENUE_DETAIL_KEYS
    assert body["floor"] == "B1" and body["default_seating_type"] == "seated"
    assert body["entrance_image_url"] is None  # 사진 없으면 임의 생성하지 않음
    assert body["data_origin"] == "demo"
    assert client.get("/api/venues/2").json()["entrance_hint_en"] is None


def test_venue_detail_404(client):
    res = client.get("/api/venues/999")
    assert res.status_code == 404 and res.json()["error"]["code"] == "VENUE_NOT_FOUND"


def test_media_url_mapping():
    from models import media_url

    assert media_url(None) is None
    assert media_url("posters/1.webp") == "/media/posters/1.webp"
    assert media_url("https://cdn.example.com/a.jpg") == "https://cdn.example.com/a.jpg"
