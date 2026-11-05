"""공연장 조회 API: GET /api/venues, GET /api/venues/{venue_id}.

공연장 신규 생성 API 는 MVP 범위에서 제외한다.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from database import get_db
from models import venue_detail
from schemas import ApiError, Area, VenueDetail, VenueListResponse
from services.venue_matcher import normalize_name

router = APIRouter(prefix="/api/venues", tags=["venues"])


@router.get("", response_model=VenueListResponse)
def list_venues(
    q: str | None = Query(default=None, max_length=100),
    area: Area | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    sql = "SELECT id, name, area FROM venues"
    params: list = []
    if area:
        sql += " WHERE area = ?"
        params.append(area)
    rows = conn.execute(sql + " ORDER BY id", params).fetchall()

    needle = normalize_name(q)
    if needle:
        rows = [r for r in rows if needle in normalize_name(r["name"])]
    items = [{"id": r["id"], "name": r["name"], "area": r["area"]} for r in rows]
    return {"items": items[:limit], "total": len(items)}


@router.get("/{venue_id}", response_model=VenueDetail)
def get_venue(venue_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = conn.execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
    if row is None:
        raise ApiError(404, "VENUE_NOT_FOUND", "공연장을 찾을 수 없습니다.", {"venue_id": venue_id})
    return venue_detail(row)
