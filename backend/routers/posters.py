"""POST /api/posters/parse — 포스터 추출(Gemini Vision) + 공연장 자동 매칭 (관리자 전용, DB 이벤트 생성 아님)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, UploadFile

from database import get_db, get_settings, require_admin
from models import AIUnavailableError
from schemas import ApiError, PosterParseResponse
from services import poster_parser
from services.venue_matcher import match_venue

router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/posters/parse", response_model=PosterParseResponse)
async def parse_poster(file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared not in poster_parser.MIME_EXT:
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "JPG, PNG, WebP 이미지만 업로드할 수 있습니다.",
                       {"content_type": declared})

    limit = get_settings().max_poster_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(413, "FILE_TOO_LARGE", "포스터는 최대 5MB까지 업로드할 수 있습니다.",
                       {"max_bytes": limit})
    actual = poster_parser.detect_image_mime(data)
    if not data or actual is None or actual != declared:
        raise ApiError(400, "INVALID_IMAGE", "이미지 파일을 읽을 수 없습니다. 다시 업로드해 주세요.")

    try:
        payload = poster_parser.call_vision(data, actual)
    except AIUnavailableError:
        raise ApiError(503, "AI_UNAVAILABLE", "포스터 분석을 사용할 수 없습니다. 수동으로 입력해 주세요.")

    extracted, needs_review, warnings = poster_parser.normalize_extraction(payload)
    venue_match = match_venue(conn, extracted["venue_name"])
    poster_parser.apply_venue_review(venue_match, needs_review, warnings)
    upload_id = poster_parser.save_temp(data, actual)
    return {
        "upload_id": upload_id,
        "extracted": extracted,
        "venue_match": venue_match,
        "needs_review": needs_review,
        "warnings": warnings,
    }
