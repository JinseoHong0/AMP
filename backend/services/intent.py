"""자연어 → LLM 직접 추천 + 서버 검증 (AI.md §3 의도 해석 규칙 유지).

흐름:
1) 서버: 공개·미래 공연 후보를 만든다 (UI 필터가 있으면 하드 조건 선적용) → `build_candidates`.
2) LLM : 질의를 해석해 `applied_filters` 와 추천 `items(event_id, reason)` 를 한 번에 반환
         → `call_llm_recommend` (**AI 연결 공란**).
3) 서버: 응답 형식 검증(`parse_llm_response`, 1회 재시도) → 조건 검증·병합(`parse_intent_payload`,
         `merge_conditions`, UI 우선) → DB 하드 조건 재확인으로 위반·미존재 ID 제거(`verify_picks`, 최대 3개).
   이유 문장 검사는 services/reason.py, 규칙 점수는 services/ranker.py.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from models import (
    ALLOWED_MOOD_TAGS,
    AREAS,
    KST,
    SEATING_CHOICES,
    AIUnavailableError,
    parse_utc,
    resolve_date_expression,
)


# ---------------------------------------------------------------------------
# AI 연결 지점 — 현재 공란
# ---------------------------------------------------------------------------
def call_llm_recommend(
    query: str,
    candidates: list[dict[str, Any]],
    today_kst: str,
    locale: str,
) -> dict[str, Any]:
    """자연어 + 후보 공연 목록 → LLM 이 바로 추천. **AI 공급자 확정 후 AI 담당이 구현.**

    - 호출은 백엔드에서만, 키는 `.env` 의 LLM_API_KEY. 질의·공연 설명은 데이터로 취급(지시로 실행 금지).
    - candidates: `build_candidates` 형식. today_kst: 'today/tomorrow' 해석 기준 KST 날짜(YYYY-MM-DD).

    반환 형식 (서버가 검증 후 사용):
    {
      "applied_filters": {           # SearchIntent 와 동일 키
        "date_expression": "2026-11-07" | "today" | "tomorrow" | null,
        "area": "sinchon" | "hongdae" | null,
        "max_price_krw": 20000 | null,
        "mood_tags": ["calm"],
        "solo_friendly": true | false | null,
        "seating_preference": "seated" | "standing" | null,
        "seating_requirement": "seated" | "standing" | null
      },
      "items": [                     # 추천 순서대로, candidates 의 id 만 사용
        {"event_id": 101, "reason": "후보 데이터에 있는 사실만으로 쓴 한 줄 이유"}
      ]
    }
    """
    raise AIUnavailableError("AI 공급자가 연결되지 않았습니다.")


# ---------------------------------------------------------------------------
# 검색 조건(SearchIntent) 검증 · 병합
# ---------------------------------------------------------------------------
INTENT_KEYS = (
    "date_expression", "area", "max_price_krw", "mood_tags",
    "solo_friendly", "seating_preference", "seating_requirement",
)


@dataclass
class SearchIntent:
    date_expression: str | None = None
    area: str | None = None
    max_price_krw: int | None = None
    mood_tags: list[str] = field(default_factory=list)
    solo_friendly: bool | None = None
    seating_preference: str | None = None
    seating_requirement: str | None = None


@dataclass
class IntentResult:
    intent: SearchIntent
    dropped: list[str]  # 허용 범위 밖이라 버린 필드명


def parse_intent_payload(payload: Any) -> IntentResult:
    """LLM JSON → SearchIntent. 허용 enum/범위 밖 값은 **버리고** 기록한다(다른 뜻으로 바꾸지 않음)."""
    if not isinstance(payload, dict):
        raise ValueError("SearchIntent 는 JSON 객체여야 합니다.")
    intent = SearchIntent()
    dropped: list[str] = []

    expr = payload.get("date_expression")
    if expr is not None:
        if isinstance(expr, str):
            try:
                resolve_date_expression(expr)
                intent.date_expression = expr.strip().lower()
            except ValueError:
                dropped.append("date_expression")
        else:
            dropped.append("date_expression")

    area = payload.get("area")
    if area is not None:
        if area in AREAS:
            intent.area = area
        else:
            dropped.append("area")

    price = payload.get("max_price_krw")
    if price is not None:
        if isinstance(price, int) and not isinstance(price, bool) and price >= 0:
            intent.max_price_krw = price
        else:
            dropped.append("max_price_krw")

    moods = payload.get("mood_tags") or []
    if isinstance(moods, list):
        seen: list[str] = []
        for tag in moods:
            if tag in ALLOWED_MOOD_TAGS and tag not in seen:
                seen.append(tag)
            elif tag not in ALLOWED_MOOD_TAGS:
                if "mood_tags" not in dropped:
                    dropped.append("mood_tags")
        intent.mood_tags = seen
    else:
        dropped.append("mood_tags")

    solo = payload.get("solo_friendly")
    if solo is not None:
        if isinstance(solo, bool):
            intent.solo_friendly = solo
        else:
            dropped.append("solo_friendly")

    for key in ("seating_preference", "seating_requirement"):
        value = payload.get(key)
        if value is None:
            continue
        if value in SEATING_CHOICES:
            setattr(intent, key, value)
        else:
            dropped.append(key)

    return IntentResult(intent=intent, dropped=dropped)


@dataclass
class MergedConditions:
    date: date | None
    area: str | None
    max_price_krw: int | None
    mood_tags: list[str]
    solo_friendly: bool | None
    seating_preference: str | None
    seating_requirement: str | None
    notices: list[str]

    def applied_filters(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat() if self.date else None,
            "area": self.area,
            "max_price_krw": self.max_price_krw,
            "mood_tags": list(self.mood_tags),
            "solo_friendly": self.solo_friendly,
            "seating_preference": self.seating_preference,
            "seating_requirement": self.seating_requirement,
        }

    def applied_conditions(self) -> dict[str, Any]:
        """실제 적용한 필수 조건을 API.md `EventQuery` 식으로. 조건이 없으면 `{"all": []}`."""
        nodes: list[dict[str, Any]] = []
        if self.date:
            nodes.append({"field": "starts_at", "op": "gte", "value": f"{self.date.isoformat()}T00:00:00+09:00"})
            nodes.append({"field": "starts_at", "op": "lt",
                          "value": f"{(self.date + timedelta(days=1)).isoformat()}T00:00:00+09:00"})
        if self.area:
            nodes.append({"field": "area", "op": "eq", "value": self.area})
        if self.max_price_krw is not None:
            nodes.append({"field": "price_krw", "op": "lte", "value": self.max_price_krw})
        if self.seating_requirement:
            nodes.append({"field": "seating_type", "op": "eq", "value": self.seating_requirement})
        return {"all": nodes}

    def preferences(self, locale: str = "ko") -> list[str]:
        """선호(필수 아님)를 사람이 읽는 문장으로. 고정 태그·점수로 노출하지 않는다."""
        lang = "en" if locale == "en" else "ko"
        items = [_PREFERENCE_TEXT[lang]["mood"][tag] for tag in self.mood_tags if tag in _PREFERENCE_TEXT[lang]["mood"]]
        if self.solo_friendly is True:
            items.append(_PREFERENCE_TEXT[lang]["solo"])
        if self.seating_preference:
            items.append(_PREFERENCE_TEXT[lang]["seating"][self.seating_preference])
        return items


_PREFERENCE_TEXT: dict[str, dict[str, Any]] = {
    "ko": {
        "mood": {"calm": "차분한 분위기", "energetic": "신나는 분위기", "romantic": "로맨틱한 분위기",
                 "acoustic": "어쿠스틱한 분위기"},
        "solo": "혼자 관람하기 좋은 공연",
        "seating": {"seated": "좌석 관람 선호", "standing": "스탠딩 관람 선호"},
    },
    "en": {
        "mood": {"calm": "Calm mood", "energetic": "Energetic mood", "romantic": "Romantic mood",
                 "acoustic": "Acoustic mood"},
        "solo": "Good for a solo visit",
        "seating": {"seated": "Prefers seated", "standing": "Prefers standing"},
    },
}


_DROP_NOTICES = {
    "ko": {
        "date_expression": "지원하지 않는 날짜 표현은 적용하지 않았어요. 날짜를 직접 선택해 주세요.",
        "area": "현재 신촌·홍대 지역만 지원해요. 다른 지역 조건은 적용하지 않았어요.",
        "max_price_krw": "가격 조건을 해석하지 못해 적용하지 않았어요.",
        "mood_tags": "지원하지 않는 분위기 조건은 적용하지 않았어요.",
        "solo_friendly": "혼자 방문 조건을 해석하지 못해 적용하지 않았어요.",
        "seating_preference": "좌석 선호 조건을 해석하지 못해 적용하지 않았어요.",
        "seating_requirement": "좌석 필수 조건을 해석하지 못해 적용하지 않았어요.",
    },
    "en": {
        "date_expression": "The date expression is not supported and was not applied. Please pick a date.",
        "area": "Only Sinchon and Hongdae are supported. Other areas were not applied.",
        "max_price_krw": "The price condition could not be read and was not applied.",
        "mood_tags": "Unsupported mood conditions were not applied.",
        "solo_friendly": "The solo-visit condition could not be read and was not applied.",
        "seating_preference": "The seating preference could not be read and was not applied.",
        "seating_requirement": "The seating requirement could not be read and was not applied.",
    },
}


def merge_conditions(
    intent_result: IntentResult | None,
    ui: dict[str, Any],
    locale: str = "ko",
    today: date | None = None,
) -> MergedConditions:
    """UI 에서 명시한 값이 같은 키의 AI 추출값보다 우선한다."""
    lang = "en" if locale == "en" else "ko"
    intent = intent_result.intent if intent_result else SearchIntent()
    notices: list[str] = []
    if intent_result:
        notices.extend(_DROP_NOTICES[lang][k] for k in intent_result.dropped)

    def pick(key: str, ai_value: Any) -> Any:
        ui_value = ui.get(key)
        if key == "mood_tags":
            return list(ui_value) if ui_value else list(ai_value)
        return ui_value if ui_value is not None else ai_value

    if ui.get("date"):
        day = date.fromisoformat(ui["date"])
    else:
        day = resolve_date_expression(intent.date_expression, today)

    pref = pick("seating_preference", intent.seating_preference)
    req = pick("seating_requirement", intent.seating_requirement)
    if req is not None and pref is not None and pref != req:
        notices.append(
            f"좌석 필수 조건({req})을 적용하고 충돌하는 좌석 선호({pref})는 적용하지 않았어요."
            if lang == "ko"
            else f"The seating requirement ({req}) was applied; the conflicting preference ({pref}) was ignored."
        )
        pref = None

    moods: list[str] = []
    for tag in pick("mood_tags", intent.mood_tags):
        if tag not in moods:
            moods.append(tag)

    return MergedConditions(
        date=day,
        area=pick("area", intent.area),
        max_price_krw=pick("max_price_krw", intent.max_price_krw),
        mood_tags=moods,
        solo_friendly=pick("solo_friendly", intent.solo_friendly),
        seating_preference=pref,
        seating_requirement=req,
        notices=notices,
    )


def has_effective_filter(ui: dict[str, Any]) -> bool:
    """수동(칩) 필터에 유효 조건이 1개 이상인지."""
    return any(
        (bool(v) if k == "mood_tags" else v is not None)
        for k, v in ui.items()
    )


# ---------------------------------------------------------------------------
# LLM 직접 추천: 후보 생성 · 응답 검증
# ---------------------------------------------------------------------------
MAX_ITEMS = 3


def _json_list(value: str | None) -> list[Any]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _kst_local(utc_str: str | None) -> str | None:
    return None if utc_str is None else parse_utc(utc_str).astimezone(KST).strftime("%Y-%m-%dT%H:%M")


def build_candidates(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """LLM 에 넘길 후보: DB 에 있는 확인된 사실만. 시각은 이해하기 쉽게 KST 로컬로도 제공."""
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "starts_at_kst": _kst_local(r["starts_at_utc"]),
            "doors_open_at_kst": _kst_local(r["doors_open_at_utc"]),
            "venue_name": r["venue_name"],
            "area": r["venue_area"],
            "price_krw": r["price_krw"],
            "price_basis": r["price_basis"],
            "advance_price_krw": r["advance_price_krw"],
            "door_price_krw": r["door_price_krw"],
            "genre": r["genre"],
            "lineup": _json_list(r["lineup_json"]),
            "mood_tags": _json_list(r["mood_tags_json"]),
            "solo_friendly": None if r["solo_friendly"] is None else bool(r["solo_friendly"]),
            "seating_type": r["seating_type"],
            "seat_assignment": r["seat_assignment"],
            "description_ko": r["description_ko"],
        }
        for r in rows
    ]


@dataclass
class LLMPick:
    event_id: int
    reason: Any


@dataclass
class LLMRecommendation:
    intent: IntentResult
    picks: list[LLMPick]


def parse_llm_response(payload: Any) -> LLMRecommendation:
    """형식이 틀리면 ValueError. 개별 item 의 잘못된 값은 버린다."""
    if not isinstance(payload, dict):
        raise ValueError("추천 응답은 JSON 객체여야 합니다.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("items 는 배열이어야 합니다.")
    intent = parse_intent_payload(payload.get("applied_filters") or {})
    picks: list[LLMPick] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        event_id = item.get("event_id")
        if isinstance(event_id, int) and not isinstance(event_id, bool):
            picks.append(LLMPick(event_id=event_id, reason=item.get("reason")))
    return LLMRecommendation(intent=intent, picks=picks)


def ask_llm(query: str, candidates: list[dict[str, Any]], today_kst: str, locale: str) -> LLMRecommendation:
    """LLM 호출. 형식 불일치는 1회만 재시도, 그래도 실패하면 AIUnavailableError."""
    last_error: Exception | None = None
    for _ in range(2):
        try:
            payload = call_llm_recommend(query, candidates, today_kst, locale)
        except AIUnavailableError:
            raise
        except Exception as exc:  # 공급자 SDK 오류 — 상세(키 등)는 노출하지 않는다
            raise AIUnavailableError(type(exc).__name__) from exc
        try:
            return parse_llm_response(payload)
        except ValueError as exc:
            last_error = exc
    raise AIUnavailableError(f"추천 응답 형식 오류: {last_error}")


def verify_picks(picks: list[LLMPick], allowed_ids: set[int]) -> tuple[list[LLMPick], int]:
    """하드 조건을 통과한 ID 만, 중복 제거, 최대 3개. (통과 목록, 제거된 개수)."""
    kept: list[LLMPick] = []
    seen: set[int] = set()
    removed = 0
    for pick in picks:
        if pick.event_id in seen:
            continue
        seen.add(pick.event_id)
        if pick.event_id not in allowed_ids:
            removed += 1
            continue
        if len(kept) < MAX_ITEMS:
            kept.append(pick)
    return kept, removed
