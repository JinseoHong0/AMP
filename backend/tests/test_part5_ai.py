"""5단계: Gemini 호출 · 등록 시 영문 자동 번역 · 번역 재시도 · 포스터 Vision 추출 (가짜 Gemini)."""
from __future__ import annotations

import base64

import httpx
import pytest

from conftest import text

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

SOURCE_EN = {
    "title_en": "Saturday Indie Live",
    "description_en": "A small acoustic show.",
    "admission_notes_en": "Unassigned seating. First come, first served.",
    "drink_policy_en": "One drink order (5,000 won) is required.",
}


def _event_body(**overrides):
    body = {
        "upload_id": None, "venue_id": 1, "title": "토요일 인디 라이브",
        "starts_at_local": "2026-11-07T20:00:00", "ends_at_local": None, "doors_open_at_local": None,
        "price_krw": 18000, "advance_price_krw": 18000, "door_price_krw": 22000, "booking_url": None,
        "lineup": ["Sample Band A"], "genre": "indie", "mood_tags": ["energetic"], "solo_friendly": None,
        "seating_type": None, "seat_assignment": None,
        "drink_policy": "음료 1잔(5,000원) 주문이 필요합니다.",
        "description_ko": "어쿠스틱 중심의 소규모 공연입니다.",
        "admission_notes_ko": "좌석은 비지정석입니다. 선착순으로 입장합니다.",
        "source_url": None, "data_origin": "demo", "review_confirmed": True,
    }
    body.update(overrides)
    return body


# ---------- Gemini 공통 호출 ----------
def test_gemini_request_shape_and_secret_handling(gemini):
    from services import reason

    gemini.add(text({"ok": True}))
    content = reason.gemini_generate([{"role": "user", "parts": [{"text": "hi"}]}], timeout_s=5,
                                     system="sys", response_schema={"type": "object"})
    assert reason.content_json(content) == {"ok": True}
    body = gemini.requests[0]
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert gemini.headers[0]["x-goog-api-key"] == "test-key" and "key=" not in gemini.urls[0]


@pytest.mark.parametrize("failure", [503, 429, 400, httpx.ReadTimeout("slow"), httpx.ConnectError("down")])
def test_gemini_failures_become_ai_unavailable(gemini, failure):
    from models import AIUnavailableError
    from services import reason

    gemini.add(failure)
    with pytest.raises(AIUnavailableError) as info:
        reason.gemini_generate([{"role": "user", "parts": [{"text": "hi"}]}], timeout_s=5)
    assert "test-key" not in str(info.value)


def test_gemini_transient_errors_retry_within_limit(gemini):
    from models import AIUnavailableError
    from services import reason

    gemini.add(503, 429, text({"ok": True}))
    content = reason.gemini_generate([{"role": "user", "parts": [{"text": "hi"}]}], timeout_s=10,
                                     transient_retries=2)
    assert reason.content_json(content) == {"ok": True} and len(gemini.requests) == 3

    gemini.add(503, 503)  # 재시도 1회까지만
    with pytest.raises(AIUnavailableError):
        reason.gemini_generate([{"role": "user", "parts": [{"text": "hi"}]}], timeout_s=10, transient_retries=1)
    assert len(gemini.requests) == 5

    gemini.add(400)  # 요청 오류는 재시도하지 않음
    with pytest.raises(AIUnavailableError):
        reason.gemini_generate([{"role": "user", "parts": [{"text": "hi"}]}], timeout_s=10, transient_retries=2)
    assert len(gemini.requests) == 6


def test_gemini_not_configured_and_thought_parts_ignored(env, gemini):
    from services import reason

    content = {"role": "model", "parts": [{"text": "thinking...", "thought": True}, {"text": "{\"a\": 1}"}]}
    assert reason.content_json(content) == {"a": 1}
    assert reason.content_json(text("```json\n{\"b\": 2}\n```")) == {"b": 2}


# ---------- 번역 검증 ----------
def test_validate_translation_rules():
    from services.reason import validate_translation

    source = {"title": "공연", "description_ko": None, "admission_notes_ko": "현장 20,000원", "drink_policy": None}
    ok = {"title_en": "Show", "description_en": None, "admission_notes_en": "20,000 won at the door",
          "drink_policy_en": None}
    assert validate_translation(source, ok)["admission_notes_en"] == "20,000 won at the door"
    for bad, message in [
        ({**ok, "description_en": "invented"}, "원문이 없는데"),
        ({**ok, "title_en": "  "}, "비어"),
        ({**ok, "admission_notes_en": "25,000 won at the door"}, "금액"),
        ({**ok, "title_en": "x" * 501}, "너무 깁니다"),
    ]:
        with pytest.raises(ValueError, match=message):
            validate_translation(source, bad)


# ---------- 등록 시 자동 번역 ----------
def test_register_generates_and_stores_english(client, gemini):
    gemini.add(text(SOURCE_EN))
    res = client.post("/api/events", json=_event_body())
    assert res.status_code == 201, res.json()
    created = res.json()
    assert created["translation"]["status"] == "generated" and created["translation"]["generated_at"]
    assert created["warnings"] == [] and created["message"] == "공연과 영어 번역이 등록되었습니다."
    detail = client.get(f"/api/events/{created['id']}").json()
    assert detail["title_en"] == "Saturday Indie Live"
    assert detail["drink_policy_en"] == SOURCE_EN["drink_policy_en"]
    assert detail["description_ko"] == "어쿠스틱 중심의 소규모 공연입니다."  # 원문은 덮어쓰지 않음
    sent = gemini.requests[0]["contents"][0]["parts"][0]["text"]
    assert "토요일 인디 라이브" in sent and "선착순" in sent  # 최종 원문으로 번역
    assert gemini.requests[0]["generationConfig"]["responseJsonSchema"]["required"] == [
        "title_en", "description_en", "admission_notes_en", "drink_policy_en"]


def test_register_with_null_optional_texts(client, gemini):
    gemini.add(text({"title_en": "Title only", "description_en": None, "admission_notes_en": None,
                     "drink_policy_en": None}))
    res = client.post("/api/events", json=_event_body(drink_policy="   ", description_ko=None,
                                                      admission_notes_ko=""))
    assert res.status_code == 201 and res.json()["translation"]["status"] == "generated"
    detail = client.get(f"/api/events/{res.json()['id']}").json()
    assert detail["drink_policy"] is None and detail["drink_policy_en"] is None  # 공백뿐 → null


def test_register_translation_failure_still_registers(client, gemini):
    gemini.add(503, text({"title_en": ""}))  # 1차 실패, 재시도는 검증 실패
    res = client.post("/api/events", json=_event_body())
    assert res.status_code == 201
    body = res.json()
    assert body["translation"] == {"status": "failed", "generated_at": None}
    assert body["warnings"] == ["공연은 등록되었으나 영어 번역을 생성하지 못했습니다."]
    assert len(gemini.requests) == 2  # 재시도 최대 1회
    detail = client.get(f"/api/events/{body['id']}").json()
    assert detail["translation"]["status"] == "failed" and detail["title_en"] is None


def test_register_translation_respects_time_budget(client, gemini, monkeypatch):
    monkeypatch.setenv("LLM_TRANSLATE_TIMEOUT_S", "0.5")
    res = client.post("/api/events", json=_event_body())
    assert res.status_code == 201 and res.json()["translation"]["status"] == "failed"
    assert gemini.requests == []  # 한도가 너무 짧으면 호출하지 않음


# ---------- 번역 재시도 ----------
def _failed_event(client, gemini) -> int:
    gemini.add(503, 503)
    return client.post("/api/events", json=_event_body()).json()["id"]


def test_retry_translation_success(client, gemini):
    event_id = _failed_event(client, gemini)
    gemini.add(text(SOURCE_EN))
    res = client.post(f"/api/events/{event_id}/translate")
    assert res.status_code == 200
    assert res.json()["id"] == event_id and res.json()["translation"]["status"] == "generated"
    assert client.get(f"/api/events/{event_id}").json()["title_en"] == "Saturday Indie Live"
    again = client.post(f"/api/events/{event_id}/translate")  # 같은 원문 → 모델 호출 없이 재사용
    assert again.status_code == 200 and len(gemini.requests) == 3
    assert client.get("/api/events", params={"date": "2026-11-07", "limit": 50}).json()["total"] == 9  # 재등록 없음


def test_retry_translation_failure_is_503_with_details(client, gemini):
    event_id = _failed_event(client, gemini)
    gemini.add(503, 503)
    res = client.post(f"/api/events/{event_id}/translate")
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert res.json()["error"]["details"] == {"event_id": event_id,
                                              "translation": {"status": "failed", "generated_at": None}}


def test_retry_translation_source_changed_is_409(client, gemini, db):
    event_id = _failed_event(client, gemini)

    def change_source(_body):
        db.execute("UPDATE events SET title = '바뀐 제목' WHERE id = ?", (event_id,))
        db.commit()
        return text(SOURCE_EN)

    gemini.add(change_source)
    res = client.post(f"/api/events/{event_id}/translate")
    assert res.status_code == 409 and res.json()["error"]["code"] == "TRANSLATION_SOURCE_CHANGED"
    assert client.get(f"/api/events/{event_id}").json()["title_en"] is None


def test_retry_translation_404_and_admin_only(client, remote_client, db):
    assert client.post("/api/events/99999/translate").status_code == 404
    draft = db.execute("SELECT id FROM events WHERE status = 'draft'").fetchone()["id"]
    assert client.post(f"/api/events/{draft}/translate").status_code == 404
    assert remote_client.post("/api/events/1/translate").status_code == 403


# ---------- 포스터 Vision ----------
def test_poster_vision_call(client, gemini):
    gemini.add(text({"title": "토요일 인디 라이브", "starts_at_local": "2026-11-07T20:00:00",
                     "doors_open_at_local": None, "venue_name": "샘플 라이브 클럽", "price_krw": 18000,
                     "advance_price_krw": 18000, "door_price_krw": 22000, "lineup": ["Sample Band A"],
                     "genre": None}))
    res = client.post("/api/posters/parse", files={"file": ("p.png", PNG, "image/png")})
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["venue_match"]["status"] == "matched" and body["needs_review"] == ["doors_open_at_local"]
    request = gemini.requests[0]
    image = request["contents"][0]["parts"][0]["inlineData"]
    assert image["mimeType"] == "image/png" and base64.b64decode(image["data"]) == PNG
    assert "Never guess" in request["systemInstruction"]["parts"][0]["text"]
    assert request["generationConfig"]["responseJsonSchema"]["properties"]["venue_name"]


def test_poster_vision_failure_is_503(client, gemini):
    gemini.add(503, 503, 503)  # 일시 장애 재시도(2회) 후에도 실패
    res = client.post("/api/posters/parse", files={"file": ("p.png", PNG, "image/png")})
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert len(gemini.requests) == 3 and not gemini.script


def test_poster_vision_recovers_from_transient_503(client, gemini):
    gemini.add(503, text({"title": "토요일 인디 라이브", "starts_at_local": None, "doors_open_at_local": None,
                          "venue_name": None, "price_krw": None, "advance_price_krw": None,
                          "door_price_krw": None, "lineup": [], "genre": None}))
    res = client.post("/api/posters/parse", files={"file": ("p.png", PNG, "image/png")})
    assert res.status_code == 200 and res.json()["extracted"]["title"] == "토요일 인디 라이브"


def test_poster_vision_bad_json_is_503(client, gemini):
    gemini.add(text("not json at all"))
    assert client.post("/api/posters/parse", files={"file": ("p.png", PNG, "image/png")}).status_code == 503
