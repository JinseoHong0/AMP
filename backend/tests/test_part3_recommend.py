"""3단계: POST /api/recommend — LLM 직접 추천 + 서버 검증, AI 장애 시 규칙 기반 복구.

AI 연결은 공란이므로 LLM 응답이 필요한 경우 테스트에서 services.intent.call_llm_recommend 를 가짜로 바꿔 끼운다.
"""
from __future__ import annotations

import pytest

from services import intent

DOC_FILTERS = {
    "date_expression": "2026-11-07",
    "area": "sinchon",
    "max_price_krw": 20000,
    "mood_tags": ["calm"],
    "solo_friendly": True,
    "seating_preference": None,
    "seating_requirement": "seated",
}
DOC_QUERY = "11월 7일 신촌에서 혼자 볼 만한 2만 원 이하 잔잔한 좌석 공연만 추천해 줘"


@pytest.fixture()
def eid(db):
    def _eid(title):
        return db.execute("SELECT id FROM events WHERE title = ?", (title,)).fetchone()["id"]
    return _eid


@pytest.fixture()
def fake_llm(monkeypatch):
    """state['responses']: 호출마다 순서대로 반환(마지막 값 반복). 예외 객체면 raise."""
    state = {"responses": [], "calls": []}

    def _fake(query, candidates, today_kst, locale):
        state["calls"].append({"query": query, "candidates": candidates, "today": today_kst, "locale": locale})
        responses = state["responses"]
        value = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(intent, "call_llm_recommend", _fake)
    return state


def _post(client, query="", filters=None, locale="ko"):
    return client.post("/api/recommend", json={"query": query, "filters": filters or {}, "locale": locale})


def _resp(filters=None, items=()):
    return {"applied_filters": filters or {}, "items": [{"event_id": i, "reason": r} for i, r in items]}


# ---------- LLM 직접 추천 ----------
def test_llm_recommends_directly(client, fake_llm, eid):
    walk = eid("밤의 산책")
    fake_llm["responses"] = [_resp(DOC_FILTERS, [(walk, "신촌에서 예매가 15,000원인 차분한 좌석 공연이에요.")])]
    res = _post(client, DOC_QUERY)
    assert res.status_code == 200
    body = res.json()
    assert len(fake_llm["calls"]) == 1 and fake_llm["calls"][0]["query"] == DOC_QUERY
    assert body["applied_filters"] == {**{k: v for k, v in DOC_FILTERS.items() if k != "date_expression"},
                                       "date": "2026-11-07"}
    assert [i["event"]["title"] for i in body["items"]] == ["밤의 산책"]
    item = body["items"][0]
    assert item["reason"] == "신촌에서 예매가 15,000원인 차분한 좌석 공연이에요."  # LLM 문장 사용
    assert item["matched_tags"] == ["calm"] and "score" not in item  # 고정 점수 미노출 (API.md §6)
    assert body["total_matches"] == 2  # 하드 조건 통과: 밤의 산책, 어쿠스틱 선데이
    assert body["used_fallback"] is False
    assert body["notice"] == "예매 가능 여부는 예매처에서 확인해 주세요."
    # API.md §6 응답 필드
    assert body["status"] == "ok" and body["clarification"] is None and body["search_limited"] is False
    assert body["applied_conditions"] == {"all": [
        {"field": "starts_at", "op": "gte", "value": "2026-11-07T00:00:00+09:00"},
        {"field": "starts_at", "op": "lt", "value": "2026-11-08T00:00:00+09:00"},
        {"field": "area", "op": "eq", "value": "sinchon"},
        {"field": "price_krw", "op": "lte", "value": 20000},
        {"field": "seating_type", "op": "eq", "value": "seated"},
    ]}
    assert body["preferences"] == ["차분한 분위기", "혼자 관람하기 좋은 공연"]


def test_llm_order_is_kept(client, fake_llm, eid):
    a, b, c = eid("어쿠스틱 선데이"), eid("밤의 산책"), eid("새벽 네온")
    fake_llm["responses"] = [_resp({"area": "sinchon"}, [(a, "이유 A"), (b, "이유 B"), (c, "이유 C")])]
    titles = [i["event"]["title"] for i in _post(client, "신촌 공연").json()["items"]]
    assert titles == ["어쿠스틱 선데이", "밤의 산책", "새벽 네온"]


def test_candidates_are_db_facts_only(client, fake_llm, eid):
    fake_llm["responses"] = [_resp()]
    _post(client, "아무 공연")
    call = fake_llm["calls"][0]
    titles = {c["title"] for c in call["candidates"]}
    assert len(titles) == 20 and not titles & {"지난 공연", "준비 중 공연", "취소된 공연"}
    walk = next(c for c in call["candidates"] if c["title"] == "밤의 산책")
    assert walk["starts_at_kst"] == "2026-11-07T19:00" and walk["doors_open_at_kst"] == "2026-11-07T18:30"
    assert walk["price_krw"] == 15000 and walk["price_basis"] == "advance" and walk["area"] == "sinchon"
    assert call["today"] == "2026-11-06" and call["locale"] == "ko"


def test_ui_filters_prefilter_candidates_and_override(client, fake_llm, eid):
    rock = eid("홍대 록 파티")
    fake_llm["responses"] = [_resp({"area": "hongdae", "mood_tags": ["energetic"]}, [(rock, "신나는 록 공연")])]
    body = _post(client, "홍대 신나는 공연", {"area": "sinchon"}).json()
    assert {c["area"] for c in fake_llm["calls"][0]["candidates"]} == {"sinchon"}
    assert body["applied_filters"]["area"] == "sinchon"  # UI 우선
    assert body["items"] == []  # 홍대 공연은 UI 조건 위반 → 제거
    assert "제외" in body["notice"]


@pytest.mark.parametrize("title_or_id", [9999, "준비 중 공연", "취소된 공연", "지난 공연"])
def test_unknown_or_unpublished_ids_removed(client, fake_llm, eid, title_or_id):
    bad = title_or_id if isinstance(title_or_id, int) else eid(title_or_id)
    good = eid("밤의 산책")
    fake_llm["responses"] = [_resp({}, [(bad, "없는 공연"), (good, "좋은 공연")])]
    body = _post(client, "공연 추천").json()
    assert [i["event"]["id"] for i in body["items"]] == [good]
    assert "제외" in body["notice"]


def test_llm_pick_violating_its_own_hard_filters_removed(client, fake_llm, eid):
    rock, jazz, free = eid("홍대 록 파티"), eid("블루 재즈 데이트"), eid("라운지 언플러그드")
    filters = {"date_expression": "2026-11-07", "area": "hongdae", "max_price_krw": 20000,
               "seating_requirement": "seated"}
    fake_llm["responses"] = [_resp(filters, [(rock, "록"), (free, "무료"), (jazz, "재즈")])]
    body = _post(client, "11월 7일 홍대 2만원 이하 좌석만").json()
    # 록 파티: 현장 25,000 예산 초과 / 라운지: 이벤트 좌석 정보 null → 좌석 필수 불충족
    assert [i["event"]["title"] for i in body["items"]] == ["블루 재즈 데이트"]
    assert body["total_matches"] == 1


def test_max_three_and_duplicates(client, fake_llm, eid):
    ids = [eid(t) for t in ("밤의 산책", "밤의 산책", "새벽 네온", "겨울 노래", "피아노 라이브")]
    fake_llm["responses"] = [_resp({}, [(i, "이유") for i in ids])]
    body = _post(client, "공연").json()
    assert [i["event"]["title"] for i in body["items"]] == ["밤의 산책", "새벽 네온", "겨울 노래"]


def test_llm_empty_items_is_200_empty(client, fake_llm):
    fake_llm["responses"] = [_resp({"area": "sinchon"}, [])]
    body = _post(client, "조건에 맞는 게 없을 질의").json()
    assert body["items"] == [] and body["notice"] == "조건에 맞는 공연이 없습니다."


def test_no_candidates_skips_llm(client, fake_llm):
    fake_llm["responses"] = [_resp()]
    body = _post(client, "무료 좌석", {"date": "2026-11-07", "max_price_krw": 0, "seating_requirement": "seated"})
    assert body.status_code == 200 and body.json()["items"] == [] and body.json()["total_matches"] == 0
    assert fake_llm["calls"] == []


@pytest.mark.parametrize(
    "reason_text",
    ["지금 예매 가능한 인기 1위 공연!", "혼자 가기 완벽하고 안전한 곳", "좌석이 반드시 남아 있어요",
     "", None, 123, "x" * 301, "자세한 건 https://evil.example 참고"],
)
def test_unsafe_llm_reason_replaced_by_template(client, fake_llm, eid, reason_text):
    walk = eid("밤의 산책")
    fake_llm["responses"] = [{"applied_filters": DOC_FILTERS, "items": [{"event_id": walk, "reason": reason_text}]}]
    body = _post(client, DOC_QUERY).json()
    item = body["items"][0]
    assert item["reason"].startswith("신촌 공연이며 예매가 15,000원으로 안내되어 있고")
    assert body["used_fallback"] is True


def test_requirement_preference_conflict(client, fake_llm, eid):
    fake_llm["responses"] = [_resp({"seating_requirement": "seated", "seating_preference": "standing"},
                                   [(eid("밤의 산책"), "좌석 공연")])]
    body = _post(client, "좌석만, 근데 스탠딩이 좋아").json()
    assert body["applied_filters"]["seating_requirement"] == "seated"
    assert body["applied_filters"]["seating_preference"] is None
    assert "충돌" in body["notice"]


def test_invalid_llm_filters_dropped_with_notice(client, fake_llm):
    fake_llm["responses"] = [_resp({"area": "gangnam", "date_expression": "this_week",
                                    "mood_tags": ["calm", "cozy"], "max_price_krw": -5,
                                    "seating_requirement": "vip"})]
    body = _post(client, "이번 주 강남 공연").json()
    f = body["applied_filters"]
    assert f["area"] is None and f["date"] is None and f["max_price_krw"] is None
    assert f["mood_tags"] == ["calm"] and f["seating_requirement"] is None
    assert "신촌·홍대" in body["notice"] and "날짜" in body["notice"]


def test_today_resolved_in_kst(client, fake_llm, eid):
    fake_llm["responses"] = [_resp({"date_expression": "today"}, [(eid("오늘의 무대"), "오늘 공연")])]
    body = _post(client, "오늘 공연").json()
    assert body["applied_filters"]["date"] == "2026-11-06"
    assert [i["event"]["title"] for i in body["items"]] == ["오늘의 무대"]


def test_bad_item_entries_ignored(client, fake_llm, eid):
    walk = eid("밤의 산책")
    fake_llm["responses"] = [{"applied_filters": {}, "items": ["x", {"event_id": "1"}, {"event_id": True},
                                                               {"event_id": walk, "reason": "좋은 공연"}]}]
    body = _post(client, "공연").json()
    assert [i["event"]["id"] for i in body["items"]] == [walk]


# ---------- LLM 장애/형식 오류 ----------
def test_malformed_response_retried_once(client, fake_llm, eid):
    fake_llm["responses"] = ["not-json", _resp({}, [(eid("밤의 산책"), "좋은 공연")])]
    res = _post(client, "공연")
    assert res.status_code == 200 and len(res.json()["items"]) == 1
    assert len(fake_llm["calls"]) == 2


def test_malformed_twice_without_filters_is_503(client, fake_llm):
    fake_llm["responses"] = [{"items": "nope"}]
    res = _post(client, "공연")
    assert res.status_code == 503 and len(fake_llm["calls"]) == 2  # 무한 재시도 금지


def test_llm_exception_with_filters_falls_back_without_leak(client, fake_llm):
    fake_llm["responses"] = [RuntimeError("secret-key-sk-123")]
    res = _post(client, "신촌 공연", {"area": "sinchon"})
    assert res.status_code == 200 and "secret" not in res.text
    assert res.json()["used_fallback"] is True


# ---------- AI 미연결(현재 기본 상태) → 규칙 기반 복구 ----------
def test_ai_blank_with_filters_falls_back(client):
    data = _post(client, "신촌 좌석 공연", {"area": "sinchon", "seating_requirement": "seated"}).json()
    assert data["used_fallback"] is True and "필터로만" in data["notice"]
    assert all(i["event"]["venue"]["area"] == "sinchon" for i in data["items"])
    assert all(i["event"]["seating_type"] == "seated" for i in data["items"])


def test_ai_blank_without_filters_is_503(client):
    res = _post(client, "아무 공연이나 추천해 줘")
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"


def test_filters_only_does_not_call_llm(client, fake_llm):
    fake_llm["responses"] = [_resp()]
    data = _post(client, "   ", {"area": "hongdae"}).json()
    assert fake_llm["calls"] == [] and len(data["items"]) == 3
    # 검색어 없이 필터만: used_fallback=true + AI 순위 미적용 안내, 표시보다 후보가 많으면 search_limited
    assert data["used_fallback"] is True and "AI 추천 순위는 적용되지 않았어요" in data["notice"]
    assert data["search_limited"] is True and data["total_matches"] > 3
    assert data["applied_conditions"] == {"all": [{"field": "area", "op": "eq", "value": "hongdae"}]}
    assert data["preferences"] == [] and data["status"] == "ok"


# ---------- 규칙 기반 경로 (필터만 / AI 장애) ----------
def test_rule_doc_example_score(client):
    body = _post(client, filters={"date": "2026-11-07", "area": "sinchon", "max_price_krw": 20000,
                                  "mood_tags": ["calm"], "solo_friendly": True,
                                  "seating_requirement": "seated"}).json()
    assert body["total_matches"] == 2
    first = body["items"][0]
    assert first["event"]["title"] == "밤의 산책" and first["matched_tags"] == ["calm"]
    assert all("score" not in i for i in body["items"])
    assert body["search_limited"] is False  # 후보 2개 모두 표시
    assert first["reason"].startswith("신촌 공연이며 예매가 15,000원으로 안내되어 있고")


def test_rule_seating_preference_is_soft(client):
    body = _post(client, filters={"date": "2026-11-07", "area": "hongdae", "max_price_krw": 20000,
                                  "seating_preference": "seated"}).json()
    # 좌석 선호는 순서만 바꾼다(좌석 공연이 먼저), 스탠딩·미확인 공연도 남는다
    assert [i["event"]["title"] for i in body["items"]] == ["블루 재즈 데이트", "라운지 언플러그드", "인디 쇼케이스"]
    assert body["preferences"] == ["좌석 관람 선호"]


def test_rule_seating_requirement_excludes_null_mixed_standing(client):
    body = _post(client, filters={"seating_requirement": "seated"}).json()
    assert {i["event"]["seating_type"] for i in body["items"]} == {"seated"}
    assert body["total_matches"] == 10


def test_rule_budget_unknown_excluded_zero_free(client):
    body = _post(client, filters={"max_price_krw": 0}).json()
    assert {i["event"]["title"] for i in body["items"]} == {"라운지 언플러그드", "신인 밴드 경연"}
    assert "무료로 안내" in body["items"][0]["reason"]
    body = _post(client, filters={"date": "2026-11-07", "max_price_krw": 100000}).json()
    assert body["total_matches"] == 7


def test_rule_advance_price_counts_for_budget(client):
    body = _post(client, filters={"date": "2026-11-07", "area": "sinchon", "max_price_krw": 20000,
                                  "mood_tags": ["energetic"]}).json()
    first = body["items"][0]
    assert first["event"]["title"] == "새벽 네온" and first["event"]["price_basis"] == "advance"
    assert "예매가 20,000원" in first["reason"]


def test_rule_max_three_and_tiebreak(client):
    body = _post(client, filters={"mood_tags": ["calm", "acoustic"]}).json()
    assert len(body["items"]) == 3 and body["total_matches"] == 20
    # 두 태그가 모두 맞는 공연이 먼저, 동점이면 시작 시각 순
    assert body["items"][0]["matched_tags"] == ["calm", "acoustic"]
    tags = [len(i["matched_tags"]) for i in body["items"]]
    assert tags == sorted(tags, reverse=True)


def test_rule_past_draft_cancelled_never_recommended(client):
    body = _post(client, filters={"mood_tags": ["calm"], "max_price_krw": 10000}).json()
    assert not {i["event"]["title"] for i in body["items"]} & {"지난 공연", "준비 중 공연", "취소된 공연"}


def test_rule_reason_english(client):
    filters = {"date": "2026-11-07", "area": "sinchon", "mood_tags": ["calm"], "seating_requirement": "seated"}
    data = _post(client, filters=filters, locale="en").json()
    assert data["items"][0]["reason"] == (
        "A Sinchon show whose price is not confirmed, with confirmed calm mood, seated viewing."
    )
    data = _post(client, filters={**filters, "max_price_krw": 20000}, locale="en").json()
    assert data["items"][0]["reason"] == (
        "A Sinchon show listed at ₩15,000 (advance), with confirmed calm mood, seated viewing."
    )
    assert data["notice"] == ("Results for the selected filters only; AI recommendation ranking was not applied. "
                              "Please check ticket availability with the seller.")
    assert data["preferences"] == ["Calm mood"]


FORBIDDEN = ["예매 가능", "인기", "완벽", "안전", "반드시", "남아"]


def test_rule_reason_never_uses_forbidden_claims(client):
    for filters in ({"area": "sinchon", "solo_friendly": True, "mood_tags": ["calm"]},
                    {"area": "hongdae", "seating_preference": "standing"},
                    {"max_price_krw": 0}):
        for item in _post(client, filters=filters).json()["items"]:
            assert not any(w in item["reason"] for w in FORBIDDEN), item["reason"]


# ---------- 입력 검증 ----------
@pytest.mark.parametrize(
    "payload, status, code",
    [
        ({"query": "", "filters": {}}, 422, "VALIDATION_ERROR"),  # API.md §6: 둘 다 없으면 422
        ({"query": "   "}, 422, "VALIDATION_ERROR"),
        ({"query": "x" * 501}, 422, "VALIDATION_ERROR"),
        ({"filters": {"mood_tags": ["cozy"]}}, 422, "VALIDATION_ERROR"),
        ({"filters": {"area": "gangnam"}}, 422, "VALIDATION_ERROR"),
        ({"filters": {"max_price_krw": -1}}, 422, "VALIDATION_ERROR"),
        ({"filters": {"date": "2026-13-40"}}, 422, "VALIDATION_ERROR"),
        ({"filters": {"seating_requirement": "mixed"}}, 422, "VALIDATION_ERROR"),
        ({"filters": {"area": "sinchon"}, "locale": "jp"}, 422, "VALIDATION_ERROR"),
        ({"filters": {"area": "sinchon"}, "price_basis": "x"}, 422, "VALIDATION_ERROR"),
    ],
)
def test_validation(client, payload, status, code):
    res = client.post("/api/recommend", json=payload)
    assert res.status_code == status, res.json()
    assert res.json()["error"]["code"] == code


def test_malformed_json_common_error(client):
    res = client.post("/api/recommend", content=b"{bad json", headers={"Content-Type": "application/json"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------- 단위 ----------
def test_unit_parse_intent_payload():
    from services.intent import parse_intent_payload

    r = parse_intent_payload({"max_price_krw": True, "solo_friendly": "yes", "mood_tags": "calm"})
    assert r.intent.max_price_krw is None and r.intent.solo_friendly is None
    assert set(r.dropped) == {"max_price_krw", "solo_friendly", "mood_tags"}
    with pytest.raises(ValueError):
        parse_intent_payload(["x"])


def test_unit_check_llm_reason():
    from services.reason import check_llm_reason

    assert check_llm_reason("  차분한   좌석 공연이에요. ") == "차분한 좌석 공연이에요."
    assert check_llm_reason("Tickets still available!") is None
    assert check_llm_reason("A perfect night") is None
