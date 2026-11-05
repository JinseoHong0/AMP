# AMP v1.1 — 개발 명세 변경 내역

> 기준: 2026-11-05 개발 명세 v1.0 → 2026-11-06 수정안 v1.1. 아직 개발 착수 전이므로 **이 문서가 이전 코드를 마이그레이션하는 작업을 요구하는 것은 아니다.**

## 2026-11-06 등록 번역 개정

- 최종 원문으로 공연 등록 시 영문 제목·소개·입장 안내·드링크 안내를 자동 생성해 함께 저장. 영어 수동 입력/별도 검수는 필수 아님.
- `title_en`, `drink_policy_en`, `translation_status`, `translation_source_hash`, `translated_at_utc` 추가. 기존 설명/입장 영문 필드는 자동 생성값 저장에 재사용.
- 등록 API의 영문 입력 제거. 응답의 `translation` 상태와 자동 번역 표시·원문 보기 추가.
- 번역 실패 시 원문 공연은 201로 등록하고 관리자 번역 재시도 API 추가. DB 저장 실패는 별도 오류.
- 원문 지문·원자적 저장으로 이전 번역과 동시 요청 덮어쓰기 방지. 공유 공연장 정보는 기존 계약 유지.

## 2026-11-06 검색 설계 개정

- 고정 `SearchIntent`·문장별 판단표·Python 가중치 랭킹을 제거하고, AI가 검색 계획·DB 도구 호출·재조회·후보 비교·이유 작성을 수행하도록 변경.
- `search_events`/`get_event_details` 내부 읽기 전용 도구, 범용 `EventQuery` 조건식, 페이지 조회와 실행 한도 정의. DB 테이블과 공개 API 경로는 유지.
- 서버는 최초 필수 조건과 UI 필터 유지, 파라미터 바인딩, 실제 조회된 ID·최신 상태·근거 검증 담당.
- 추천 응답의 `score` 제거. `status`, `applied_conditions`, `preferences`, `search_limited`, `clarification` 추가. 조회 전 `total_matches=null` 허용.
- 확인 질문/실제 0건/탐색 미완료/AI 장애를 구분. 자연어 AI 실패 시 수동 필터 결과로 자동 대체하지 않음.
- 아래 내용은 최초 v1.1 변경 기록이며 검색 흐름의 현재 계약은 개정된 `AI.md`/`API.md`를 따른다.

## 변경 이유

인디스트릿은 이미 공연/공연장/아티스트 정보를 제공하며 **설명 텍스트 기반 공연 정보 자동 추출**도 지원한다. 기존 AMP의 '정보가 없다/등록 자동화 자체가 차별점'이라는 주장을 수정하고, **상황별 선택·방문 준비·포스터 이미지 등록**의 체감 경험을 중심으로 범위를 재정의했다. 기존 서비스의 자연어 추천/이미지 추출 존재 여부는 **미확인**이며 부재를 단정하지 않는다.

## 파일별 변경

| 파일 | 핵심 변경 |
|---|---|
| `PROJECT.md` | 문제 정의 수정, 방문 준비 카드, 필수/선호 좌석, 가격 종류, P0/P1 순서, 수용 기준 |
| `DATABASE.md` | `doors_open_at_utc`, 예매·현장가, `price_basis`, `booking_url`, `seat_assignment`, `admission_notes_ko/en` 추가; 대표 가격 산출·입장 정책 표시 규칙 |
| `API.md` | 기존 API 7개 유지, `GET /api/venues` 신규 1개, `venue_match` 결과, 등록 신규 필드, 좌석 요구/선호/가격 응답 일치 |
| `AI.md` | SearchIntent 필수·선호 좌석 분리, 서버 DB 매칭 정책, 포스터 가격 분해, 근거 없는 추정 금지 |
| `DEVELOPMENT.md` | P0 관객 → P1 공급자, FE/BE/AI 병렬 개발과 계약 테스트, 새 실패 케이스 |
| `README.md` | 이전 README v1.1의 데이터 이름 불일치를 API/DB 기준으로 보정 |

## 반드시 공유할 최종 결정 8가지

1. DB는 **`events` + `venues` 두 테이블** 유지. `venue_id`는 MVP 등록 필수.
2. 행사별 입장 시각은 **`doors_open_at_utc`**, 시작은 **`starts_at_utc`**.
3. 가격은 `price_krw` 대표 가격 및 `price_basis`; `advance_price_krw`, `door_price_krw`를 보관.
4. `0`원 무료와 `NULL` 미확인을 다르게 처리. 현재 구매 가능성은 보장하지 않음.
5. `seating_preference`는 AI 후보 비교에 사용하고, `seating_requirement`는 DB 조회와 최종 응답에서 필수 조건으로 검증.
6. `seat_assignment`는 지정석/비지정석 구분; ‘선착순’은 `admission_notes_*`로 설명.
7. Vision이 장소 ID를 만드는 게 아니라 서버가 **기존 장소명만 매칭**. `venue_match.status`와 `GET /api/venues` 사용.
8. 방문 원문은 등록자가 확인하며 공연 영문은 등록 시 자동 생성·표시. **긴 안내문 정책 추론·자동 요약은 MVP 제외**, 원문 번역은 포함.

## 개발 착수 전에 남은 결정

- AI 제공자와 모델/비용·호출량.
- 로컬 시연 여부와 행사 실제 개발 시간.
- 데이터·포스터 이미지의 사용 허가 및 시드 검수 담당자.
- 로컬 관리자 POST 접근 방식(공개 배포면 인증과 영구 스토리지 필요).

**명세 배포 순서:** root `README.md` + `docs/` 폴더를 팀 저장소에 배치 → 계약 합의 → 프런트 mock/백엔드 스키마 병렬 개발 시작.
