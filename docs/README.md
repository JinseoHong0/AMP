# AMP — 개발 상세 명세서 v1.1

**Amplify Local Stages. 작은 무대의 울림을 세계로.**  
2026 명지대학교 해커톤 · AI × K-콘텐츠: Local to Global · 5조  
버전 **v1.1 (2026-11-06)** · 상태 **개발 전 구현 계약**

이 폴더의 문서는 새로 코드를 개발할 팀을 위한 **공통 명세**다. 실제 구현된 코드는 포함하지 않는다. 각 명세의 필드명, API 요청·응답, 가격 산출 규칙과 완료 기준은 v1.1로 정합성을 맞췄다.

## 읽는 순서

1. [PROJECT.md](./PROJECT.md) — 목표 사용자, 새 문제 정의, 화면별 요구사항, P0/P1, 수용 기준
2. [DATABASE.md](./DATABASE.md) — 2테이블 ERD, 실행 가능한 SQLite DDL, 가격·좌석·시간 정책
3. [API.md](./API.md) — 엔드포인트 8개, JSON 요청·응답, 에러, 공연장 검색·자동 매칭
4. [AI.md](./AI.md) — 자연어 의도 추출, 엄격한 DB 필터, 소프트 점수, 포스터 AI, 장소 매칭 책임
5. [DEVELOPMENT.md](./DEVELOPMENT.md) — 5인 역할, 12시간 가정 일정, mock 병렬 개발, 테스트/PR
6. [CHANGELOG_v1.1.md](./CHANGELOG_v1.1.md) — v1.0에서 수정한 부분과 **팀 공통 결정사항**

## 빠른 개발 계약

- 스택: React + TypeScript + Vite / Python FastAPI + Pydantic / SQLite.
- P0: 공연 검색·추천·방문 준비 카드·확인된 KO/EN 가이드. **먼저 완성**.
- P1: 이미지 추출·기존 공연장 DB 매칭·검수·등록. **최종 시연 목표**.
- 신규 등록 `venue_id`는 필수. 새로운 공연장 생성은 MVP 제외.
- 날짜 KST 기준, DB/시각 API는 UTC Z. `doors_open_at`은 `starts_at`과 별도.
- `price_krw`는 확인된 최저 유효 가격이며 `price_basis`로 예매/현장/일반 구분. `NULL`은 미확인, `0`은 확인된 무료.
- 추천: 날짜/지역/가격/좌석 필수 하드 필터 → 분위기/혼자/좌석 선호 소프트 점수 → 최대 3개.
- 매칭: 이미지에서 `extracted.venue_name` 추출 → FastAPI가 기존 `venues` 검색 → `venue_match` 반환.
- 데모: 최소 공연 20건/공연장 4곳. 허가 없는 타사 이미지·텍스트 복제 금지, 합성 정보 `DEMO` 표시.
- 공개 운영을 목표로 한다면 별도 인증, 영구 스토리지, 호출량/비용 제한 필요.

## 우선순위 / 충돌 해결 기준

**코드 작성 전** `DATABASE.md`의 저장 필드와 `API.md`의 요청·응답을 먼저 고정한다. 추천 알고리즘은 `AI.md`의 의미와 `DATABASE.md` 필터 계약을 따른다. README는 소개문이고, API/DB는 구현의 원본 계약이다.

> 이전 버전의 `venue_name_detected`/`default_guide_en` 제안은 사용하지 않는다. **기존** `extracted.venue_name`/`entrance_hint_en`을 사용한다. 프런트 타입·백엔드 모델·API 예시는 같은 이름이어야 한다.
