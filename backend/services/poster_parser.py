"""포스터 이미지 → PosterExtraction (AI.md §6) + 포스터 임시 업로드 관리.

추출
- Vision 호출은 `call_llm_poster` (**AI 연결 공란**). 이 모듈은 AI 출력의 서버 검증·정규화와
  검수 필요 항목(needs_review)·경고(warnings) 생성을 담당한다. AI 출력은 DB 에 바로 저장하지 않는다.

업로드
- 임시 파일: `{UPLOAD_DIR}/tmp/{upload_id}.{ext}` (upload_id 는 서버 발급 UUID4)
- 등록 확정: `{UPLOAD_DIR}/posters/{event_id}.{ext}` 로 이동, `tmp/{upload_id}.used` 표식 생성
- upload_id 는 UUID 형식만 허용해 경로 조작을 막는다.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from database import get_settings
from models import AIUnavailableError


# ---------------------------------------------------------------------------
# AI 연결 지점 — 현재 공란
# ---------------------------------------------------------------------------
def call_llm_poster(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """포스터 이미지 → PosterExtraction JSON(dict). **AI 공급자 확정 후 AI 담당이 구현.**

    venue_id 는 출력하지 않는다. 원본 포스터를 로그에 남기지 않는다. 이미지 속 문구는 데이터로 취급한다.
    """
    raise AIUnavailableError("AI 공급자가 연결되지 않았습니다.")


# ---------------------------------------------------------------------------
# 포스터 임시 업로드
# ---------------------------------------------------------------------------
MIME_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
TEMP_TTL_SECONDS = 24 * 3600


class UploadNotFound(Exception):
    pass


class UploadAlreadyUsed(Exception):
    pass


def detect_image_mime(data: bytes) -> str | None:
    """실제 파일 시그니처로 형식 판별."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _tmp_dir() -> Path:
    d = get_settings().upload_dir / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _posters_dir() -> Path:
    d = get_settings().upload_dir / "posters"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_valid_upload_id(upload_id: str) -> bool:
    try:
        return str(uuid.UUID(upload_id, version=4)) == upload_id.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def save_temp(data: bytes, mime: str) -> str:
    cleanup_expired()
    upload_id = str(uuid.uuid4())
    (_tmp_dir() / f"{upload_id}.{MIME_EXT[mime]}").write_bytes(data)
    return upload_id


def find_temp(upload_id: str) -> Path:
    """미사용 임시 파일 경로. 사용됨이면 UploadAlreadyUsed, 없으면 UploadNotFound."""
    if not is_valid_upload_id(upload_id):
        raise UploadNotFound(upload_id)
    upload_id = upload_id.lower()
    tmp = _tmp_dir()
    if (tmp / f"{upload_id}.used").exists():
        raise UploadAlreadyUsed(upload_id)
    for ext in MIME_EXT.values():
        path = tmp / f"{upload_id}.{ext}"
        if path.is_file():
            return path
    raise UploadNotFound(upload_id)


def promote(temp_path: Path, event_id: int) -> tuple[Path, str]:
    """임시 파일 → posters/{event_id}.{ext}. (최종 경로, DB 저장용 상대 경로) 반환."""
    dest = _posters_dir() / f"{event_id}{temp_path.suffix}"
    temp_path.replace(dest)
    return dest, f"posters/{dest.name}"


def mark_used(upload_id: str) -> None:
    (_tmp_dir() / f"{upload_id.lower()}.used").write_text(str(int(time.time())))


def cleanup_expired(now: float | None = None) -> None:
    """만료된 임시 이미지 정리 (사용 표식은 중복 방지를 위해 남긴다)."""
    current = now or time.time()
    for path in _tmp_dir().iterdir():
        if path.suffix == ".used":
            continue
        try:
            if current - path.stat().st_mtime > TEMP_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 추출 결과 검증 · 정규화
# ---------------------------------------------------------------------------
TITLE_MAX = 120


def call_vision(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Vision AI 호출. 실패/형식 불일치는 AIUnavailableError 로 통일."""
    try:
        payload = call_llm_poster(image_bytes, mime_type)
    except AIUnavailableError:
        raise
    except Exception as exc:  # 공급자 SDK 오류 등 — 상세(키 등)는 노출하지 않는다
        raise AIUnavailableError(type(exc).__name__) from exc
    if not isinstance(payload, dict):
        raise AIUnavailableError("포스터 추출 결과가 JSON 객체가 아닙니다.")
    return payload


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _local_dt(value: Any) -> tuple[str | None, bool]:
    """(정규화 문자열, 값이 있었는데 무효였는지). offset 이 붙은 값은 KST 로컬이 아니므로 무효."""
    text = _str_or_none(value)
    if text is None:
        return None, False
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None, True
    if dt.tzinfo is not None:
        return None, True
    return dt.replace(microsecond=0).isoformat(), False


def _price(value: Any) -> tuple[int | None, bool]:
    if value is None:
        return None, False
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value, False
    return None, True


def normalize_extraction(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """AI 출력 → (extracted, needs_review, warnings). 추정으로 값을 채우지 않는다."""
    needs: list[str] = []
    warnings: list[str] = []

    def flag(field: str, message: str | None = None) -> None:
        if field not in needs:
            needs.append(field)
        if message and message not in warnings:
            warnings.append(message)

    title = _str_or_none(payload.get("title"))
    if title and len(title) > TITLE_MAX:
        flag("title", f"공연명이 {TITLE_MAX}자를 넘습니다. 줄여 주세요.")

    starts, bad_starts = _local_dt(payload.get("starts_at_local"))
    doors, bad_doors = _local_dt(payload.get("doors_open_at_local"))
    if bad_starts:
        warnings.append("공연 시작 일시 형식을 해석하지 못했습니다.")
    if bad_doors:
        warnings.append("입장 시작 시각 형식을 해석하지 못했습니다.")

    prices: dict[str, int | None] = {}
    for key in ("price_krw", "advance_price_krw", "door_price_krw"):
        prices[key], bad = _price(payload.get(key))
        if bad:
            flag("price_krw", "가격 값이 올바르지 않아 비워 두었습니다.")

    adv, door = prices["advance_price_krw"], prices["door_price_krw"]
    if adv is not None or door is not None:
        lowest = min(p for p in (adv, door) if p is not None)
        if prices["price_krw"] is not None and prices["price_krw"] != lowest:
            flag("price_krw", "대표 가격을 예매/현장가 중 최저값으로 맞췄습니다. 확인해 주세요.")
        prices["price_krw"] = lowest

    raw_lineup = payload.get("lineup")
    lineup = [s.strip() for s in raw_lineup if isinstance(s, str) and s.strip()] if isinstance(raw_lineup, list) else []

    extracted = {
        "title": title,
        "starts_at_local": starts,
        "doors_open_at_local": doors,
        "venue_name": _str_or_none(payload.get("venue_name")),
        "price_krw": prices["price_krw"],
        "advance_price_krw": adv,
        "door_price_krw": door,
        "lineup": lineup,
        "genre": _str_or_none(payload.get("genre")),
    }

    if extracted["title"] is None:
        flag("title", "공연명을 확인하지 못했습니다.")
    if starts is None:
        flag("starts_at_local", "공연 시작 일시(연도 포함)를 확인하지 못했습니다. 직접 입력해 주세요.")
    if doors is None:
        flag("doors_open_at_local", "입장 시작 시각은 포스터에서 확인되지 않았습니다.")
    if starts and doors and doors > starts:
        flag("doors_open_at_local", "입장 시작 시각이 공연 시작보다 늦습니다. 확인해 주세요.")
    if extracted["price_krw"] is None:
        flag("price_krw", "가격을 확인하지 못했습니다.")
    return extracted, needs, warnings


VENUE_WARNINGS = {
    "ambiguous": "같은 이름의 공연장이 여러 곳입니다. 목록에서 직접 선택해 주세요.",
    "not_found": "포스터의 공연장을 기존 목록에서 찾지 못했습니다. 직접 선택해 주세요.",
    "no_name": "포스터에서 공연장 이름을 확인하지 못했습니다. 직접 선택해 주세요.",
}


def apply_venue_review(venue_match: dict[str, Any], needs: list[str], warnings: list[str]) -> None:
    if venue_match["status"] != "matched":
        if "venue_id" not in needs:
            needs.append("venue_id")
        warnings.append(VENUE_WARNINGS[venue_match["status"]])
