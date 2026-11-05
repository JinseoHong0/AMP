import re
from datetime import datetime

from backend.poster_schemas import ExtractedFields, VisionResult


def review_extraction(result: VisionResult) -> tuple[ExtractedFields, list[str], list[str]]:
    """Normalize model output, preserving invalid readings in warnings for human review."""
    values = result.extracted.model_dump()
    review: list[str] = []
    warnings = [warning[:500] for warning in result.warnings[:20] if warning.strip()]

    def invalidate(field: str, explanation: str) -> None:
        original = values[field]
        if original is not None:
            warnings.append(f"{explanation} (읽은 값: {str(original)[:160]})")
        values[field] = None
        review.append("venue_id" if field == "venue_name" else field)

    for field, limit in [("title", 120), ("venue_name", 200), ("genre", 100)]:
        value = values[field]
        values[field] = value.strip() or None if value is not None else None
        if values[field] is not None and len(values[field]) > limit:
            invalidate(field, f"{field} 길이를 확인해 주세요.")

    for field in ("starts_at_local", "doors_open_at_local"):
        value = values[field]
        if value is not None:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", value):
                    raise ValueError()
                values[field] = datetime.fromisoformat(value).isoformat(timespec="seconds")
            except ValueError:
                invalidate(field, "유효하지 않은 날짜·시각입니다. 직접 확인해 주세요.")
    if not result.date_has_explicit_year or result.multiple_schedules:
        for field in ("starts_at_local", "doors_open_at_local"):
            invalidate(field, "연도가 없거나 여러 일정이 있어 날짜를 확정하지 않았습니다.")
        warnings.append("포스터의 연도와 단일 공연 일정을 직접 확인해 주세요.")
    start, doors = values["starts_at_local"], values["doors_open_at_local"]
    if start and doors and doors > start:
        # Keep syntactically valid original readings in the form; registration must reject this order.
        review.extend(["starts_at_local", "doors_open_at_local"])
        warnings.append("읽은 입장 시간이 공연 시작보다 늦습니다. 두 시각을 수정해 주세요.")

    for field in ("price_krw", "advance_price_krw", "door_price_krw"):
        if values[field] is not None and not 0 <= values[field] <= 9_007_199_254_740_991:
            invalidate(field, "티켓 가격 범위를 확인해 주세요.")
    prices = [
        values[key] for key in ("advance_price_krw", "door_price_krw") if values[key] is not None
    ]
    if prices:
        if values["price_krw"] is not None and values["price_krw"] != min(prices):
            warnings.append("대표 가격을 확인된 예매·현장 가격 중 최저가로 맞췄습니다.")
            review.append("price_krw")
        values["price_krw"] = min(prices)
    values["lineup"] = list(
        dict.fromkeys(name.strip() for name in values["lineup"] if name.strip())
    )
    for field in ("title", "starts_at_local", "doors_open_at_local", "price_krw", "genre"):
        if values[field] is None:
            review.append(field)
    if not values["lineup"]:
        review.append("lineup")
    if values["doors_open_at_local"] is None:
        warnings.append("입장 시작 시각은 확인되지 않았습니다. 공연 시작 시간과 구분해 주세요.")
    return (
        ExtractedFields.model_validate(values),
        list(dict.fromkeys(review)),
        list(dict.fromkeys(warnings)),
    )
