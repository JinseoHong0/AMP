"""5단계: POST /api/translate — 한국어 홍보 문구 → 영어 번역 초안 (AI, 관리자 검수 전제)."""
from __future__ import annotations

import pytest

from services import reason

PROMO = "가을밤, 어쿠스틱 기타와 함께하는 작은 공연에 초대합니다."


@pytest.fixture()
def fake_translate(monkeypatch):
    state = {"result": "Join us for a small acoustic guitar show on an autumn night.", "calls": []}

    def _fake(text_ko, target_locale="en"):
        state["calls"].append((text_ko, target_locale))
        if isinstance(state["result"], Exception):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr(reason, "call_llm_translate", _fake)
    return state


def test_translate_returns_draft_without_saving(client, fake_translate, db):
    before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    res = client.post("/api/translate", json={"text_ko": f"  {PROMO}  "})
    assert res.status_code == 200
    body = res.json()
    assert body["text_en"] == fake_translate["result"]
    assert body["needs_review"] is True and "검수" in body["notice"]
    assert fake_translate["calls"] == [(PROMO, "en")]  # 앞뒤 공백 정리 후 전달
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before


def test_translate_then_save_reviewed_text(client, fake_translate):
    draft = client.post("/api/translate", json={"text_ko": PROMO}).json()["text_en"]
    reviewed = draft.replace("Join us", "You are invited")
    res = client.post("/api/events", json={
        "venue_id": 1, "title": "가을밤 어쿠스틱", "starts_at_local": "2026-11-08T19:00:00",
        "description_ko": PROMO, "description_en": reviewed, "review_confirmed": True,
    })
    assert res.status_code == 201
    detail = client.get(f"/api/events/{res.json()['id']}").json()
    assert detail["description_ko"] == PROMO and detail["description_en"] == reviewed


def test_translate_ai_blank_is_503(client):
    res = client.post("/api/translate", json={"text_ko": PROMO})
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "x" * 4001, RuntimeError("secret-key-sk-123")])
def test_translate_bad_ai_output_is_503(client, fake_translate, bad):
    fake_translate["result"] = bad
    res = client.post("/api/translate", json={"text_ko": PROMO})
    assert res.status_code == 503 and "secret" not in res.text


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"text_ko": ""}, "text_ko"),
        ({"text_ko": "   "}, "text_ko"),
        ({"text_ko": "가" * 2001}, "text_ko"),
        ({}, "text_ko"),
        ({"text_ko": PROMO, "target_locale": "ja"}, "target_locale"),
        ({"text_ko": PROMO, "extra": 1}, "extra"),
    ],
)
def test_translate_validation(client, payload, field):
    res = client.post("/api/translate", json=payload)
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == field


def test_translate_admin_only(remote_client, fake_translate):
    res = remote_client.post("/api/translate", json={"text_ko": PROMO})
    assert res.status_code == 403 and fake_translate["calls"] == []
