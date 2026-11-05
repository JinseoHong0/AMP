"""POST /api/recommend — 상황 맞춤 추천.

- 자연어 query 가 있으면: LLM 이 후보 중에서 **바로 추천** → 서버가 ID·하드 조건·이유 문장을 검증.
- AI 장애/미연결: 수동 필터가 있으면 규칙 기반(하드 필터 → 소프트 랭킹 → 템플릿 이유)으로 복구,
  필터도 없으면 503 AI_UNAVAILABLE.
- query 없이 필터만: 규칙 기반 (AI 불필요).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends

from database import get_db
from models import (
    AIUnavailableError,
    event_summary,
    kst_day_range_utc,
    now_utc,
    select_published_events,
    to_utc_str,
    today_kst,
)
from schemas import ApiError, RecommendRequest, RecommendResponse
from services import intent as intent_service
from services import ranker, reason

router = APIRouter(prefix="/api", tags=["recommend"])

NOTICES = {
    "ko": {
        "booking": "예매 가능 여부는 예매처에서 확인해 주세요.",
        "empty": "조건에 맞는 공연이 없습니다.",
        "ai_fallback": "AI 추천을 사용할 수 없어 선택한 필터로만 검색했어요.",
        "removed": "AI 추천 중 조건에 맞지 않거나 확인되지 않는 공연은 제외했어요.",
        "filters_only": "검색어 없이 선택한 조건으로 찾은 결과예요. AI 추천 순위는 적용되지 않았어요.",
    },
    "en": {
        "booking": "Please check ticket availability with the seller.",
        "empty": "No shows match your conditions.",
        "ai_fallback": "AI recommendations are unavailable, so only the selected filters were used.",
        "removed": "Some AI picks were removed because they did not match the conditions.",
        "filters_only": "Results for the selected filters only; AI recommendation ranking was not applied.",
    },
}


def _hard_filtered(conn: sqlite3.Connection, cond: intent_service.MergedConditions) -> list[sqlite3.Row]:
    min_utc = max_utc = None
    if cond.date:
        min_utc, max_utc = kst_day_range_utc(cond.date)
    return select_published_events(
        conn,
        now_utc=to_utc_str(now_utc()),
        min_utc=min_utc,
        max_utc=max_utc,
        area=cond.area,
        max_price=cond.max_price_krw,
        seating_type=cond.seating_requirement,
    )


def _response(cond, rows, items, notices, used_fallback, lang, search_limited=False) -> dict:
    """API.md §6 응답. 점수(score)는 노출하지 않는다. 확인 질문(needs_clarification)은 AI 연결 후 사용."""
    notices.append(NOTICES[lang]["booking"] if items else NOTICES[lang]["empty"])
    return {
        "status": "ok",
        "applied_filters": cond.applied_filters(),
        "applied_conditions": cond.applied_conditions(),
        "preferences": cond.preferences(lang),
        "total_matches": len(rows),
        "items": items,
        "notice": " ".join(notices),
        "used_fallback": used_fallback,
        "search_limited": search_limited,
        "clarification": None,
    }


def _rule_based(conn, ui, lang, notices, used_fallback) -> dict:
    cond = intent_service.merge_conditions(None, ui, locale=lang, today=today_kst())
    notices.extend(cond.notices)
    applied = cond.applied_filters()
    rows = _hard_filtered(conn, cond)
    items = []
    for s in ranker.rank(rows, cond.mood_tags, cond.solo_friendly, cond.seating_preference):
        items.append({"event": event_summary(s.row), "matched_tags": s.matched_tags,
                      "reason": reason.build_reason(s.row, applied, s.matched_tags, lang)})
    # 표시한 개수보다 필수 조건 후보가 많으면 탐색 범위 제한으로 알린다 (API.md §6)
    return _response(cond, rows, items, notices, used_fallback, lang, search_limited=len(rows) > len(items))


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    lang = req.locale
    ui = req.filters.model_dump()
    query = req.query.strip()
    has_ui = intent_service.has_effective_filter(ui)

    if not query and not has_ui:
        raise ApiError(422, "VALIDATION_ERROR", "검색어 또는 필터를 1개 이상 입력해 주세요.", {"field": "query"})
    if ui["date"]:
        try:
            date.fromisoformat(ui["date"])
        except ValueError:
            raise ApiError(422, "VALIDATION_ERROR", "요청 값을 확인해 주세요.", {"field": "filters.date"})

    if not query:
        # 검색어 없이 필터만: AI 없이 필수 조건 결과를 반환하고, AI 순위 미적용을 알린다 (API.md §6)
        return _rule_based(conn, ui, lang, [NOTICES[lang]["filters_only"]], used_fallback=True)

    # 1) 후보: 공개·미래 공연 + UI 하드 조건 선적용
    ui_cond = intent_service.merge_conditions(None, ui, locale=lang, today=today_kst())
    candidates = _hard_filtered(conn, ui_cond)
    if not candidates:
        notices = list(ui_cond.notices)
        return _response(ui_cond, [], [], notices, False, lang)

    # 2) LLM 직접 추천
    try:
        llm = intent_service.ask_llm(
            query, intent_service.build_candidates(candidates), today_kst().isoformat(), lang
        )
    except AIUnavailableError:
        if not has_ui:
            raise ApiError(503, "AI_UNAVAILABLE", "AI 추천을 사용할 수 없습니다. 필터를 선택해 검색해 주세요.")
        return _rule_based(conn, ui, lang, [NOTICES[lang]["ai_fallback"]], used_fallback=True)

    # 3) 조건 병합(UI 우선) → DB 하드 조건 재확인
    cond = intent_service.merge_conditions(llm.intent, ui, locale=lang, today=today_kst())
    notices = list(cond.notices)
    applied = cond.applied_filters()
    rows = _hard_filtered(conn, cond)
    by_id = {r["id"]: r for r in rows}
    picks, removed = intent_service.verify_picks(llm.picks, set(by_id))
    if removed:
        notices.append(NOTICES[lang]["removed"])

    # 4) 이유 문장 검사 (실패 시 템플릿). matched_tags 는 DB 태그와 요청 태그의 교집합으로 서버가 구성
    used_fallback = False
    items = []
    for pick in picks:
        row = by_id[pick.event_id]
        scored = ranker.score_event(row, cond.mood_tags, cond.solo_friendly, cond.seating_preference)
        text = reason.check_llm_reason(pick.reason)
        if text is None:
            text = reason.build_reason(row, applied, scored.matched_tags, lang)
            used_fallback = True
        items.append({"event": event_summary(row), "matched_tags": scored.matched_tags, "reason": text})
    return _response(cond, rows, items, notices, used_fallback, lang)
