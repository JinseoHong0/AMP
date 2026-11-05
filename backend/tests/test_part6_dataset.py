"""6단계: 실제 공연 데이터(엑셀) 가져오기 — 파서 단위, 병합 규칙, 실제 파일 연동."""
from __future__ import annotations

import json
from datetime import time

import pytest
from fastapi.testclient import TestClient

import seed

DS_HEADER = ["출처사이트", "출처URL", "공연명", "날짜", "시간", "공연장", "지역", "출연진", "가격", "예매링크", "게시일"]
EX_HEADER = ["공연명", "날짜", "공연장", "출처사이트", "출처URL", "추출상태", "상세설명", "출연진", "시간", "가격",
             "예매링크", "문의", "포스터URL", "비고"]


# ---------- 파서 단위 ----------
@pytest.mark.parametrize(
    "text, expected",
    [
        ("예매 25,000원 / 현장 30,000원", (None, 25000, 30000)),
        ("예매 55,000원 / 당일 현장구매 66,000원", (None, 55000, 66000)),
        ("예매 40,000원 / 현장 45,000원 (현매는 잔여석에 한함 / 청소년 할인 40% 적용)", (None, 40000, 45000)),
        ("현장 35,000원", (None, None, 35000)),
        ("예매 66,000원", (None, 66000, None)),
        ("55,000원", (55000, None, None)),
        ("77,000원부터", (77000, None, None)),
        ("₩49,000 – ₩60,000", (49000, None, None)),
        ("1층 132,000원, 2층 121,000원", (121000, None, None)),
        ("₩30,000 [+1 FREE DRINK] (현장결제만 가능 - 현금, 카드)", (None, None, 30000)),
        ("무료", (0, None, None)),
        ("예매 정보는 추후 안내 예정", None),
        ("티켓 없음", None),
        ("1원", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_price(text, expected):
    assert seed.parse_price(text) == expected


@pytest.mark.parametrize(
    "text, title, expected",
    [
        ("19:30", "", (time(19, 30), None, None)),
        ("20:00-20:50", "", (time(20), None, time(20, 50))),
        ("23:00", "", (time(23), None, None)),
        ("11.07 토 17:00", "", (time(17), None, None)),
        ("오후 8시", "", (time(20), None, None)),
        ("오후 7시 30분", "", (time(19, 30), None, None)),
        ("입장 오후 7시; 1부 8시 - 8시 50분; 2부 9시 20분 - 10시 10분", "", (time(20), time(19), None)),
        ("1부 20:00~20:50; 2부 21:00~22:10; 8:00 PM ~ 10:10 PM", "", (time(20), None, None)),
        ("8:00 PM ~ 10:10 PM; 매일", "", (time(20), None, None)),
        ("10월 4일 (일) 오후 4시~ 6시 (3시 10분 입장)", "", (time(16), time(15, 10), None)),
        ("8시", "", (None, None, None)),  # 오전/오후 불명 → 추정하지 않음
        ("", "IN MATE STAGE 공연 안내 - 10월 5일(월) 7:30pm", (time(19, 30), None, None)),
        ("", "제목에 시각 없음", (None, None, None)),
    ],
)
def test_parse_time(text, title, expected):
    assert seed.parse_time(text, title) == expected


def test_parse_lineup():
    assert seed.parse_lineup("A; B; A", "") == ["A", "B"]
    assert seed.parse_lineup("더 스미어, 김영석밴드", "") == ["더 스미어", "김영석밴드"]
    assert seed.parse_lineup("", "X, Y") == ["X", "Y"]
    assert seed.parse_lineup("연합 공연 함께하실 팀 모십니다!", "") == []
    assert seed.parse_lineup("총 4팀 " + "가" * 80, "") == []
    assert seed.parse_lineup(None, None) == []


def test_canonical_venue_and_recruitment():
    assert seed.canonical_venue("클럽FF") == "Club FF"
    assert seed.canonical_venue("Club FF") == "Club FF"
    assert seed.canonical_venue("아지토 라이브 홀") == "아지토 라이브홀"
    assert seed.canonical_venue("AZITO LIVEHALL (서울 서대문구 신촌역로 13 세오빌딩 지하") == "아지토 라이브홀"
    assert seed.canonical_venue("아지토") is None  # 모호한 약칭은 확정하지 않음
    assert seed.canonical_venue("┃ 인천아트플랫폼 C동 공연장") is None  # 권역 밖
    assert seed.canonical_venue(None) is None
    assert seed.is_recruitment("11월 8일 홍대 연합 공연 함께 할 1팀 찾습니다!")
    assert seed.is_recruitment("[홍대/무료대관] 평일 저녁 미니콘서트 대관료 0원 지원")
    assert seed.is_recruitment("아무 제목", "모집글(관객 가격 미기재 가능)")
    assert not seed.is_recruitment("ADYNE SOLO CONCERT ‘ANOTHER WAY’")


# ---------- 합성 엑셀로 병합 규칙 ----------
def _write_xlsx(path, sheet, header, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(header)
    for r in rows:
        ws.append([r.get(h) for h in header])
    wb.save(path)


@pytest.fixture()
def tiny_files(tmp_path):
    ds_rows = [
        # 1) 데이터셋 시간 + 추출본 입장 시각 보충, 예매/현장가
        {"출처사이트": "클럽에반스", "출처URL": "https://example.com/evans", "공연명": "재즈 나잇", "날짜": "2026-11-07",
         "시간": "20:00", "공연장": "클럽에반스", "지역": "Hongdae", "출연진": "A; B",
         "가격": "예매 25,000원 / 현장 30,000원"},
        # 2) 데이터셋 가격 없음 → 추출본 가격·예매링크 보충
        {"출처사이트": "인디스트릿", "출처URL": "https://indistreet.com/venues/hongdaeff", "공연명": "보충 공연",
         "날짜": "2026-11-08", "시간": "19:30", "공연장": "클럽FF", "지역": "홍대"},
        # 3) 두 파일 가격 충돌 → 미확인
        {"출처사이트": "뮬", "출처URL": "https://www.mule.co.kr/x", "공연명": "IN MATE STAGE 공연 안내 - 11월 9일 8pm",
         "날짜": "2026-11-09", "공연장": "아지토 라이브홀", "지역": "신촌", "가격": "무료"},
        # 4) 모집글 → 제외
        {"출처사이트": "뮬", "공연명": "11월 10일 같이 공연할 팀 모집합니다", "날짜": "2026-11-10",
         "공연장": "우주정거장", "지역": "홍대"},
        # 5) 모르는 공연장 → 제외
        {"출처사이트": "뮬", "공연명": "인천 공연", "날짜": "2026-11-11", "시간": "19:00", "공연장": "인천아트플랫폼",
         "지역": "인천"},
        # 6) 시간 없음 → 제외
        {"출처사이트": "인디스트릿", "공연명": "시간 미상", "날짜": "2026-11-12", "공연장": "우무지", "지역": "상수"},
    ]
    ex_rows = [
        {"공연명": "재즈 나잇", "날짜": "2026-11-07", "공연장": "클럽에반스", "시간": "입장 오후 7시; 1부 8시 - 8시 50분",
         "상세설명": "복사된 홍보 문장", "포스터URL": "https://cdn.example.com/p.jpg"},
        {"공연명": "보충 공연", "날짜": "2026-11-08", "공연장": "클럽FF", "가격": "15,000원",
         "예매링크": "https://tickets.example.com/1 | https://other.example.com", "출연진": "X, Y"},
        {"공연명": "IN MATE STAGE 공연 안내 - 11월 9일 8pm", "날짜": "2026-11-09", "공연장": "아지토 라이브홀",
         "가격": "30000원", "시간": "오후 8시"},
    ]
    ds_path, ex_path = tmp_path / "ds.xlsx", tmp_path / "ex.xlsx"
    _write_xlsx(ds_path, seed.DATASET_SHEET, DS_HEADER, ds_rows)
    _write_xlsx(ex_path, seed.EXTRACT_SHEET, EX_HEADER, ex_rows)
    return ds_path, ex_path


@pytest.fixture()
def empty_db(env):
    from database import connect, init_db

    init_db()
    conn = connect()
    yield conn
    conn.close()


def _event(conn, title):
    return conn.execute(
        "SELECT e.*, v.name AS venue_name, v.area AS venue_area FROM events e JOIN venues v ON v.id = e.venue_id "
        "WHERE e.title = ?", (title,)
    ).fetchone()


def test_import_merge_rules(empty_db, tiny_files):
    report = seed.import_dataset(empty_db, *tiny_files)
    assert report.rows == 6 and report.imported == 3
    assert report.skipped == {"공연팀 모집·대관 글": 1, "공연장 미확인·권역 밖": 1, "시작 시각 미확인": 1}
    assert report.price_conflicts == 1

    jazz = _event(empty_db, "재즈 나잇")
    assert jazz["starts_at_utc"] == "2026-11-07T11:00:00Z"
    assert jazz["doors_open_at_utc"] == "2026-11-07T10:00:00Z"  # 추출본 '입장 오후 7시' 보충
    assert (jazz["price_krw"], jazz["price_basis"], jazz["advance_price_krw"], jazz["door_price_krw"]) == \
        (25000, "advance", 25000, 30000)
    assert json.loads(jazz["lineup_json"]) == ["A", "B"]
    # 사실 정보만: 포스터·상세설명은 저장하지 않음
    assert jazz["poster_image_path"] is None and jazz["description_ko"] is None
    assert jazz["data_origin"] == "verified" and jazz["verified_at_utc"] is None
    assert jazz["source_url"] == "https://example.com/evans" and jazz["status"] == "published"

    filled = _event(empty_db, "보충 공연")
    assert filled["venue_name"] == "Club FF"  # '클럽FF' 표기 통일
    assert (filled["price_krw"], filled["price_basis"]) == (15000, "general")
    assert filled["booking_url"] == "https://tickets.example.com/1"
    assert json.loads(filled["lineup_json"]) == ["X", "Y"]

    conflict = _event(empty_db, "IN MATE STAGE 공연 안내 - 11월 9일 8pm")
    assert conflict["price_krw"] is None and conflict["price_basis"] is None  # '무료' vs '30000원'
    assert conflict["venue_area"] == "sinchon"
    assert conflict["starts_at_utc"] == "2026-11-09T11:00:00Z"

    venues = {r["name"]: r for r in empty_db.execute("SELECT * FROM venues")}
    assert set(venues) == {"클럽에반스", "Club FF", "아지토 라이브홀"}
    assert venues["Club FF"]["source_url"] == "https://indistreet.com/venues/hongdaeff"  # 공연장 페이지만
    assert venues["클럽에반스"]["source_url"] is None
    # 데이터에 명시된 주소·층수만 저장, 없는 곳은 NULL (지어내지 않음)
    assert (venues["클럽에반스"]["address"], venues["클럽에반스"]["floor"]) == ("서울시 마포구 와우산로 63 2층", "2F")
    assert (venues["아지토 라이브홀"]["address"], venues["아지토 라이브홀"]["floor"]) ==         ("서울 서대문구 신촌역로 13 세오빌딩 지하", None)
    assert venues["Club FF"]["address"] is None and venues["Club FF"]["floor"] is None
    assert all(v["data_origin"] == "verified" for v in venues.values())


def test_import_is_idempotent_and_reset(empty_db, tiny_files):
    seed.import_dataset(empty_db, *tiny_files)
    again = seed.import_dataset(empty_db, *tiny_files)
    assert again.imported == 0 and again.already_present == 3
    assert empty_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3
    reset = seed.import_dataset(empty_db, *tiny_files, reset=True)
    assert reset.imported == 3 and empty_db.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 3


def test_import_without_extract_file(empty_db, tiny_files):
    report = seed.import_dataset(empty_db, tiny_files[0], None)
    assert report.price_conflicts == 0
    jazz = _event(empty_db, "재즈 나잇")
    assert jazz["doors_open_at_utc"] is None  # 보충 없음
    inmate = _event(empty_db, "IN MATE STAGE 공연 안내 - 11월 9일 8pm")
    assert inmate["price_krw"] == 0  # 데이터셋 값만 있으면 그대로


# ---------- 실제 엑셀 파일 연동 ----------
real_files = pytest.mark.skipif(
    not (seed.DATASET_PATH.exists() and seed.EXTRACT_PATH.exists()), reason="저장소 루트에 데이터 엑셀이 없음"
)


@pytest.fixture()
def real_client(empty_db):
    from main import create_app

    report = seed.import_dataset(empty_db)
    with TestClient(create_app(), client=("127.0.0.1", 50000)) as c:
        yield c, report, empty_db


@real_files
def test_real_dataset_import(real_client):
    _, report, conn = real_client
    assert report.rows == 426
    assert report.imported >= 300 and report.skipped.get("공연팀 모집·대관 글", 0) >= 70
    assert conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0] >= 20
    # 명세 최소치: 공연장 4곳·공연 20건 이상, 미래 공연 다수
    future = conn.execute("SELECT COUNT(*) FROM events WHERE starts_at_utc >= '2026-11-06T03:00:00Z'").fetchone()[0]
    assert future >= 100
    assert conn.execute("SELECT COUNT(*) FROM events WHERE poster_image_path IS NOT NULL "
                        "OR description_ko IS NOT NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM events WHERE data_origin <> 'verified'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM events WHERE title LIKE '%모집%'").fetchone()[0] == 0
    # 가격 규칙 위반 없음 (DB CHECK + 서버 산출)
    for r in conn.execute("SELECT price_krw, price_basis, advance_price_krw, door_price_krw FROM events"):
        assert seed.compute_price(None if (r[2] or r[3]) else r[0], r[2], r[3]) == (r[0], r[1])


@real_files
def test_real_dataset_through_api(real_client):
    client, _, _ = real_client
    events = client.get("/api/events", params={"date": "2026-11-07", "area": "hongdae", "limit": 50}).json()
    titles = {i["title"] for i in events["items"]}
    assert "ADYNE SOLO CONCERT ‘ANOTHER WAY’" in titles and events["total"] >= 10
    assert all(i["data_origin"] == "verified" for i in events["items"])

    adyne = next(i for i in events["items"] if i["title"].startswith("ADYNE"))
    assert (adyne["price_krw"], adyne["price_basis"], adyne["door_price_krw"]) == (40000, "advance", 45000)
    detail = client.get(f"/api/events/{adyne['id']}").json()
    assert detail["starts_at"] == "2026-11-07T11:00:00Z" and detail["lineup"] == ["에이다인"]
    assert detail["source_url"].startswith("https://") and detail["verified_at"] is None

    under_40k = client.get("/api/events", params={"max_price_krw": 40000, "limit": 50}).json()
    assert under_40k["items"] and all(0 <= i["price_krw"] <= 40000 for i in under_40k["items"])

    venues = client.get("/api/venues", params={"q": "클럽 에반스"}).json()
    assert [v["name"] for v in venues["items"]] == ["클럽에반스"]
    assert client.get("/api/venues", params={"area": "sinchon"}).json()["total"] >= 2

    rec = client.post("/api/recommend", json={"query": "", "filters": {"date": "2026-11-07", "area": "hongdae",
                                                                      "max_price_krw": 40000}}).json()
    assert 1 <= len(rec["items"]) <= 3 and rec["total_matches"] >= len(rec["items"])
    assert all(i["event"]["price_krw"] <= 40000 for i in rec["items"])
    assert all("홍대 공연이며" in i["reason"] for i in rec["items"])


@real_files
def test_real_venue_detail_through_api(real_client):
    client, _, conn = real_client
    evans = conn.execute("SELECT id FROM venues WHERE name = '클럽에반스'").fetchone()["id"]
    body = client.get(f"/api/venues/{evans}").json()
    assert body["address"] == "서울시 마포구 와우산로 63 2층" and body["floor"] == "2F"
    assert body["data_origin"] == "verified" and body["entrance_image_url"] is None
    unknown = conn.execute("SELECT id FROM venues WHERE name = '롤링홀'").fetchone()["id"]
    assert client.get(f"/api/venues/{unknown}").json()["address"] is None


@real_files
def test_real_venue_names_match_posters(real_client):
    from services.venue_matcher import match_venue

    _, _, conn = real_client
    assert match_venue(conn, "롤링홀")["status"] == "matched"
    assert match_venue(conn, "club ff")["status"] == "matched"  # 대소문자·공백 정규화
    assert match_venue(conn, "KT&G 상상마당 홍대 라이브홀")["status"] == "matched"
    assert match_venue(conn, "없는 클럽")["status"] == "not_found"
