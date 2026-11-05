"""포스터에서 추출한 공연장 이름 → 기존 venues 매칭 (AI 가 아닌 서버 로직, AI.md §7).

유사도 매칭으로 확정하지 않는다. 정규화한 이름의 **정확 일치**만 인정한다.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from typing import Any

# 무시할 일부 구두점 (공백은 별도로 제거)
_PUNCT = re.compile(r"[\s.,·•'\"`’‘“”()\[\]{}<>!?~\-_/\\:;|&@#*+=]+")


def normalize_name(name: str | None) -> str:
    """NFKC → casefold → 공백/일부 구두점 제거."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", name).casefold()
    return _PUNCT.sub("", text)


def match_venue(conn: sqlite3.Connection, venue_name: str | None) -> dict[str, Any]:
    """`venue_match` 객체 생성: matched | ambiguous | not_found | no_name."""
    target = normalize_name(venue_name)
    if not target:
        return {"status": "no_name", "venue_id": None, "candidates": []}

    rows = conn.execute("SELECT id, name, area FROM venues ORDER BY id").fetchall()
    hits = [
        {"id": r["id"], "name": r["name"], "area": r["area"]}
        for r in rows
        if normalize_name(r["name"]) == target
    ]
    if len(hits) == 1:
        return {"status": "matched", "venue_id": hits[0]["id"], "candidates": hits}
    if len(hits) > 1:
        return {"status": "ambiguous", "venue_id": None, "candidates": hits}
    return {"status": "not_found", "venue_id": None, "candidates": []}
