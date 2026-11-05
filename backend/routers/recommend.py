"""POST /api/recommend — 상황 맞춤 추천 (API.md §6).

- 자연어 query 가 있으면: AI(Gemini)가 DB 조회 도구로 탐색·재조회하고 최대 3개를 고른다. 서버는 조건 유지와
  ID·근거·필수 조건 검증을 맡는다 (services/intent.py `run_ai_search`).
  AI 실패·시간 초과로 결과를 완성하지 못하면 503 AI_UNAVAILABLE — 수동 필터 결과로 자동 대체하지 않는다.
- query 없이 필터만: AI 없이 필수 조건 결과(최대 3개)와 사실 템플릿 이유, used_fallback=true.
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
        "not_picked": "조건에 맞는 공연은 있지만 요청에 맞는 추천을 고르지 못했어요.",
        "removed": "AI 추천 중 확인되지 않는 공연은 제외했어요.",
        "limited": "모든 후보를 살펴보기 전에 탐색을 마쳤어요.",
        "filters_only": "검색어 없이 선택한 조건으로 찾은 결과예요. AI 추천 순위는 적용되지 않았어요.",
    },
    "en": {
        "booking": "Please check ticket availability with the seller.",
        "empty": "No shows match your conditions.",
        "not_picked": "Some shows match the requirements, but none was picked for this request.",
        "removed": "Some AI picks were removed because they could not be verified.",
        "limited": "The search ended before every candidate was reviewed.",
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


def _filters_only(conn: sqlite3.Connection, cond: intent_service.MergedConditions, lang: str) -> dict:
    rows = _hard_filtered(conn, cond)
    applied = cond.applied_filters()
    items = [
        {"event": event_summary(s.row), "matched_tags": s.matched_tags,
         "reason": reason.build_reason(s.row, applied, s.matched_tags, lang)}
        for s in ranker.rank(rows, cond.mood_tags, cond.solo_friendly, cond.seating_preference)
    ]
    notices = [*cond.notices, NOTICES[lang]["filters_only"], NOTICES[lang]["booking" if items else "empty"]]
    return {
        "status": "ok",
        "applied_filters": applied,
        "applied_conditions": cond.applied_conditions(),
        "preferences": cond.preferences(lang),
        "total_matches": len(rows),
        "items": items,
        "notice": " ".join(notices),
        "used_fallback": True,
        "search_limited": len(rows) > len(items),  # 표시한 개수보다 후보가 많으면 (API.md §6)
        "clarification": None,
    }


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    lang = req.locale
    ui = req.filters.model_dump()
    query = req.query.strip()
    if not query and not intent_service.has_effective_filter(ui):
        raise ApiError(422, "VALIDATION_ERROR", "검색어 또는 필터를 1개 이상 입력해 주세요.", {"field": "query"})
    if ui["date"]:
        try:
            date.fromisoformat(ui["date"])
        except ValueError:
            raise ApiError(422, "VALIDATION_ERROR", "요청 값을 확인해 주세요.", {"field": "filters.date"})

    cond = intent_service.merge_conditions(ui, locale=lang)
    if not query:
        return _filters_only(conn, cond, lang)

    try:
        outcome = intent_service.run_ai_search(conn, query, cond, lang, to_utc_str(now_utc()), today_kst())
    except AIUnavailableError:
        raise ApiError(503, "AI_UNAVAILABLE",
                       "AI 추천을 완료하지 못했습니다. 잠시 후 다시 시도하거나 공연 목록에서 직접 찾아보세요.")

    items = [{"event": event_summary(p.row), "matched_tags": p.matched_tags, "reason": p.reason}
             for p in outcome.picks]
    notices = list(cond.notices)
    if "removed" in outcome.notices:
        notices.append(NOTICES[lang]["removed"])
    if outcome.search_limited:
        notices.append(NOTICES[lang]["limited"])
    if outcome.status == "ok":
        if items:
            notices.append(NOTICES[lang]["booking"])
        elif outcome.total_matches == 0:
            notices.append(NOTICES[lang]["empty"])
        else:
            notices.append(NOTICES[lang]["not_picked"])
    return {
        "status": outcome.status,
        "applied_filters": intent_service.summarize_filters(cond, outcome.required),
        "applied_conditions": (intent_service.applied_conditions(cond, outcome.required)
                               if outcome.searched else None),
        "preferences": outcome.preferences,
        "total_matches": outcome.total_matches,
        "items": items if outcome.status == "ok" else [],
        "notice": " ".join(notices) or None,
        "used_fallback": any(p.used_fallback for p in outcome.picks),
        "search_limited": outcome.search_limited,
        "clarification": outcome.clarification,
    }
