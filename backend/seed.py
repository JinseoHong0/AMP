"""초기 데이터 적재.

1) 실제 공연 데이터 (기본) — 저장소 루트의 엑셀 2개를 가져온다.
   - `신촌홍대_인디공연_데이터셋.xlsx` (시트 `공연목록`): 사실 정보의 1차 출처
   - `공연_상세정보_추출본.xlsx` (시트 `전체`): 데이터셋에 비어 있는 시간·가격·출연진·예매링크 보충
   - **사실 정보만** 저장한다: 공연명·일시·공연장·지역·가격·출연진·예매링크·출처URL.
     외부 사이트의 포스터 이미지 URL과 상세설명 문장은 저작권 정책(DATABASE.md §10)에 따라 저장하지 않는다.
   - `data_origin=verified`, `verified_at_utc=NULL`(검증일 미확인), `source_url`=수집 출처.
   - 제외: 뮬의 공연팀 모집·대관 글, 공연장을 특정할 수 없거나 신촌·홍대 권역 밖인 행,
     시작 시각을 확인할 수 없는 행. 두 파일의 가격이 서로 다르면 가격은 미확인(NULL)으로 둔다.

2) 가상 DEMO 시드 (`--demo`) — 공연장 4곳, 공연 23건. 테스트가 이 고정 데이터를 사용한다.
   공연 날짜는 기준일(기본: 실행일 KST)로부터의 상대 일수로 생성한다.

사용법:
    python seed.py                     # 실제 데이터 가져오기 (멱등: 이미 있는 공연장/공연은 건너뜀)
    python seed.py --reset             # 공연·공연장 전체 삭제 후 다시 가져오기
    python seed.py --dataset A.xlsx --extract B.xlsx
    python seed.py --demo [--reset] [--base-date 2026-11-06]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from database import PROJECT_DIR, connect, init_db
from models import KST, compute_price, now_utc, to_utc_str, today_kst
from services.venue_matcher import normalize_name

VENUES: list[dict] = [
    {
        "name": "샘플 라이브 클럽",
        "area": "sinchon",
        "address": "(데모) 서울 서대문구 예시로 12",
        "floor": "B1",
        "entrance_image_path": None,
        "entrance_hint_ko": "건물 정면 입구 오른쪽 계단으로 지하 1층까지 내려갑니다.",
        "entrance_hint_en": "Take the stairs on the right of the main entrance down to B1.",
        "description_ko": "(데모) 어쿠스틱 공연이 자주 열리는 소규모 좌석형 클럽 예시입니다.",
        "description_en": "(Demo) An example of a small seated club that often hosts acoustic shows.",
        "default_seating_type": "seated",
        "default_drink_policy": "공연별 확인 필요",
    },
    {
        "name": "데모 스테이지",
        "area": "hongdae",
        "address": "(데모) 서울 마포구 예시길 34",
        "floor": "B2",
        "entrance_image_path": None,
        "entrance_hint_ko": "편의점 옆 좁은 출입구로 들어가 지하 2층으로 내려갑니다.",
        "entrance_hint_en": None,  # 영문 미검수 → FE 는 원문 + 미확인 표시
        "description_ko": "(데모) 록·펑크 공연 위주의 스탠딩 공연장 예시입니다.",
        "description_en": None,
        "default_seating_type": "standing",
        "default_drink_policy": "1드링크 포함(공연장 기본, 공연별 확인 필요)",
    },
    {
        "name": "모노 사운드홀",
        "area": "sinchon",
        "address": "(데모) 서울 서대문구 샘플로 56",
        "floor": "2F",
        "entrance_image_path": None,
        "entrance_hint_ko": "건물 뒤편 엘리베이터로 2층에 올라갑니다.",
        "entrance_hint_en": "Use the elevator at the back of the building to the 2nd floor.",
        "description_ko": "(데모) 좌석과 스탠딩 구역이 함께 있는 공연장 예시입니다.",
        "description_en": "(Demo) An example venue with both seated and standing areas.",
        "default_seating_type": "mixed",
        "default_drink_policy": None,
    },
    {
        "name": "블루 앰프 라운지",
        "area": "hongdae",
        "address": "(데모) 서울 마포구 데모로 78",
        "floor": "B1",
        "entrance_image_path": None,
        "entrance_hint_ko": "파란 간판 아래 입구로 들어가 지하 1층으로 내려갑니다.",
        "entrance_hint_en": "Enter under the blue sign and go down to B1.",
        "description_ko": "(데모) 재즈·시티팝 공연이 열리는 라운지형 공연장 예시입니다.",
        "description_en": "(Demo) An example lounge venue for jazz and city-pop shows.",
        "default_seating_type": "seated",
        "default_drink_policy": "음료 주문 권장(공연장 기본, 공연별 확인 필요)",
    },
]

# (공연장 index, 제목, 기준일+N, 시작 HH:MM, 공연 길이(분)|None, 입장 시작(시작 N분 전)|None,
#  단일가, 예매가, 현장가, 라인업, 장르, 분위기, 혼자, 좌석형태, 좌석배정, 드링크, 설명ko, 설명en,
#  입장안내ko, 입장안내en, 상태)
EVENTS: list[tuple] = [
    (0, "밤의 산책", 1, "19:00", 120, 30, None, 15000, 20000, ["Sample Band A"], "indie",
     ["calm", "acoustic"], True, "seated", "unassigned", "공연별 안내 확인 필요",
     "어쿠스틱 중심의 소규모 공연입니다.", "A small-scale acoustic show.",
     "좌석은 비지정석입니다. 선착순으로 입장합니다.", "Unassigned seating. Entry is first come, first served.",
     "published"),
    (0, "어쿠스틱 선데이", 1, "21:00", 90, 30, 18000, None, None, ["Demo Duo"], "acoustic",
     ["acoustic", "romantic"], None, "seated", "assigned", None,
     "두 명의 기타리스트가 꾸미는 공연입니다.", None, "지정석 번호는 입장 시 안내됩니다.", None, "published"),
    (2, "새벽 네온", 1, "20:00", 150, 60, None, 20000, 25000, ["Neon Sample", "Demo Lights"], "synth-pop",
     ["energetic"], True, "mixed", None, "1드링크 포함",
     "신스팝 밴드 두 팀의 합동 공연입니다.", "A joint show of two synth-pop bands.", None, None, "published"),
    (2, "모노 포크 나잇", 1, "18:00", 90, None, None, None, None, ["Folk Sample"], "folk",
     ["calm"], True, "seated", None, None, "포크 싱어송라이터 공연입니다.", None, None, None, "published"),
    (1, "홍대 록 파티", 1, "20:00", 180, 30, None, None, 25000, ["Rock Demo", "Sample Riot"], "rock",
     ["energetic"], None, "standing", None, "1드링크 포함", "록 밴드 세 팀의 공연입니다.", None,
     "재입장 불가 공연입니다.", None, "published"),
    (3, "블루 재즈 데이트", 1, "19:30", 120, 30, None, 20000, 20000, ["Jazz Sample Trio"], "jazz",
     ["romantic", "calm"], False, "seated", "assigned", "음료 1잔 주문 필수",
     "재즈 트리오의 저녁 공연입니다.", "An evening show by a jazz trio.",
     "지정석입니다.", "Assigned seating.", "published"),
    (3, "라운지 언플러그드", 1, "17:00", 90, None, 0, None, None, ["Unplugged Demo"], "acoustic",
     ["acoustic", "calm"], True, None, None, None, "무료 언플러그드 공연입니다.", "A free unplugged show.",
     None, None, "published"),
    (1, "인디 쇼케이스", 1, "22:00", 120, 30, None, 12000, 15000, ["Demo Rookies"], "indie",
     ["energetic"], True, "standing", None, None, "신인 밴드 쇼케이스입니다.", None, None, None, "published"),
    (0, "오늘의 무대", 0, "20:00", 90, 30, 10000, None, None, ["Today Sample"], "indie",
     ["calm"], True, "seated", "unassigned", None, "오늘 저녁 소규모 공연입니다.", None, None, None, "published"),
    (1, "오늘 밤 펑크", 0, "21:00", 120, 30, None, None, 15000, ["Punk Demo"], "punk",
     ["energetic"], None, "standing", None, "1드링크 포함", "펑크 밴드 공연입니다.", None, None, None, "published"),
    (2, "주말 오후 콘서트", 2, "15:00", 120, 30, None, 25000, 30000, ["Afternoon Sample"], "pop",
     ["romantic"], None, "mixed", None, None, "주말 오후 공연입니다.", None, None, None, "published"),
    (3, "시티팝 나이트", 2, "20:00", 120, 30, 20000, None, None, ["City Demo"], "city-pop",
     ["romantic", "energetic"], None, "seated", "unassigned", None, "시티팝 공연입니다.", "A city-pop show.",
     None, None, "published"),
    (0, "기타 솔로 리사이틀", 2, "19:00", 90, 30, None, 18000, None, ["Solo Guitar Demo"], "acoustic",
     ["acoustic", "calm"], True, "seated", "assigned", None, "기타 독주 공연입니다.", None,
     "지정석입니다.", "Assigned seating.", "published"),
    (1, "신인 밴드 경연", 3, "19:00", 180, 30, 0, None, None, ["Demo Contest"], "rock",
     ["energetic"], None, "standing", None, None, "무료 신인 밴드 경연입니다.", None, None, None, "published"),
    (2, "감성 듀오", 3, "20:00", 90, 30, 22000, None, None, ["Mood Duo Demo"], "indie",
     ["romantic", "calm"], None, "mixed", None, None, "듀오 공연입니다.", None, None, None, "published"),
    (3, "포스트록 저녁", 3, "20:00", 120, 30, None, 23000, 28000, ["Post Demo"], "post-rock",
     ["calm"], None, "standing", None, None, "포스트록 공연입니다.", None, None, None, "published"),
    (0, "겨울 노래", 4, "19:30", 90, 30, 16000, None, None, ["Winter Sample"], "indie",
     ["calm", "acoustic"], True, "seated", "unassigned", None, "겨울 테마 공연입니다.", None,
     None, None, "published"),
    (1, "그런지 리바이벌", 5, "20:00", 120, 30, None, 19000, 24000, ["Grunge Demo"], "rock",
     ["energetic"], None, "standing", None, "1드링크 포함", "그런지 공연입니다.", None, None, None, "published"),
    (3, "밤산책 재즈", 6, "19:00", 120, None, None, None, None, ["Night Jazz Demo"], "jazz",
     ["romantic"], None, "seated", None, None, "재즈 공연입니다.", None, None, None, "published"),
    (2, "피아노 라이브", 6, "18:00", 90, 30, None, 17000, None, ["Piano Demo"], "piano",
     ["calm"], True, "seated", "unassigned", None, "피아노 공연입니다.", None, None, None, "published"),
    # 공개 추천에 나오면 안 되는 데이터 (지난 공연 / 초안 / 취소)
    (0, "지난 공연", -1, "19:00", 90, 30, 10000, None, None, ["Past Demo"], "indie",
     ["calm"], True, "seated", None, None, "이미 끝난 공연입니다.", None, None, None, "published"),
    (1, "준비 중 공연", 1, "19:00", 90, 30, 10000, None, None, ["Draft Demo"], "indie",
     ["calm"], True, "seated", None, None, "초안 공연입니다.", None, None, None, "draft"),
    (3, "취소된 공연", 1, "19:00", 90, 30, 10000, None, None, ["Cancelled Demo"], "indie",
     ["calm"], True, "seated", None, None, "취소된 공연입니다.", None, None, None, "cancelled"),
]


def _kst(day: date, hhmm: str) -> datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hh, mm), tzinfo=KST)


def seed(conn: sqlite3.Connection, base_date: date | None = None, reset: bool = False) -> dict[str, int]:
    base = base_date or today_kst()
    now = to_utc_str(now_utc())
    if reset:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM venues")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('events','venues')")

    venue_ids: list[int] = []
    for v in VENUES:
        row = conn.execute("SELECT id FROM venues WHERE name = ?", (v["name"],)).fetchone()
        if row:
            venue_ids.append(row["id"])
            continue
        cur = conn.execute(
            """INSERT INTO venues (name, area, address, floor, entrance_image_path, entrance_hint_ko,
               entrance_hint_en, description_ko, description_en, default_seating_type, default_drink_policy,
               source_url, verified_at_utc, data_origin)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,'demo')""",
            (v["name"], v["area"], v["address"], v["floor"], v["entrance_image_path"], v["entrance_hint_ko"],
             v["entrance_hint_en"], v["description_ko"], v["description_en"], v["default_seating_type"],
             v["default_drink_policy"]),
        )
        venue_ids.append(cur.lastrowid)

    inserted = 0
    for (vi, title, offset, hhmm, duration, doors_before, price, adv, door, lineup, genre, moods, solo,
         seating, assign, drink, desc_ko, desc_en, notes_ko, notes_en, status) in EVENTS:
        venue_id = venue_ids[vi]
        exists = conn.execute(
            "SELECT 1 FROM events WHERE venue_id = ? AND title = ?", (venue_id, title)
        ).fetchone()
        if exists:
            continue
        starts = _kst(base + timedelta(days=offset), hhmm)
        ends = starts + timedelta(minutes=duration) if duration else None
        doors = starts - timedelta(minutes=doors_before) if doors_before else None
        price_krw, basis = compute_price(price, adv, door)
        conn.execute(
            """INSERT INTO events (venue_id, title, starts_at_utc, ends_at_utc, doors_open_at_utc, price_krw,
               price_basis, advance_price_krw, door_price_krw, booking_url, lineup_json, genre, mood_tags_json,
               solo_friendly, seating_type, seat_assignment, drink_policy, description_ko, description_en,
               admission_notes_ko, admission_notes_en, poster_image_path, status, data_origin, source_url,
               verified_at_utc, created_at_utc, updated_at_utc)
               VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,NULL,?,'demo',NULL,NULL,?,?)""",
            (venue_id, title, to_utc_str(starts), to_utc_str(ends) if ends else None,
             to_utc_str(doors) if doors else None, price_krw, basis, adv, door,
             json.dumps(lineup, ensure_ascii=False), genre, json.dumps(moods),
             None if solo is None else int(solo), seating, assign, drink, desc_ko, desc_en,
             notes_ko, notes_en, status, now, now),
        )
        inserted += 1

    conn.commit()
    return {
        "venues": conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0],
        "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "inserted_events": inserted,
    }


# ===========================================================================
# 실제 공연 데이터 (엑셀) 가져오기
# ===========================================================================
DATASET_PATH = PROJECT_DIR / "신촌홍대_인디공연_데이터셋.xlsx"
EXTRACT_PATH = PROJECT_DIR / "공연_상세정보_추출본.xlsx"
DATASET_SHEET = "공연목록"
EXTRACT_SHEET = "전체"

# 공연장 정규 이름 → (지역, 원본 표기 별칭). 지역은 데이터셋 `지역` 열(홍대·상수·연남=hongdae,
# 신촌·이대·서대문=sinchon)과 게시글의 주소/제목으로 확인했다. 목록에 없는 공연장의 행은 가져오지 않는다.
VENUE_TABLE: dict[str, tuple[str, list[str]]] = {
    "Club FF": ("hongdae", ["클럽FF", "홍대 클럽 FF"]),
    "롤링홀": ("hongdae", []),
    "클럽에반스": ("hongdae", []),
    "우주정거장": ("hongdae", ["홍대 우주정거장"]),
    "생기스튜디오": ("hongdae", ["홍대 생기스튜디오"]),
    "우무지": ("hongdae", []),
    "채널1969": ("hongdae", []),
    "Club Victim": ("hongdae", []),
    "스트레인지 프룻": ("hongdae", []),
    "무신사개러지": ("hongdae", []),
    "Club 빵": ("hongdae", []),
    "A.O.R": ("hongdae", ["홍대 클럽 A.O.R (All Of Rock"]),
    "웨스트브릿지 라이브홀": ("hongdae", []),
    "스페이스 한강": ("hongdae", ["홍대 스페이스 한강"]),
    "살롱문보우": ("hongdae", []),
    "프리버드": ("hongdae", ["클럽 프리버드 CLUB FREEBIRD [주소:서울시 마포구 와우산로17"]),
    "벨르(구 벨로주)": ("hongdae", []),
    "KT&G 상상마당 홍대 라이브홀": ("hongdae", []),
    "언플러그드 라운지": ("hongdae", []),
    "공상온도": ("hongdae", []),
    "아지토 라이브홀": ("sinchon", ["아지토 라이브 홀", "신촌 아지토 라이브홀",
                                "AZITO LIVEHALL (서울 서대문구 신촌역로 13 세오빌딩 지하"]),
    # 뮬 게시글에만 등장하는 공연장 (게시글의 주소·제목으로 권역 확인)
    "스팀펑크락": ("sinchon", ["스팀펑크락 (서대문구 연세로9길 13, 신촌"]),
    "몽향": ("sinchon", ["신촌 몽향", "신촌 복합문화공간 몽향 🎵"]),
    "롤러코스터": ("hongdae", []),
    "구름아래소극장": ("hongdae", ["｜구름아래소극장 주소｜서울특별시 마포구 와우산로29가길 15 관람료｜무료"]),
    "Joons 준스바": ("hongdae", ["Joons 준스바 (서울 마포구 와우산로19길 6-11 지하 1층"]),
    "스페이스 브릭": ("hongdae", ["서울 마포구 잔다리로 31 지하2층 '스페이스 브릭'"]),
}
# 데이터에 **명시된** 주소·층수만 (공연장 열 또는 추출본 문장 그대로). 없거나 잘린 주소는 NULL 로 둔다.
VENUE_DETAILS: dict[str, tuple[str, str | None]] = {
    "클럽에반스": ("서울시 마포구 와우산로 63 2층", "2F"),
    "아지토 라이브홀": ("서울 서대문구 신촌역로 13 세오빌딩 지하", None),
    "스팀펑크락": ("서대문구 연세로9길 13", None),
    "구름아래소극장": ("서울특별시 마포구 와우산로29가길 15", None),
    "Joons 준스바": ("서울 마포구 와우산로19길 6-11 지하 1층", "B1"),
    "스페이스 브릭": ("서울 마포구 잔다리로 31 지하2층", "B2"),
}
_VENUE_ALIASES: dict[str, str] = {}
for _canon, (_area, _aliases) in VENUE_TABLE.items():
    for _alias in [_canon, *_aliases]:
        _VENUE_ALIASES[normalize_name(_alias)] = _canon

# 관객 대상 공연이 아닌 글(공연팀 모집·대관·양도)
_RECRUIT = re.compile(
    r"모집|구합니다|구해요|구인|찾습니다|모십니다|모셔|양도|대관|함께\s*하실|같이\s*하실|공연하실"
    r"|하실\s*(?:분|팀|밴드)|팀\s*구"
)
_AMOUNT = re.compile(r"₩\s*(\d[\d,]*)|(\d[\d,]*)\s*원")
_TIME_TOKEN = r"(오전|오후)?\s*(\d{1,2})(?::(\d{2})|\s*시(?:\s*(\d{1,2})\s*분)?)\s*(AM|PM|am|pm)?"
_URL = re.compile(r"https?://[^\s|]+")
MIN_PRICE, MAX_PRICE = 100, 1_000_000  # 이 범위 밖 금액은 대관비·오기로 보고 무시


def canonical_venue(raw: str | None) -> str | None:
    return _VENUE_ALIASES.get(normalize_name(raw)) if raw else None


def is_recruitment(title: str, note: str = "") -> bool:
    return bool(_RECRUIT.search(title or "")) or "모집글" in (note or "")


def parse_price(text: str | None) -> tuple[int | None, int | None, int | None] | None:
    """가격 문자열 → (단일가, 예매가, 현장가). 가격 정보가 없으면 None.

    - '예매 25,000원 / 현장 30,000원' → (None, 25000, 30000)
    - '현장 35,000원' → (None, None, 35000) / '55,000원' · '77,000원부터' → (55000, None, None)
    - '1층 132,000원, 2층 121,000원' · '₩49,000 – ₩60,000' → 최저 명시가를 단일가로
    - '무료' → (0, None, None) / '예매 정보는 추후 안내 예정' · '티켓 없음' → None
    """
    if not text or not str(text).strip():
        return None
    text = str(text).strip()
    general: list[int] = []
    advance: list[int] = []
    door: list[int] = []
    for segment in re.split(r"\s*/\s*|;\s*|,\s+", text):
        amounts = [int((a or b).replace(",", "")) for a, b in _AMOUNT.findall(segment)]
        amounts = [a for a in amounts if MIN_PRICE <= a < MAX_PRICE]
        if not amounts:
            continue
        if any(k in segment for k in ("현장", "현매", "당일")):
            door.extend(amounts)
        elif "예매" in segment:
            advance.extend(amounts)
        else:
            general.extend(amounts)
    if advance or door:
        return None, min(advance) if advance else None, min(door) if door else None
    if general:
        return min(general), None, None
    if "무료" in text or text.lower() == "free":
        return 0, None, None
    return None


def _hm(hour: str, minute: str | None, ampm: str | None) -> time | None:
    h, m = int(hour), int(minute or 0)
    marker = (ampm or "").lower()
    if marker in ("오후", "pm") and h < 12:
        h += 12
    elif marker in ("오전", "am") and h == 12:
        h = 0
    return time(h, m) if 0 <= h < 24 and 0 <= m < 60 else None


def _token_time(match: re.Match, context_pm: bool = False) -> time | None:
    """_TIME_TOKEN 일치 → time. 'N시'처럼 오전/오후가 없는 12 미만 시각은 문맥(입장 오후)이 있을 때만 오후로."""
    ampm_ko, hour, mm_colon, mm_ko, ampm_en = match.groups()
    marker = ampm_ko or ampm_en
    if marker is None and mm_colon is None and int(hour) < 12:
        if not context_pm:
            return None  # '8시' 단독은 오전/오후를 알 수 없음
        marker = "오후"
    return _hm(hour, mm_colon or mm_ko, marker)


def parse_time(text: str | None, title: str = "") -> tuple[time | None, time | None, time | None]:
    """시간 문자열 → (시작, 입장 시작, 종료). 확인할 수 없는 값은 None (추정하지 않음)."""
    text = (str(text) if text is not None else "").strip()
    start = doors = end = None
    if text:
        simple = re.fullmatch(r"(\d{1,2}):(\d{2})\s*(?:[-~–]\s*(\d{1,2}):(\d{2}))?", text)
        if simple:
            start = _hm(simple[1], simple[2], None)
            if simple[3]:
                end = _hm(simple[3], simple[4], None)
        else:
            rest = text
            dm = re.search(r"입장\s*" + _TIME_TOKEN, rest) or re.search(r"\(\s*" + _TIME_TOKEN + r"\s*입장", rest)
            if dm:
                inner = re.search(_TIME_TOKEN, dm.group(0))
                doors = _token_time(inner, context_pm=True) if inner else None
                rest = rest[: dm.start()] + rest[dm.end():]
            context_pm = doors is not None and doors.hour >= 12
            sm = re.search(r"1부\s*" + _TIME_TOKEN, rest)
            if sm:
                start = _token_time(re.search(_TIME_TOKEN, sm.group(0)), context_pm)
            else:
                for m in re.finditer(_TIME_TOKEN, rest):
                    start = _token_time(m, context_pm)
                    if start:
                        break
    if start is None and title:
        tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(pm|PM|am|AM)\b", title)
        if tm:
            start = _hm(tm[1], tm[2], tm[3])
    if start and doors and doors > start:
        doors = None
    if start and end and end <= start:
        end = None
    return start, doors, end


def parse_lineup(primary: str | None, fallback: str | None) -> list[str]:
    """데이터셋 값 우선, 없으면 추출본. ';'가 있으면 ';', 없으면 ','로 구분. 안내문이 섞인 값은 버린다."""
    for text in (primary, fallback):
        if text and str(text).strip():
            text = str(text)
            items = [s.strip() for s in text.split(";" if ";" in text else ",") if s.strip()]
            if any(len(s) > 60 or _RECRUIT.search(s) or "\n" in s for s in items):
                return []
            return list(dict.fromkeys(items))
    return []


def first_url(*values: str | None) -> str | None:
    for value in values:
        m = _URL.search(str(value or ""))
        if m:
            return m.group(0)
    return None


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value).strip()


def read_sheet(path: Path, sheet: str) -> list[dict[str, str]]:
    from openpyxl import load_workbook  # 가져오기 때만 필요

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = wb[sheet].iter_rows(values_only=True)
        header = [_cell(h) for h in next(rows)]
        return [dict(zip(header, (_cell(v) for v in row))) for row in rows if any(v is not None for v in row)]
    finally:
        wb.close()


@dataclass
class ImportReport:
    rows: int = 0
    imported: int = 0
    already_present: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    price_conflicts: int = 0
    venues_created: int = 0

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row.get("공연명", ""), row.get("날짜", ""), row.get("공연장", "")


def import_dataset(
    conn: sqlite3.Connection,
    dataset_path: Path = DATASET_PATH,
    extract_path: Path | None = EXTRACT_PATH,
    reset: bool = False,
) -> ImportReport:
    """엑셀 → venues/events. 멱등: (공연장, 공연명, 시작 시각)이 같으면 건너뛴다."""
    dataset = read_sheet(dataset_path, DATASET_SHEET)
    extract = {}
    if extract_path is not None and Path(extract_path).exists():
        extract = {_row_key(r): r for r in read_sheet(extract_path, EXTRACT_SHEET)}

    if reset:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM venues")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('events','venues')")

    report = ImportReport(rows=len(dataset))
    now = to_utc_str(now_utc())
    venue_ids: dict[str, int] = {}

    def venue_id_for(name: str, source_url: str | None) -> int:
        if name in venue_ids:
            return venue_ids[name]
        row = conn.execute("SELECT id FROM venues WHERE name = ?", (name,)).fetchone()
        if row:
            venue_ids[name] = row["id"]
        else:
            venue_page = source_url if source_url and "/venues/" in source_url else None
            address, floor = VENUE_DETAILS.get(name, (None, None))
            cur = conn.execute(
                "INSERT INTO venues (name, area, address, floor, source_url, verified_at_utc, data_origin) "
                "VALUES (?, ?, ?, ?, ?, NULL, 'verified')",
                (name, VENUE_TABLE[name][0], address, floor, venue_page),
            )
            venue_ids[name] = cur.lastrowid
            report.venues_created += 1
        return venue_ids[name]

    for row in dataset:
        ex = extract.get(_row_key(row), {})
        title = row.get("공연명", "").strip()
        if not title:
            report.skip("공연명 없음")
            continue
        if is_recruitment(title, ex.get("비고", "")):
            report.skip("공연팀 모집·대관 글")
            continue
        venue = canonical_venue(row.get("공연장"))
        if venue is None:
            report.skip("공연장 미확인·권역 밖")
            continue
        try:
            day = date.fromisoformat(row.get("날짜", "")[:10])
        except ValueError:
            report.skip("날짜 형식 오류")
            continue

        # 시간: 데이터셋 우선. 추출본의 입장 시각은 시작 시각이 같거나 추출본에 시작이 없을 때만 보충한다.
        start, doors, end = parse_time(row.get("시간"), "")
        ex_start, ex_doors, ex_end = parse_time(ex.get("시간"), title)
        if start is None:
            start, doors, end = ex_start, ex_doors, ex_end
        elif doors is None and ex_doors is not None and ex_start in (None, start) and ex_doors <= start:
            doors = ex_doors
        if start is None:
            report.skip("시작 시각 미확인")
            continue
        if time(5) <= start < time(10):
            # 공연 데이터의 05~09시 시작은 12시간제 표기 오류(예: '7시'→07:00)로 확인됨 → 추정하지 않고 제외
            report.skip("시작 시각 의심(오전 5~10시)")
            continue

        # 가격: 데이터셋 우선, 비어 있으면 추출본. 둘 다 있는데 최저가가 다르면 미확인으로 둔다.
        p_main, p_extra = parse_price(row.get("가격")), parse_price(ex.get("가격"))
        parsed = p_main or p_extra
        if p_main and p_extra and compute_price(*p_main)[0] != compute_price(*p_extra)[0]:
            report.price_conflicts += 1
            parsed = None
        price_krw, basis = compute_price(*parsed) if parsed else (None, None)
        advance, door = (parsed[1], parsed[2]) if parsed else (None, None)

        source_url = first_url(row.get("출처URL"), ex.get("출처URL"))
        venue_id = venue_id_for(venue, source_url)
        starts_utc = to_utc_str(datetime.combine(day, start, tzinfo=KST))
        if conn.execute(
            "SELECT 1 FROM events WHERE venue_id = ? AND title = ? AND starts_at_utc = ?",
            (venue_id, title[:120], starts_utc),
        ).fetchone():
            report.already_present += 1
            continue

        conn.execute(
            """INSERT INTO events (venue_id, title, starts_at_utc, ends_at_utc, doors_open_at_utc, price_krw,
               price_basis, advance_price_krw, door_price_krw, booking_url, lineup_json, genre, mood_tags_json,
               solo_friendly, seating_type, seat_assignment, drink_policy, description_ko, description_en,
               admission_notes_ko, admission_notes_en, poster_image_path, status, data_origin, source_url,
               verified_at_utc, created_at_utc, updated_at_utc)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,'[]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
                       'published','verified',?,NULL,?,?)""",
            (venue_id, title[:120], starts_utc,
             to_utc_str(datetime.combine(day, end, tzinfo=KST)) if end else None,
             to_utc_str(datetime.combine(day, doors, tzinfo=KST)) if doors else None,
             price_krw, basis, advance, door,
             first_url(row.get("예매링크"), ex.get("예매링크")),
             json.dumps(parse_lineup(row.get("출연진"), ex.get("출연진")), ensure_ascii=False),
             source_url, now, now),
        )
        report.imported += 1

    conn.commit()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="AMP 초기 데이터 적재")
    parser.add_argument("--demo", action="store_true", help="실제 데이터 대신 가상 DEMO 시드 사용")
    parser.add_argument("--reset", action="store_true", help="기존 공연·공연장을 삭제 후 재생성")
    parser.add_argument("--base-date", type=date.fromisoformat, default=None, help="(--demo) KST 기준일 YYYY-MM-DD")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH, help="공연 데이터셋 엑셀 경로")
    parser.add_argument("--extract", type=Path, default=EXTRACT_PATH, help="상세정보 추출본 엑셀 경로")
    args = parser.parse_args()
    init_db()
    conn = connect()
    try:
        if args.demo:
            result = seed(conn, base_date=args.base_date, reset=args.reset)
            print(f"DEMO seed 완료: venues={result['venues']} events={result['events']} "
                  f"(신규 {result['inserted_events']}건)")
            return
        report = import_dataset(conn, args.dataset, args.extract, reset=args.reset)
        total_v = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
        total_e = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()
    print(f"데이터셋 {report.rows}행 → 신규 공연 {report.imported}건, 이미 있음 {report.already_present}건, "
          f"신규 공연장 {report.venues_created}곳, 가격 충돌(미확인 처리) {report.price_conflicts}건")
    for reason, count in sorted(report.skipped.items(), key=lambda kv: -kv[1]):
        print(f"  제외 - {reason}: {count}건")
    print(f"DB 합계: venues={total_v} events={total_e}")


if __name__ == "__main__":
    main()
