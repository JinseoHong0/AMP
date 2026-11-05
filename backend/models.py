"""도메인 모델: 상수/enum, 도메인 오류, 시간(KST↔UTC), 가격 산출(DATABASE.md §5),
DB row → API dict 변환, 공개 공연 하드 필터 쿼리.

시간 규칙: DB 는 UTC `Z` 문자열, 사용자 기준 날짜는 Asia/Seoul(KST).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from database import get_settings

AREAS = ("sinchon", "hongdae")
SEATING_TYPES = ("standing", "seated", "mixed")
SEAT_ASSIGNMENTS = ("assigned", "unassigned")
SEATING_CHOICES = ("seated", "standing")  # preference / requirement 에 허용되는 값
DATA_ORIGINS = ("verified", "demo")
EVENT_STATUSES = ("draft", "published", "cancelled")
PRICE_BASES = ("advance", "door", "general")
# 사전 합의된 검수 분위기 태그. 새 태그는 API 계약 합의 후 추가한다.
ALLOWED_MOOD_TAGS = ("calm", "energetic", "romantic", "acoustic")


# ---------------------------------------------------------------------------
# 시간
# ---------------------------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def now_utc() -> datetime:
    """현재 UTC 시각. `FIXED_NOW_UTC`가 있으면 고정 테스트 시계로 사용한다."""
    fixed = get_settings().fixed_now_utc
    if fixed:
        return parse_utc(fixed)
    return datetime.now(UTC).replace(microsecond=0)


def today_kst() -> date:
    return now_utc().astimezone(KST).date()


def to_utc_str(dt: datetime) -> str:
    """aware datetime → `YYYY-MM-DDTHH:MM:SSZ`."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime 은 UTC 문자열로 바꿀 수 없습니다.")
    return dt.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def local_to_utc(dt: datetime) -> datetime:
    """KST 로컬 시각(naive) → UTC aware. offset 이 있으면 그 offset 을 존중한다."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(UTC)


def local_to_utc_str(dt: datetime | None) -> str | None:
    return None if dt is None else to_utc_str(local_to_utc(dt))


def kst_day_range_utc(day: date) -> tuple[str, str]:
    """KST 하루 [00:00, 다음날 00:00) 를 UTC 문자열 범위로 변환."""
    start = datetime.combine(day, time.min, tzinfo=KST)
    end = start + timedelta(days=1)
    return to_utc_str(start), to_utc_str(end)


def resolve_date_expression(expr: str | None, today: date | None = None) -> date | None:
    """`today|tomorrow|YYYY-MM-DD|None` → KST 날짜. 형식이 틀리면 ValueError."""
    if expr is None:
        return None
    base = today or today_kst()
    value = expr.strip().lower()
    if value == "today":
        return base
    if value == "tomorrow":
        return base + timedelta(days=1)
    if not _DATE_RE.fullmatch(value):
        raise ValueError(f"지원하지 않는 날짜 표현: {expr!r}")
    return date.fromisoformat(value)


# ---------------------------------------------------------------------------
# 도메인 오류 / 가격
# ---------------------------------------------------------------------------
class AIUnavailableError(RuntimeError):
    """AI(LLM/Vision) 미연결 또는 호출 실패. 호출 측은 명세의 장애 동작으로 복구한다."""


class PriceMismatchError(ValueError):
    """구분 가격과 다른 대표 가격을 동시에 보낸 경우."""


def compute_price(
    price_krw: int | None,
    advance_price_krw: int | None,
    door_price_krw: int | None,
) -> tuple[int | None, str | None]:
    """대표 가격(price_krw)과 price_basis 를 서버에서 산출한다.

    1) 예매/현장가 중 하나라도 있으면 min(non-null), 동가이면 advance 우선.
       요청 price_krw 가 있고 그 값과 다르면 PriceMismatchError.
    2) 둘 다 없으면 단일 price_krw → general.
    3) 모두 없으면 (None, None).
    """
    for value in (price_krw, advance_price_krw, door_price_krw):
        if value is not None and value < 0:
            raise ValueError("가격은 음수일 수 없습니다.")

    if advance_price_krw is not None or door_price_krw is not None:
        candidates: list[tuple[int, str]] = []
        if advance_price_krw is not None:
            candidates.append((advance_price_krw, "advance"))
        if door_price_krw is not None:
            candidates.append((door_price_krw, "door"))
        # 동가이면 advance 가 먼저 들어가 있으므로 min 이 안정적으로 advance 를 고른다.
        best_price, best_basis = min(candidates, key=lambda c: c[0])
        if price_krw is not None and price_krw != best_price:
            raise PriceMismatchError(
                f"대표 가격 {price_krw} 이(가) 예매/현장가 최저값 {best_price} 와 다릅니다."
            )
        return best_price, best_basis

    if price_krw is not None:
        return price_krw, "general"
    return None, None


def media_url(path: str | None) -> str | None:
    """저장 경로(`posters/x.jpg`) → `/media/posters/x.jpg`. HTTPS 는 그대로."""
    if not path:
        return None
    if path.startswith("https://") or path.startswith("/media/"):
        return path
    return "/media/" + path.lstrip("/")


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _bool_or_none(value: int | None) -> bool | None:
    return None if value is None else bool(value)


def venue_summary(row: sqlite3.Row, prefix: str = "") -> dict[str, Any]:
    return {"id": row[f"{prefix}id"], "name": row[f"{prefix}name"], "area": row[f"{prefix}area"]}


def venue_detail(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "area": row["area"],
        "address": row["address"],
        "floor": row["floor"],
        "entrance_image_url": media_url(row["entrance_image_path"]),
        "default_seating_type": row["default_seating_type"],
        "default_drink_policy": row["default_drink_policy"],
        "entrance_hint_ko": row["entrance_hint_ko"],
        "entrance_hint_en": row["entrance_hint_en"],
        "description_ko": row["description_ko"],
        "description_en": row["description_en"],
        "source_url": row["source_url"],
        "verified_at": row["verified_at_utc"],
        "data_origin": row["data_origin"],
    }


def event_summary(row: sqlite3.Row) -> dict[str, Any]:
    """목록/추천 카드용. row 는 events.* + venue_id/venue_name/venue_area 를 포함해야 한다."""
    return {
        "id": row["id"],
        "title": row["title"],
        "starts_at": row["starts_at_utc"],
        "price_krw": row["price_krw"],
        "price_basis": row["price_basis"],
        "advance_price_krw": row["advance_price_krw"],
        "door_price_krw": row["door_price_krw"],
        "genre": row["genre"],
        "mood_tags": _json_list(row["mood_tags_json"]),
        "seating_type": row["seating_type"],
        "poster_url": media_url(row["poster_image_path"]),
        "venue": {"id": row["venue_id"], "name": row["venue_name"], "area": row["venue_area"]},
        "data_origin": row["data_origin"],
    }


def event_detail(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "venue_id": row["venue_id"],
        "title": row["title"],
        "starts_at": row["starts_at_utc"],
        "ends_at": row["ends_at_utc"],
        "doors_open_at": row["doors_open_at_utc"],
        "price_krw": row["price_krw"],
        "price_basis": row["price_basis"],
        "advance_price_krw": row["advance_price_krw"],
        "door_price_krw": row["door_price_krw"],
        "booking_url": row["booking_url"],
        "lineup": _json_list(row["lineup_json"]),
        "genre": row["genre"],
        "mood_tags": _json_list(row["mood_tags_json"]),
        "solo_friendly": _bool_or_none(row["solo_friendly"]),
        "seating_type": row["seating_type"],
        "seat_assignment": row["seat_assignment"],
        "drink_policy": row["drink_policy"],
        "description_ko": row["description_ko"],
        "description_en": row["description_en"],
        "admission_notes_ko": row["admission_notes_ko"],
        "admission_notes_en": row["admission_notes_en"],
        "poster_url": media_url(row["poster_image_path"]),
        "status": row["status"],
        "data_origin": row["data_origin"],
        "source_url": row["source_url"],
        "verified_at": row["verified_at_utc"],
    }


# events + venues 조인 시 공통 SELECT 절
EVENT_WITH_VENUE_SELECT = (
    "SELECT e.*, v.name AS venue_name, v.area AS venue_area "
    "FROM events e JOIN venues v ON e.venue_id = v.id"
)


def select_published_events(
    conn: sqlite3.Connection,
    *,
    now_utc: str | None,
    min_utc: str | None = None,
    max_utc: str | None = None,
    area: str | None = None,
    max_price: int | None = None,
    seating_type: str | None = None,
) -> list[sqlite3.Row]:
    """공개 공연 하드 필터 (DATABASE.md §7 개념 SQL).

    - status=published 만.
    - now_utc 가 주어지면 지난 공연 제외.
    - max_price: price_krw NULL(미확인)은 제외, 0 은 확인된 무료.
    - seating_type: 이벤트에 **명시된** 값과 정확 일치만 (장소 기본값 사용 안 함).
    정렬: starts_at_utc ASC, id ASC.
    """
    where = ["e.status = 'published'"]
    params: list[Any] = []
    if now_utc is not None:
        where.append("e.starts_at_utc >= ?")
        params.append(now_utc)
    if min_utc is not None:
        where.append("e.starts_at_utc >= ?")
        params.append(min_utc)
    if max_utc is not None:
        where.append("e.starts_at_utc < ?")
        params.append(max_utc)
    if area is not None:
        where.append("v.area = ?")
        params.append(area)
    if max_price is not None:
        where.append("e.price_krw IS NOT NULL AND e.price_krw <= ?")
        params.append(max_price)
    if seating_type is not None:
        where.append("e.seating_type = ?")
        params.append(seating_type)
    sql = f"{EVENT_WITH_VENUE_SELECT} WHERE {' AND '.join(where)} ORDER BY e.starts_at_utc ASC, e.id ASC"
    return conn.execute(sql, params).fetchall()
