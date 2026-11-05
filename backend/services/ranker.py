"""소프트 랭킹 — 재현 가능한 규칙 점수 (DATABASE.md §7, AI.md §4).

하드 필터(날짜/지역/가격/좌석 필수)를 통과한 후보에만 적용한다. 점수로 제외된 후보를 되살리지 않는다.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

MOOD_POINTS = 40
SOLO_POINTS = 20
SEATING_PREF_POINTS = 20
MAX_RESULTS = 3


@dataclass
class Scored:
    row: sqlite3.Row
    score: int
    matched_tags: list[str]


def _moods(row: sqlite3.Row) -> list[str]:
    try:
        data = json.loads(row["mood_tags_json"] or "[]")
    except json.JSONDecodeError:
        return []
    return [t for t in data if isinstance(t, str)]


def score_event(
    row: sqlite3.Row,
    mood_tags: list[str],
    solo_friendly: bool | None,
    seating_preference: str | None,
) -> Scored:
    event_moods = _moods(row)
    # 요청 순서를 유지하며 중복 제거한 일치 태그
    matched = [t for t in dict.fromkeys(mood_tags) if t in event_moods]
    score = MOOD_POINTS * len(matched)
    if solo_friendly is True and row["solo_friendly"] == 1:
        score += SOLO_POINTS
    # 이벤트에 명시된 seating_type 만 사용 (장소 기본값 X)
    if seating_preference is not None and row["seating_type"] == seating_preference:
        score += SEATING_PREF_POINTS
    return Scored(row=row, score=score, matched_tags=matched)


def rank(
    rows: list[sqlite3.Row],
    mood_tags: list[str],
    solo_friendly: bool | None,
    seating_preference: str | None,
    limit: int = MAX_RESULTS,
) -> list[Scored]:
    """점수 내림차순 → 시작 시각 오름차순 → ID 오름차순, 최대 limit 개."""
    scored = [score_event(r, mood_tags, solo_friendly, seating_preference) for r in rows]
    scored.sort(key=lambda s: (-s.score, s.row["starts_at_utc"], s.row["id"]))
    return scored[:limit]
