"""3단계: POST /api/recommend — AI 도구 호출 검색·추천(가짜 Gemini) + 필터만 경로 + EventQuery 조건식."""
from __future__ import annotations

import json

import pytest

from conftest import fc, function_responses

DAY = [
    {"field": "starts_at", "op": "gte", "value": "2026-11-07T00:00:00+09:00"},
    {"field": "starts_at", "op": "lt", "value": "2026-11-08T00:00:00+09:00"},
]
DOC_REQUIRED = {"all": [*DAY,
                        {"field": "area", "op": "eq", "value": "sinchon"},
                        {"field": "price_krw", "op": "lte", "value": 20000},
                        {"field": "seating_type", "op": "eq", "value": "seated"}]}
DOC_QUERY = "11월 7일 신촌에서 혼자 볼 만한 2만 원 이하 잔잔한 좌석 공연만 추천해 줘"
NO_FILTERS = {"date": None, "area": None, "max_price_krw": None, "mood_tags": [], "solo_friendly": None,
              "seating_preference": None, "seating_requirement": None}


@pytest.fixture()
def eid(db):
    def _eid(title):
        return db.execute("SELECT id FROM events WHERE title = ?", (title,)).fetchone()["id"]
    return _eid


def _post(client, query="", filters=None, locale="ko"):
    return client.post("/api/recommend", json={"query": query, "filters": {**NO_FILTERS, **(filters or {})},
                                               "locale": locale})


def _search(required=None, **kw):
    args = dict(kw)
    if required is not None:
        args["required_conditions"] = json.dumps(required, ensure_ascii=False)
    return fc("search_events", args)


def _submit(items=(), status="ok", **kw):
    return fc("submit_recommendations", {"status": status, "items": list(items), **kw})


# ---------- AI 정상 흐름 ----------
def test_ai_searches_then_recommends_with_verified_evidence(client, gemini, eid):
    walk = eid("밤의 산책")
    gemini.add(
        _search(DOC_REQUIRED),
        _submit([{"event_id": walk, "reason": "신촌에서 예매가 15,000원인 차분한 좌석 공연이라 요청에 어울릴 수 있어요.",
                  "evidence": [{"field": "seating_type", "value": "seated"},
                               {"field": "mood_tags", "value": "calm"},
                               {"field": "price_krw", "value": "15000"}]}],
                preferences=["혼자 관람하기 좋은 공연", "잔잔한 분위기"]),
    )
    res = _post(client, DOC_QUERY)
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["status"] == "ok" and body["clarification"] is None
    assert [i["event"]["title"] for i in body["items"]] == ["밤의 산책"]
    item = body["items"][0]
    assert item["reason"].startswith("신촌에서 예매가 15,000원인") and "score" not in item
    assert item["matched_tags"] == ["calm"]  # 근거로 검증된 태그
    assert item["event"]["title_en"] == "Night Walk" and item["event"]["translation"]["status"] == "reviewed"
    assert body["applied_conditions"] == DOC_REQUIRED
    assert body["applied_filters"] == {**NO_FILTERS, "date": "2026-11-07", "area": "sinchon",
                                       "max_price_krw": 20000, "seating_requirement": "seated"}
    assert body["total_matches"] == 2  # 밤의 산책·어쿠스틱 선데이 (새벽 네온 mixed, 모노 포크 가격 미확인 제외)
    assert body["preferences"] == ["혼자 관람하기 좋은 공연", "잔잔한 분위기"]
    assert body["search_limited"] is False and body["used_fallback"] is False
    assert body["notice"] == "예매 가능 여부는 예매처에서 확인해 주세요."

    # 모델에 전달한 요청: 원문 그대로, 도구 선언, 함수 호출 강제, 조회 결과 반환
    first = gemini.requests[0]
    assert json.loads(first["contents"][0]["parts"][0]["text"])["query"] == DOC_QUERY
    names = [d["name"] for d in first["tools"][0]["functionDeclarations"]]
    assert names == ["search_events", "get_event_details", "submit_recommendations"]
    assert first["toolConfig"] == {"functionCallingConfig": {"mode": "ANY"}}
    assert gemini.urls[0].endswith("/models/gemini-3.5-flash:generateContent")
    assert gemini.headers[0]["x-goog-api-key"] == "test-key"
    result = function_responses(gemini.requests[1])[0]["response"]
    assert {i["title"] for i in result["items"]} == {"밤의 산책", "어쿠스틱 선데이"}
    assert result["total_matches"] == 2
    assert gemini.requests[1]["contents"][1]["parts"][0]["thoughtSignature"] == "sig"  # 모델 턴 보존


def test_ui_required_filters_always_apply(client, gemini):
    gemini.add(_search({"all": []}), _submit())
    body = _post(client, "아무 공연이나", {"area": "hongdae", "date": "2026-11-07"}).json()
    rows = function_responses(gemini.requests[1])[0]["response"]["items"]
    assert rows and all(r["area"] == "hongdae" and r["starts_at"].startswith("2026-11-07") for r in rows)
    assert body["applied_conditions"] == {"all": [*DAY, {"field": "area", "op": "eq", "value": "hongdae"}]}
    assert body["notice"] == "조건에 맞는 공연은 있지만 요청에 맞는 추천을 고르지 못했어요."


def test_conflict_with_ui_filter_is_returned_to_the_model(client, gemini):
    gemini.add(
        _search({"all": [{"field": "area", "op": "eq", "value": "sinchon"}]}),
        _search({"all": []}),
        _submit(),
    )
    _post(client, "신촌 공연", {"area": "hongdae"})
    error = function_responses(gemini.requests[1])[0]["response"]["error"]
    assert "contradicts the user's explicit UI filter" in error
    assert "items" in function_responses(gemini.requests[2])[0]["response"]


def test_required_conditions_are_locked_after_first_search(client, gemini):
    gemini.add(
        _search({"all": [{"field": "area", "op": "eq", "value": "sinchon"}]}),
        _search({"all": []}),  # 필수 조건 완화 시도
        _search(where=json.dumps({"field": "mood_tags", "op": "contains", "value": "calm"})),
        _submit(),
    )
    body = _post(client, "신촌만").json()
    assert "fixed after the first search" in function_responses(gemini.requests[2])[0]["response"]["error"]
    third = function_responses(gemini.requests[3])[0]["response"]
    assert third["items"] and all(r["area"] == "sinchon" and "calm" in r["mood_tags"] for r in third["items"])
    assert body["applied_conditions"] == {"all": [{"field": "area", "op": "eq", "value": "sinchon"}]}


def test_unseen_or_invalid_picks_get_one_correction_then_dropped(client, gemini, eid):
    walk, draft = eid("밤의 산책"), eid("준비 중 공연")
    good = {"event_id": walk, "reason": "좌석 공연이에요.", "evidence": [{"field": "seating_type", "value": "seated"}]}
    gemini.add(
        _search({"all": [*DAY, {"field": "area", "op": "eq", "value": "sinchon"}]}),
        _submit([{"event_id": 99999, "reason": "없는 공연", "evidence": [{"field": "title", "value": "x"}]}, good]),
        _submit([{"event_id": draft, "reason": "초안", "evidence": [{"field": "title", "value": "준비 중 공연"}]},
                 good]),
    )
    body = _post(client, "11월 7일 신촌").json()
    correction = function_responses(gemini.requests[2])[0]["response"]
    assert "failed server verification" in correction["error"] and "was not returned" in correction["problems"][0]
    assert [i["event"]["id"] for i in body["items"]] == [walk]  # 두 번째 제출에서 무효 항목은 제외
    assert "확인되지 않는 공연은 제외" in body["notice"]


def test_fabricated_evidence_is_rejected(client, gemini, eid):
    walk = eid("밤의 산책")
    fake = {"event_id": walk, "reason": "만 원짜리 공연", "evidence": [{"field": "price_krw", "value": "10000"}]}
    gemini.add(_search({"all": DAY}), _submit([fake]), _submit([fake]))
    body = _post(client, "11월 7일 싼 공연").json()
    assert body["items"] == []
    assert "does not match the stored data" in function_responses(gemini.requests[2])[0]["response"]["problems"][0]


def test_unsafe_ai_reason_is_replaced_by_fact_template(client, gemini, eid):
    walk = eid("밤의 산책")
    gemini.add(_search({"all": [*DAY, {"field": "area", "op": "eq", "value": "sinchon"}]}),
               _submit([{"event_id": walk, "reason": "지금 예매 가능한 인기 1위 공연!",
                         "evidence": [{"field": "area", "value": "신촌"}]}]))
    body = _post(client, "신촌 인기 공연").json()
    assert body["items"][0]["reason"].startswith("신촌 공연이며 예매가 15,000원으로 안내")
    assert body["used_fallback"] is True


def test_clarification_before_search(client, gemini):
    gemini.add(_submit(status="needs_clarification", clarification="'2만 원 정도'는 2만 원 이하로 볼까요?"))
    body = _post(client, "2만 원 정도인 공연").json()
    assert body["status"] == "needs_clarification" and body["items"] == []
    assert body["clarification"] == "'2만 원 정도'는 2만 원 이하로 볼까요?"
    assert body["applied_conditions"] is None and body["total_matches"] is None
    assert body["search_limited"] is False


def test_recommend_before_search_is_refused(client, gemini, eid):
    gemini.add(_submit([{"event_id": eid("밤의 산책"), "reason": "x", "evidence": [{"field": "area", "value": "신촌"}]}]),
               _search({"all": []}), _submit())
    _post(client, "아무거나")
    assert "call search_events before recommending" in function_responses(gemini.requests[1])[0]["response"]["error"]


def test_tool_call_limit_forces_final_answer(client, gemini):
    gemini.add(_search({"all": []}, limit=1), *[_search(limit=1) for _ in range(6)], _submit())
    body = _post(client, "계속 찾아줘").json()
    assert body["status"] == "ok" and body["search_limited"] is True
    forced = gemini.requests[-1]["toolConfig"]["functionCallingConfig"]
    assert forced == {"mode": "ANY", "allowedFunctionNames": ["submit_recommendations"]}
    assert "tool call limit reached" in function_responses(gemini.requests[-1])[0]["response"]["error"]
    assert "모든 후보를 살펴보기 전에" in body["notice"]


def test_pagination_cursor_and_keywords(client, gemini):
    def second_page(body):
        cursor = function_responses(body)[0]["response"]["next_cursor"]
        assert cursor
        return _search(cursor=cursor, limit=2)

    gemini.add(_search({"all": []}, limit=2), second_page,
               _search(cursor="bogus", where=json.dumps({"field": "genre", "op": "eq", "value": "jazz"})),
               _search(keywords=["Folk Sample"]), _submit())
    _post(client, "공연")
    page1 = function_responses(gemini.requests[1])[0]["response"]
    page2 = function_responses(gemini.requests[2])[0]["response"]
    assert page1["total"] == 20 and len(page1["items"]) == 2
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})
    both = [i["starts_at"] for i in page1["items"] + page2["items"]]
    assert both == sorted(both)
    assert "cursor does not belong" in function_responses(gemini.requests[3])[0]["response"]["error"]
    found = function_responses(gemini.requests[4])[0]["response"]["items"]
    assert [i["title"] for i in found] == ["모노 포크 나잇"]  # 출연진 키워드


def test_search_never_returns_past_draft_or_cancelled(client, gemini):
    gemini.add(_search({"all": []}, limit=50), _submit())
    _post(client, "전부")
    titles = {i["title"] for i in function_responses(gemini.requests[1])[0]["response"]["items"]}
    assert len(titles) == 20 and not titles & {"지난 공연", "준비 중 공연", "취소된 공연"}


def test_event_details_only_for_seen_ids(client, gemini, eid):
    walk, rock = eid("밤의 산책"), eid("홍대 록 파티")
    gemini.add(_search({"all": [*DAY, {"field": "area", "op": "eq", "value": "sinchon"}]}),
               fc("get_event_details", {"event_ids": [walk, rock]}), _submit())
    _post(client, "신촌")
    events = function_responses(gemini.requests[2])[0]["response"]["events"]
    assert events[0]["admission_notes_ko"].startswith("좌석은 비지정석") and events[0]["venue"]["floor"] == "B1"
    assert events[1] == {"id": rock, "error": "not returned by search_events in this request"}


def test_same_bad_call_twice_stops_exploration(client, gemini):
    bad = _search({"field": "nope", "op": "eq", "value": 1})
    gemini.add(bad, bad, _submit(status="needs_clarification", clarification="어떤 공연을 원하세요?"))
    body = _post(client, "이상한 요청").json()
    assert gemini.requests[2]["toolConfig"]["functionCallingConfig"]["allowedFunctionNames"] == [
        "submit_recommendations"]
    assert body["status"] == "needs_clarification"


# ---------- AI 장애: 수동 필터가 있어도 자동 대체하지 않음 (API.md §6) ----------
@pytest.mark.parametrize("failure", [503, 429, 500])
def test_ai_http_failure_is_503_even_with_filters(client, gemini, failure):
    gemini.add(failure, failure, failure)  # 일시 장애 재시도(2회) 후에도 계속 실패
    res = _post(client, "홍대 공연", {"area": "hongdae"})
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert "test-key" not in res.text
    assert len(gemini.requests) == 3


def test_ai_transient_failure_is_retried_within_budget(client, gemini):
    gemini.add(503, _search({"all": []}), 429, _submit())
    res = _post(client, "홍대 공연", {"area": "hongdae"})
    assert res.status_code == 200, res.json()
    assert res.json()["status"] == "ok" and len(gemini.requests) == 4
    # 재시도한 요청 본문은 원래 요청과 같다 (대화 이력이 중복 추가되지 않음)
    assert gemini.requests[0] == gemini.requests[1] and gemini.requests[2] == gemini.requests[3]


def test_ai_bad_request_is_not_retried(client, gemini):
    gemini.add(400)
    assert _post(client, "홍대 공연").status_code == 503 and len(gemini.requests) == 1


def test_ai_timeout_is_503(client, gemini):
    import httpx

    gemini.add(httpx.ReadTimeout("slow"))
    assert _post(client, "공연").status_code == 503


def test_ai_not_configured_is_503(client):
    res = _post(client, "아무 공연이나 추천해 줘", {"area": "sinchon"})
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"


def test_model_text_instead_of_function_is_nudged(client, gemini):
    from conftest import text

    gemini.add(text("hello"), _search({"all": []}), _submit())
    assert _post(client, "공연").status_code == 200
    assert "calling one of the functions" in gemini.requests[1]["contents"][-1]["parts"][0]["text"]


# ---------- 필터만 (AI 없음) ----------
def test_filters_only_does_not_call_ai(client, gemini):
    data = _post(client, "   ", {"area": "hongdae"}).json()
    assert gemini.requests == [] and len(data["items"]) == 3
    assert data["used_fallback"] is True and "AI 추천 순위는 적용되지 않았어요" in data["notice"]
    assert data["search_limited"] is True and data["total_matches"] > 3
    assert data["applied_conditions"] == {"all": [{"field": "area", "op": "eq", "value": "hongdae"}]}
    assert data["status"] == "ok" and all("score" not in i for i in data["items"])


def test_filters_only_doc_example(client):
    body = _post(client, filters={"date": "2026-11-07", "area": "sinchon", "max_price_krw": 20000,
                                  "mood_tags": ["calm"], "solo_friendly": True,
                                  "seating_requirement": "seated"}).json()
    assert body["total_matches"] == 2 and body["items"][0]["event"]["title"] == "밤의 산책"
    assert body["items"][0]["reason"].startswith("신촌 공연이며 예매가 15,000원으로 안내되어 있고")
    assert body["preferences"] == ["차분한 분위기", "혼자 관람하기 좋은 공연"]


def test_filters_only_seating_requirement_and_budget(client):
    seated = _post(client, filters={"seating_requirement": "seated"}).json()
    assert {i["event"]["seating_type"] for i in seated["items"]} == {"seated"} and seated["total_matches"] == 10
    free = _post(client, filters={"max_price_krw": 0}).json()
    assert {i["event"]["title"] for i in free["items"]} == {"라운지 언플러그드", "신인 밴드 경연"}
    conflict = _post(client, filters={"seating_requirement": "seated", "seating_preference": "standing"}).json()
    assert conflict["applied_filters"]["seating_preference"] is None and "충돌" in conflict["notice"]


def test_filters_only_english(client):
    data = _post(client, filters={"date": "2026-11-07", "area": "sinchon", "max_price_krw": 20000,
                                  "mood_tags": ["calm"], "seating_requirement": "seated"}, locale="en").json()
    assert data["items"][0]["reason"] == (
        "A Sinchon show listed at ₩15,000 (advance), with confirmed calm mood, seated viewing.")
    assert data["preferences"] == ["Calm mood"]


# ---------- 입력 검증 ----------
@pytest.mark.parametrize(
    "payload",
    [
        {"query": "", "filters": {}},
        {"query": "   "},
        {"query": "x" * 501},
        {"filters": {"mood_tags": ["cozy"]}},
        {"filters": {"area": "gangnam"}},
        {"filters": {"max_price_krw": -1}},
        {"filters": {"date": "2026-13-40"}},
        {"filters": {"seating_requirement": "mixed"}},
        {"filters": {"area": "sinchon"}, "locale": "jp"},
        {"filters": {"area": "sinchon"}, "price_basis": "x"},
    ],
)
def test_validation(client, payload):
    res = client.post("/api/recommend", json=payload)
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------- EventQuery 조건식 ----------
@pytest.mark.parametrize(
    "node, message",
    [
        ({"field": "nope", "op": "eq", "value": 1}, "unknown field"),
        ({"field": "area", "op": "like", "value": "x"}, "unknown op"),
        ({"field": "area", "op": "eq", "value": "gangnam"}, "must be one of"),
        ({"field": "price_krw", "op": "lte", "value": True}, "integer"),
        ({"field": "price_krw", "op": "lte", "value": -1}, "integer"),
        ({"field": "starts_at", "op": "gte", "value": "2026-11-07T00:00:00"}, "timezone"),
        ({"field": "starts_at", "op": "eq", "value": "2026-11-07T00:00:00+09:00"}, "ranges only"),
        ({"field": "title", "op": "gte", "value": "a"}, "only for numbers"),
        ({"field": "lineup", "op": "eq", "value": "a"}, "is a list"),
        ({"field": "solo_friendly", "op": "in", "value": [True]}, "eq or is_null"),
        ({"field": "genre", "op": "is_null", "value": "yes"}, "true or false"),
        ({"any": []}, 'empty "any"'),
        ({"all": [], "any": [{}]}, "exactly one key"),
        ({"all": [{"all": [{"all": [{"all": [{"field": "area", "op": "eq", "value": "sinchon"}]}]}]}]},
         "nested too deeply"),
        ({"all": [{"field": "area", "op": "eq", "value": "sinchon"}] * 31}, "too many nodes"),
        ({"field": "title", "op": "in", "value": []}, "list of 1-50"),
    ],
)
def test_event_query_rejects(node, message):
    from services.intent import QueryError, compile_query

    with pytest.raises(QueryError, match=message):
        compile_query(node)


def test_event_query_values_are_bound_not_interpolated(client, gemini, db):
    gemini.add(_search({"all": []}, where=json.dumps(
        {"field": "title", "op": "contains", "value": "'; DROP TABLE events; --"})), _submit())
    _post(client, "x")
    assert function_responses(gemini.requests[1])[0]["response"]["total"] == 0
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 23
    from services.intent import compile_query

    sql, params = compile_query({"field": "title", "op": "contains", "value": "50%_off"})
    assert params == ["%50\\%\\_off%"] and "ESCAPE" in sql  # LIKE 와일드카드는 리터럴
