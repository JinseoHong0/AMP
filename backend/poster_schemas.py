"""Poster contracts, isolated from the event/DB team's shared schemas.py."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExtractedFields(Contract):
    # Nullable fields remain required in the JSON schema: unknown is null, not invented.
    title: str | None
    starts_at_local: str | None
    doors_open_at_local: str | None
    venue_name: str | None
    price_krw: int | None
    advance_price_krw: int | None
    door_price_krw: int | None
    lineup: list[str]
    genre: str | None


class VisionResult(Contract):
    extracted: ExtractedFields
    date_has_explicit_year: bool
    multiple_schedules: bool
    warnings: list[str]


class VenueSummary(Contract):
    id: int = Field(gt=0)
    name: str
    area: Literal["sinchon", "hongdae"]


class VenueMatch(Contract):
    status: Literal["matched", "ambiguous", "not_found", "no_name"]
    venue_id: int | None
    candidates: list[VenueSummary]


class PosterExtraction(Contract):
    upload_id: str
    extracted: ExtractedFields
    venue_match: VenueMatch
    needs_review: list[str]
    warnings: list[str]
