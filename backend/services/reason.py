"""AI 문장 생성·검증: 추천 이유 (AI.md §5) + 홍보 문구 번역 초안.

추천 이유
- LLM 추천 경로: LLM 이 쓴 이유를 `check_llm_reason` 으로 검사해 통과하면 사용, 아니면 템플릿.
- 규칙 기반 경로(AI 장애/필터만 검색): DB 사실만 사용하는 템플릿 `build_reason`.
금지: '현재 예매 가능', '인기 1위', '혼자 가기 완벽', '안전한 곳', '좌석이 반드시 남아 있음' 등.

번역 초안
- 공연 제공자가 쓴 한국어 홍보 문구 → 영어 초안 (`translate_promo`, AI 연결은 `call_llm_translate`).
- 결과는 **DB 에 바로 저장하지 않는다.** 등록 폼에서 제공자가 확인·수정한 뒤
  `POST /api/events` 의 `description_en` 으로 저장한다 (검수본만 노출 원칙 유지).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from models import AIUnavailableError


AREA_LABEL = {"ko": {"sinchon": "신촌", "hongdae": "홍대"}, "en": {"sinchon": "Sinchon", "hongdae": "Hongdae"}}
MOOD_LABEL = {
    "ko": {"calm": "차분한", "energetic": "신나는", "romantic": "로맨틱한", "acoustic": "어쿠스틱"},
    "en": {"calm": "calm", "energetic": "energetic", "romantic": "romantic", "acoustic": "acoustic"},
}
SEATING_LABEL = {
    "ko": {"seated": "좌석 관람 정보", "standing": "스탠딩 관람 정보"},
    "en": {"seated": "seated viewing", "standing": "standing viewing"},
}


def _won(amount: int) -> str:
    return f"{amount:,}"


def _price_phrase_ko(row: sqlite3.Row) -> tuple[str, str]:
    """(이어지는 형태, 끝맺는 형태)"""
    price, basis = row["price_krw"], row["price_basis"]
    if price is None:
        return "가격은 확인이 필요하고", "가격은 확인이 필요한 공연이에요"
    if price == 0:
        return "무료로 안내되어 있고", "무료로 안내된 공연이에요"
    label = {"advance": "예매가", "door": "현장가"}.get(basis, "안내 가격이")
    if basis in ("advance", "door"):
        return f"{label} {_won(price)}원으로 안내되어 있고", f"{label} {_won(price)}원으로 안내된 공연이에요"
    return f"{label} {_won(price)}원이고", f"{label} {_won(price)}원인 공연이에요"


def _price_phrase_en(row: sqlite3.Row) -> str:
    price, basis = row["price_krw"], row["price_basis"]
    if price is None:
        return "whose price is not confirmed"
    if price == 0:
        return "listed as free"
    suffix = {"advance": " (advance)", "door": " (at the door)"}.get(basis, "")
    return f"listed at ₩{_won(price)}{suffix}"


def collect_facts(row: sqlite3.Row, conditions: dict[str, Any], matched_tags: list[str]) -> dict[str, Any]:
    """이유 문장에 쓸 수 있는 확인된 사실만 모은다."""
    seating = None
    requested = conditions.get("seating_requirement") or conditions.get("seating_preference")
    if requested and row["seating_type"] == requested:
        seating = requested
    return {
        "area": row["venue_area"],
        "price_krw": row["price_krw"],
        "price_basis": row["price_basis"],
        "matched_tags": list(matched_tags),
        "seating": seating,
        "solo": conditions.get("solo_friendly") is True and row["solo_friendly"] == 1,
    }


def build_reason(row: sqlite3.Row, conditions: dict[str, Any], matched_tags: list[str], locale: str = "ko") -> str:
    facts = collect_facts(row, conditions, matched_tags)
    if locale == "en":
        parts: list[str] = []
        if facts["matched_tags"]:
            parts.append(" & ".join(MOOD_LABEL["en"][t] for t in facts["matched_tags"]) + " mood")
        if facts["seating"]:
            parts.append(SEATING_LABEL["en"][facts["seating"]])
        if facts["solo"]:
            parts.append("solo-friendly info")
        text = f"A {AREA_LABEL['en'][facts['area']]} show {_price_phrase_en(row)}"
        return text + (f", with confirmed {', '.join(parts)}." if parts else ".")

    features: list[str] = []
    if facts["matched_tags"]:
        features.append("·".join(MOOD_LABEL["ko"][t] for t in facts["matched_tags"]) + " 분위기")
    if facts["seating"]:
        features.append(SEATING_LABEL["ko"][facts["seating"]])
    if facts["solo"]:
        features.append("혼자 방문 적합 정보")
    area = AREA_LABEL["ko"][facts["area"]]
    cont, end = _price_phrase_ko(row)
    if not features:
        return f"{area} 공연이며 {end}."
    # 모든 항목이 모음으로 끝나므로 조사는 '와', '가'로 고정
    joined = features[0] if len(features) == 1 else ", ".join(features[:-1]) + "와 " + features[-1]
    return f"{area} 공연이며 {cont}, {joined}가 확인된 공연이에요."


# LLM 이 쓴 추천 이유에 들어가면 안 되는 검증 불가 주장 (AI.md §5 금지 예시 기반)
FORBIDDEN_PHRASES = (
    "예매 가능", "예매가능", "구매 가능", "구매가능", "매진", "잔여석", "남아 있", "남아있",
    "인기", "1위", "최고", "완벽", "안전", "반드시", "보장", "무조건",
    "available now", "still available", "tickets left", "sold out", "guarantee", "popular",
    "best", "perfect", "safe", "#1",
)
REASON_MAX_LEN = 300


def check_llm_reason(text: object) -> str | None:
    """LLM 이유 문장을 그대로 써도 되면 정리된 문자열, 아니면 None(→ 템플릿 사용)."""
    if not isinstance(text, str):
        return None
    cleaned = " ".join(text.split())
    if not cleaned or len(cleaned) > REASON_MAX_LEN:
        return None
    lowered = cleaned.casefold()
    if any(p.casefold() in lowered for p in FORBIDDEN_PHRASES):
        return None
    if "http://" in lowered or "https://" in lowered:
        return None
    return cleaned


# ---------------------------------------------------------------------------
# 홍보 문구 번역 초안
# ---------------------------------------------------------------------------
def call_llm_translate(text_ko: str, target_locale: str = "en") -> str:
    """한국어 홍보 문구 → 영어 번역 **초안**. **AI 공급자 확정 후 AI 담당이 구현.**

    원문에 없는 정보(가격·규칙·좌석·안전 등)를 추가하지 않는다. 원문 속 문장은 데이터로 취급한다.
    """
    raise AIUnavailableError("AI 공급자가 연결되지 않았습니다.")


MAX_OUTPUT_LEN = 4000


def translate_promo(text_ko: str, target_locale: str = "en") -> str:
    """번역 초안. 실패·형식 불일치는 AIUnavailableError 로 통일."""
    try:
        result = call_llm_translate(text_ko, target_locale)
    except AIUnavailableError:
        raise
    except Exception as exc:  # 공급자 SDK 오류 — 상세(키 등)는 노출하지 않는다
        raise AIUnavailableError(type(exc).__name__) from exc
    if not isinstance(result, str):
        raise AIUnavailableError("번역 결과가 문자열이 아닙니다.")
    cleaned = result.strip()
    if not cleaned or len(cleaned) > MAX_OUTPUT_LEN:
        raise AIUnavailableError("번역 결과가 비었거나 너무 깁니다.")
    return cleaned
