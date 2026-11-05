"""공연 API: GET /api/events, GET /api/events/{event_id}, POST /api/events(관리자)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date as date_type
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query

from database import get_db, require_admin
from models import (
    EVENT_WITH_VENUE_SELECT,
    PriceMismatchError,
    compute_price,
    event_detail,
    event_summary,
    kst_day_range_utc,
    local_to_utc,
    media_url,
    now_utc,
    select_published_events,
    to_utc_str,
)
from schemas import (
    ApiError,
    Area,
    EventCreate,
    EventCreateResponse,
    EventDetail,
    EventListResponse,
    Locale,
    SeatingType,
)
from services import poster_parser

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=EventListResponse)
def list_events(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="KST 날짜"),
    area: Area | None = None,
    max_price_krw: int | None = Query(default=None, ge=0),
    seating_type: SeatingType | None = None,
    upcoming: bool = True,
    limit: int = Query(default=20, ge=1, le=50),
    locale: Locale = "ko",  # 목록 카드에는 언어별 문장이 없으므로 현재는 계약상 수용만 한다.
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    min_utc = max_utc = None
    if date:
        try:
            min_utc, max_utc = kst_day_range_utc(date_type.fromisoformat(date))
        except ValueError:
            raise ApiError(422, "VALIDATION_ERROR", "요청 값을 확인해 주세요.", {"field": "date"})
    rows = select_published_events(
        conn,
        now_utc=to_utc_str(now_utc()) if upcoming else None,
        min_utc=min_utc,
        max_utc=max_utc,
        area=area,
        max_price=max_price_krw,
        seating_type=seating_type,
    )
    return {"items": [event_summary(r) for r in rows[:limit]], "total": len(rows), "limit": limit}


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = conn.execute(f"{EVENT_WITH_VENUE_SELECT} WHERE e.id = ?", (event_id,)).fetchone()
    # 미공개(draft)·취소 공연은 존재 여부를 노출하지 않고 404.
    if row is None or row["status"] != "published":
        raise ApiError(404, "EVENT_NOT_FOUND", "공연을 찾을 수 없습니다.", {"event_id": event_id})
    return event_detail(row)


# ---------------------------------------------------------------------------
# POST /api/events — 검수한 공연 등록 (관리자 전용)
# ---------------------------------------------------------------------------
_register_lock = threading.Lock()  # 같은 upload_id 동시 등록(중복 클릭) 방지


def _validation(field: str, message: str = "요청 값을 확인해 주세요.") -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, {"field": field})


def _check_url(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise _validation(field, "http(s) URL 형식이어야 합니다.")
    return value


def _clean_text(value: str | None) -> str | None:
    return value if value else None


@router.post("", status_code=201, response_model=EventCreateResponse, dependencies=[Depends(require_admin)])
def create_event(body: EventCreate, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    # 1) 검수 확인
    if body.review_confirmed is not True:
        raise _validation("review_confirmed", "검수 확인(review_confirmed=true) 후 등록할 수 있습니다.")

    # 2) 기존 공연장 필수 (신규 생성 없음)
    if body.venue_id is None or body.venue_id <= 0 or conn.execute(
        "SELECT 1 FROM venues WHERE id = ?", (body.venue_id,)
    ).fetchone() is None:
        raise ApiError(422, "VENUE_REQUIRED", "기존 공연장을 선택해 주세요.", {"field": "venue_id"})

    # 3) 시각 (KST 로컬 → UTC) 및 순서
    starts = local_to_utc(body.starts_at_local)
    ends = local_to_utc(body.ends_at_local) if body.ends_at_local else None
    doors = local_to_utc(body.doors_open_at_local) if body.doors_open_at_local else None
    if doors is not None and doors > starts:
        raise _validation("doors_open_at_local", "입장 시작 시각은 공연 시작 시각보다 늦을 수 없습니다.")
    if ends is not None and ends <= starts:
        raise _validation("ends_at_local", "종료 시각은 시작 시각보다 뒤여야 합니다.")

    # 4~5) 대표 가격·price_basis 는 서버 산출
    try:
        price_krw, price_basis = compute_price(body.price_krw, body.advance_price_krw, body.door_price_krw)
    except PriceMismatchError:
        raise _validation("price_krw", "대표 가격은 예매가·현장가 중 최저값과 같아야 합니다.")

    booking_url = _check_url(body.booking_url, "booking_url")
    source_url = _check_url(body.source_url, "source_url")

    # 7) verified 는 실제 출처가 있을 때만
    now = to_utc_str(now_utc())
    verified_at = None
    if body.data_origin == "verified":
        if not source_url:
            raise _validation("source_url", "verified 데이터는 출처(source_url)가 필요합니다.")
        verified_at = now

    lineup = list(dict.fromkeys(s.strip() for s in body.lineup if s and s.strip()))
    moods = list(dict.fromkeys(body.mood_tags))

    with _register_lock:
        # 8) 업로드 ID: 서버 발급·미사용 임시 파일만
        temp_path = None
        if body.upload_id:
            try:
                temp_path = poster_parser.find_temp(body.upload_id)
            except poster_parser.UploadAlreadyUsed:
                raise ApiError(409, "UPLOAD_ALREADY_USED", "이미 등록에 사용된 포스터입니다.",
                               {"field": "upload_id"})
            except poster_parser.UploadNotFound:
                raise _validation("upload_id", "유효한 업로드 ID가 아닙니다. 포스터를 다시 업로드해 주세요.")

        cur = conn.execute(
            """INSERT INTO events (venue_id, title, starts_at_utc, ends_at_utc, doors_open_at_utc, price_krw,
               price_basis, advance_price_krw, door_price_krw, booking_url, lineup_json, genre, mood_tags_json,
               solo_friendly, seating_type, seat_assignment, drink_policy, description_ko, description_en,
               admission_notes_ko, admission_notes_en, poster_image_path, status, data_origin, source_url,
               verified_at_utc, created_at_utc, updated_at_utc)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,'published',?,?,?,?,?)""",
            (body.venue_id, body.title, to_utc_str(starts), to_utc_str(ends) if ends else None,
             to_utc_str(doors) if doors else None, price_krw, price_basis, body.advance_price_krw,
             body.door_price_krw, booking_url, json.dumps(lineup, ensure_ascii=False),
             _clean_text(body.genre), json.dumps(moods),
             None if body.solo_friendly is None else int(body.solo_friendly),
             body.seating_type, body.seat_assignment, _clean_text(body.drink_policy),
             _clean_text(body.description_ko), _clean_text(body.description_en),
             _clean_text(body.admission_notes_ko), _clean_text(body.admission_notes_en),
             body.data_origin, source_url, verified_at, now, now),
        )
        event_id = cur.lastrowid
        poster_path = dest = None
        try:
            if temp_path is not None:
                dest, poster_path = poster_parser.promote(temp_path, event_id)
                conn.execute("UPDATE events SET poster_image_path = ? WHERE id = ?", (poster_path, event_id))
            conn.commit()
        except Exception:
            conn.rollback()
            if dest is not None and temp_path is not None and dest.exists():
                dest.replace(temp_path)  # 파일 이동 되돌리기 → 재시도 가능
            raise
        if body.upload_id:
            poster_parser.mark_used(body.upload_id)

    # 등록 시 영어 자동 번역(AI)은 아직 연결 전이므로 시도하지 않았음을 그대로 알린다 (API.md §8 translation 계약).
    return {"id": event_id, "status": "published", "poster_url": media_url(poster_path),
            "translation": {"status": "not_requested", "generated_at": None},
            "warnings": ["공연은 등록되었으나 영어 번역은 아직 준비되지 않았습니다."],
            "message": "공연이 등록되었습니다."}
