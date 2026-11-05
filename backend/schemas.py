"""Pydantic 요청/응답 스키마 (API.md 계약과 동일한 필드명) + 공통 오류 응답 형식.

오류 응답: `{"error": {"code", "message", "details"}}` (API.md §0). 핸들러 등록은 main.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Area = Literal["sinchon", "hongdae"]
SeatingType = Literal["standing", "seated", "mixed"]
SeatingChoice = Literal["seated", "standing"]
SeatAssignment = Literal["assigned", "unassigned"]
PriceBasis = Literal["advance", "door", "general"]
DataOrigin = Literal["verified", "demo"]
Locale = Literal["ko", "en"]
MoodTag = Literal["calm", "energetic", "romantic", "acoustic"]


# ---------- 공통 오류 ----------
class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorInfo


# ---------- 공통 ----------
class VenueSummary(BaseModel):
    id: int
    name: str
    area: Area


class EventSummary(BaseModel):
    id: int
    title: str
    starts_at: str
    price_krw: int | None
    price_basis: PriceBasis | None
    advance_price_krw: int | None
    door_price_krw: int | None
    genre: str | None
    mood_tags: list[str]
    seating_type: SeatingType | None
    poster_url: str | None
    venue: VenueSummary
    data_origin: DataOrigin


# ---------- GET /api/events ----------
class EventListResponse(BaseModel):
    items: list[EventSummary]
    total: int
    limit: int


class EventDetail(BaseModel):
    id: int
    venue_id: int
    title: str
    starts_at: str
    ends_at: str | None
    doors_open_at: str | None
    price_krw: int | None
    price_basis: PriceBasis | None
    advance_price_krw: int | None
    door_price_krw: int | None
    booking_url: str | None
    lineup: list[str]
    genre: str | None
    mood_tags: list[str]
    solo_friendly: bool | None
    seating_type: SeatingType | None
    seat_assignment: SeatAssignment | None
    drink_policy: str | None
    description_ko: str | None
    description_en: str | None
    admission_notes_ko: str | None
    admission_notes_en: str | None
    poster_url: str | None
    status: Literal["draft", "published", "cancelled"]
    data_origin: DataOrigin
    source_url: str | None
    verified_at: str | None


# ---------- GET /api/venues ----------
class VenueListResponse(BaseModel):
    items: list[VenueSummary]
    total: int


class VenueDetail(BaseModel):
    id: int
    name: str
    area: Area
    address: str | None
    floor: str | None
    entrance_image_url: str | None
    default_seating_type: SeatingType | None
    default_drink_policy: str | None
    entrance_hint_ko: str | None
    entrance_hint_en: str | None
    description_ko: str | None
    description_en: str | None
    source_url: str | None
    verified_at: str | None
    data_origin: DataOrigin


# ---------- POST /api/recommend ----------
class RecommendFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    area: Area | None = None
    max_price_krw: int | None = Field(default=None, ge=0)
    mood_tags: list[MoodTag] = Field(default_factory=list, max_length=10)
    solo_friendly: bool | None = None
    seating_preference: SeatingChoice | None = None
    seating_requirement: SeatingChoice | None = None


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", max_length=500)
    filters: RecommendFilters = Field(default_factory=RecommendFilters)
    locale: Locale = "ko"


class AppliedFilters(BaseModel):
    date: str | None
    area: Area | None
    max_price_krw: int | None
    mood_tags: list[str]
    solo_friendly: bool | None
    seating_preference: SeatingChoice | None
    seating_requirement: SeatingChoice | None


class RecommendItem(BaseModel):
    event: EventSummary
    score: int
    matched_tags: list[str]
    reason: str


class RecommendResponse(BaseModel):
    applied_filters: AppliedFilters
    total_matches: int
    items: list[RecommendItem]
    notice: str | None
    used_fallback: bool


# ---------- POST /api/posters/parse ----------
class PosterExtraction(BaseModel):
    title: str | None = None
    starts_at_local: str | None = None
    doors_open_at_local: str | None = None
    venue_name: str | None = None
    price_krw: int | None = None
    advance_price_krw: int | None = None
    door_price_krw: int | None = None
    lineup: list[str] = Field(default_factory=list)
    genre: str | None = None


class VenueMatch(BaseModel):
    status: Literal["matched", "ambiguous", "not_found", "no_name"]
    venue_id: int | None
    candidates: list[VenueSummary]


class PosterParseResponse(BaseModel):
    upload_id: str
    extracted: PosterExtraction
    venue_match: VenueMatch
    needs_review: list[str]
    warnings: list[str]


# ---------- POST /api/events ----------
class EventCreate(BaseModel):
    """관리자 검수 후 등록 요청. `price_basis` 등 정의되지 않은 필드는 거절(extra=forbid)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    upload_id: str | None = None
    venue_id: int | None = None  # 누락/무효는 VENUE_REQUIRED 로 별도 처리
    title: str = Field(min_length=1, max_length=120)
    starts_at_local: datetime
    ends_at_local: datetime | None = None
    doors_open_at_local: datetime | None = None
    price_krw: int | None = Field(default=None, ge=0)
    advance_price_krw: int | None = Field(default=None, ge=0)
    door_price_krw: int | None = Field(default=None, ge=0)
    booking_url: str | None = Field(default=None, max_length=500)
    lineup: list[str] = Field(default_factory=list, max_length=30)
    genre: str | None = Field(default=None, max_length=40)
    mood_tags: list[MoodTag] = Field(default_factory=list, max_length=10)
    solo_friendly: bool | None = None
    seating_type: SeatingType | None = None
    seat_assignment: SeatAssignment | None = None
    drink_policy: str | None = Field(default=None, max_length=300)
    description_ko: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    admission_notes_ko: str | None = Field(default=None, max_length=2000)
    admission_notes_en: str | None = Field(default=None, max_length=2000)
    source_url: str | None = Field(default=None, max_length=500)
    data_origin: DataOrigin = "demo"
    review_confirmed: bool = False


class EventCreateResponse(BaseModel):
    id: int
    status: Literal["published"]
    poster_url: str | None
    message: str


# ---------- POST /api/translate (관리자, 번역 초안) ----------
class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text_ko: str = Field(min_length=1, max_length=2000)
    target_locale: Literal["en"] = "en"


class TranslateResponse(BaseModel):
    text_en: str
    needs_review: bool
    notice: str
