import re
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

from backend.errors import ApiError
from backend.poster_schemas import VenueMatch, VenueSummary


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    # Keep other punctuation meaningful (e.g. A+B and AB are not the same venue).
    value = re.sub(r"[·.,'’\"\-()]", " ", value)
    return " ".join(value.split())


class SqliteVenueRepository:
    """Read existing venues only; never bootstrap, seed or modify the shared DB."""

    def __init__(self, path: Path):
        self.path = path

    def list_venues(self) -> list[VenueSummary]:
        try:
            uri = self.path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=3)) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT id, name, area FROM venues ORDER BY id"
                ).fetchall()
                return [VenueSummary.model_validate(dict(row)) for row in rows]
        except (sqlite3.Error, ValueError) as error:
            raise ApiError(
                503, "VENUE_DB_UNAVAILABLE", "공연장 DB가 아직 준비되지 않았습니다."
            ) from error


def match_venue(name: str | None, venues: list[VenueSummary]) -> VenueMatch:
    normalized = normalized_name(name) if name else ""
    if not normalized:
        return VenueMatch(status="no_name", venue_id=None, candidates=[])
    candidates = [venue for venue in venues if normalized_name(venue.name) == normalized]
    if len(candidates) == 1:
        return VenueMatch(status="matched", venue_id=candidates[0].id, candidates=candidates)
    status = "ambiguous" if candidates else "not_found"
    return VenueMatch(status=status, venue_id=None, candidates=candidates)
