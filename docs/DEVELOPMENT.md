# AMP — 구현·협업·테스트 계획 (DEVELOPMENT.md)

> 버전 **v1.1** · 2026-11-06 · 5인 팀 / 집중 개발 12시간 **가정**. 실제 행사 일정에 맞춰 조정.  
> 이 문서는 작업 순서·담당·통합 기준을 정의한다. **API·DB 필드의 원본 계약은 [API.md](./API.md)와 [DATABASE.md](./DATABASE.md)** 이다.

## 1. 개발 우선순위

### P0 — 관객 핵심 흐름(우선 안정화)

- `venues` 최소 4건, `events` 최소 20건 시드 데이터(출처/`DEMO` 구분).
- 공연 목록/상세/공연장 조회 API.
- 자연어 검색 의도 추출·하드 필터(날짜·지역·대표 가격·필수 좌석 조건)·소프트 랭킹.
- 추천 최대 3개와 사실 기반 이유, 예매/현장/일반 가격 구분.
- 공연별 방문 준비 카드: 입장/시작 시각 구분, 관람 방식·비지정석, 가격, 공연별 안내.
- 검수된 한국어/영어 가이드와 미확인 표시, 기본 오류·0건 처리.

### P1 — 공연 제공자 등록(최종 데모 포함 목표)

- 포스터 이미지 업로드 → Vision 추출 → 기존 공연장 DB 유일 이름 매칭.
- 매칭 실패/모호함 시 `GET /api/venues`에서 기존 장소 수동 선택.
- 필드 수정·검수 → `POST /api/events` → 목록 및 조건부 추천 반영.
- 등록 도중 중복 클릭, 이미지 오류, AI 실패 시 수동 등록 대체 경로.

### P2 — 이번 MVP에서 제외

완제품 인증/공개 관리자 기능, 신규 공연장·아티스트 CRUD, 실시간 크롤링, 예매/결제, 커뮤니티, 북마크, 지도, 장문의 공연 공지 AI 자동 해석, 벡터 DB/RAG.

> **P1은 최종 데모 범위이지만 구현 순서가 P0 이후**라는 의미다. P1이 실패해도 검색→추천→방문 준비의 P0 데모는 작동해야 한다.

## 2. 팀별 담당 및 산출물

| 역할 | 작업 파일/영역 | P0/P1 체크포인트 |
|---|---|---|
| PM/통합 | `docs/`, 시드 데이터 검수, QA, 발표 | API 계약·데모 픽스처 고정, 통합 검수 |
| FE 검색 | `Home`, `SearchBar`, `FilterChips`, `EventCard` | 추천/0건/미확인/가격 종류 표시 |
| FE 상세/등록 | `EventDetail`, `VisitReadyCard`, `VenueGuide`, `PosterUpload`, `ReviewForm` | P0 방문 카드·KO/EN, P1 검수/장소 선택 |
| BE | DB, Pydantic, `routers/events.py`, `routers/venues.py` | 목록/상세/기존 venue 목록/등록·검증 |
| AI | `intent.py`, `ranker.py`, `reason.py`, `poster_parser.py`, `venue_matcher.py` | 조건 파싱, 규칙 랭킹, 포스터 추출, 장소 매칭 |

**핵심 연결점:** `backend/models.py`·`schemas.py`의 모델 필드, `frontend/src/types/`의 TS 타입, `docs/API.md` JSON이 반드시 같아야 한다. AI 담당은 DB를 직접 쓰지 않고, 검수·저장은 BE가 책임진다.

## 3. 프로젝트 폴더 구조(제안)

```text
amp-seoul/
├── README.md
├── .gitignore
├── .env.example
├── docs/
│   ├── README.md
│   ├── PROJECT.md
│   ├── API.md
│   ├── DATABASE.md
│   ├── AI.md
│   └── DEVELOPMENT.md
├── frontend/
│   ├── src/
│   │   ├── pages/              # Home, EventDetail, AdminRegister
│   │   ├── components/         # EventCard, VisitReadyCard, ReviewForm
│   │   ├── api/                # API client, mockData
│   │   ├── types/              # TypeScript API contracts
│   │   └── styles/
│   ├── package.json
│   └── .env.example
├── backend/
│   ├── main.py
│   ├── routers/
│   │   ├── events.py
│   │   ├── venues.py
│   │   ├── recommend.py
│   │   └── posters.py
│   ├── services/
│   │   ├── intent.py
│   │   ├── ranker.py
│   │   ├── reason.py
│   │   ├── poster_parser.py
│   │   └── venue_matcher.py
│   ├── models.py
│   ├── schemas.py
│   ├── database.py
│   ├── seed.py
│   ├── requirements.txt
│   └── data/               # 런타임 DB: Git 제외
└── assets/
    ├── posters/            # 사용 권리 확인된 샘플만
    └── entrances/
```

## 4. 구현 전 공통 계약 확정 (중요)

**개발 첫 PR 전 아래를 확인하고 `docs/API.md` + `docs/DATABASE.md`를 기준 문서로 고정한다.**

1. 가격 계약: `price_krw`는 대표 검색 가격. 예매/현장 값이 있으면 서버 산출하고 `price_basis=advance|door`; 단일 가격이면 `general`, 모르면 null.
2. 입장 시각: `doors_open_at_utc`는 `starts_at_utc`와 별도. 모르면 null.
3. 좌석: `seating_type`(standing/seated/mixed), `seat_assignment`(assigned/unassigned), `seating_preference`(소프트), `seating_requirement`(하드).
4. 장소: `venue_id`는 신규 등록 시 기존 DB에 있어야 하며 `venue_match.status`와 `GET /api/venues`가 수동 선택에 사용된다.
5. KO/EN 안내: `admission_notes_ko/en`(공연별), `entrance_hint_ko/en`(공연장 동선); 실시간 자동 번역은 없음.
6. 발표 예시는 `DEMO`이며 실제 공연으로 오해되지 않게 표시한다.

**문서 변경 절차:** 명세 변경 제안 → `DATABASE.md`/`API.md` 수정 → 관련 `AI.md`/`PROJECT.md`/타입 수정 → PR 리뷰 → merge. 문서와 실제 JSON이 다른 상태로 통합하지 않는다.

## 5. 집중 개발 12시간 가정 일정

| 시간 | 작업 | 통합 체크포인트 |
|---|---|---|
| 0~1h | 실행 환경, 레포, API/DB 필드 동결, mock 제공 | FE→BE `/api/health` 성공 |
| 1~3h | DB/seed, GET 목록·상세·venue 조회; 검색 UI mock | `GET /api/events`, `/api/venues` 응답 일치 |
| 3~5h | 자연어 → 조건 → 하드 필터 → 랭킹; 검색 카드 | 예산/좌석 필수·선호 규칙 테스트 |
| 5~7h | 방문 준비 카드·가격 종류·KO/EN 통합 | 추천→상세→방문 정보 P0 완주 |
| 7~9h | 포스터 파서·장소 매칭·검수·등록 | 업로드→등록→목록 반영 |
| 9~10.5h | 통합 오류·미확인·반응형·관리자 보호 확인 | 핵심 정상/오류 체크리스트 통과 |
| 10.5~12h | 90초 데모, 백업 영상, 발표/비교 실험 결과 | 2회 연속 시연 성공 |

실제 시간이 짧으면 **P0가 완성된 상태로 P1 데모 범위를 축소**하고, 비핵심 UI 장식·애니메이션을 먼저 제외한다. P1을 구현했다는 거짓 발표는 하지 않는다.

## 6. 병렬 작업 규칙

1. PM+FE+BE+AI가 JSON 예시와 enums를 함께 확인. `docs/API.md`를 변경 계약의 단일 출처로 사용한다.
2. FE는 `frontend/src/api/mockData.ts`에 **계약과 같은** 응답 fixture를 만들고 mock→실 API 교체 가능하게 구현.
3. BE는 Pydantic 응답 스키마와 실제 SQLite 레코드를 계약에 맞게 구성. 로컬 `/docs`에서 예제 검증.
4. AI 담당은 `SearchIntent`, `PosterExtraction` 스키마를 반환하고, Pydantic 검증/서버 기반 필터/venue 매칭을 통과시키도록 테스트.
5. 공통 API 필드 변경은 합의 없이 개별 코드에서 재명명하지 않는다. 예: `venue_name_detected` 금지, `extracted.venue_name` 사용.
6. `main`은 작동하는 버전, 기능 브랜치·작은 PR·서로 다른 담당 파일 권장.

## 7. 정상 흐름 테스트

### P0
- [ ] `/api/health` 200, `GET /api/events`/`{id}`/`venues/{id}` JSON이 문서와 일치.
- [ ] 샘플 공연 20개 이상, 공연장 4곳 이상. `DEMO` 데이터는 뱃지 표시.
- [ ] 날짜는 KST로 처리. 지난 공연·취소/초안 공연을 공개 추천하지 않음.
- [ ] 대표 가격 20,000원/예매 가격 20,000원·현장 25,000원이 정확히 구분됨.
- [ ] `'좌석 공연만'`은 `seating_requirement=seated`; `mixed|null`은 제외.
- [ ] `'좌석이면 좋겠어'`는 `seating_preference=seated`로 점수 가중치만 적용.
- [ ] 분위기/혼자 선호를 근거 있는 속성으로만 정렬, 추천 최대 3개.
- [ ] `doors_open_at`과 `starts_at`을 별도 라벨·시간으로 표시.
- [ ] 장소 기본 정책과 공연별 정책/규칙을 구분하여 표시.
- [ ] EN 토글에서 검수된 영문 안내 출력, 없으면 원문 + 미확인 표시.

### P1
- [ ] 포스터 추출이 `extracted` JSON 스키마를 준수.
- [ ] DB에 장소명이 하나 일치하면 `matched`/ID, 모호하면 `ambiguous`/null, 없으면 `not_found`/null.
- [ ] `GET /api/venues`로 기존 공연장을 수동 선택할 수 있음.
- [ ] 검수 체크/유효한 `venue_id` 없이 저장할 수 없음.
- [ ] 성공 등록 201, `GET /api/events`에서 새 공연 확인, 추천 조건에 맞을 때만 추천.

## 8. 필수 예외 테스트

- [ ] 0건 추천 → 200 + 빈 목록; 다른 공연을 조작해 보여주지 않음.
- [ ] 가격 미확인(`null`)은 예산 조건 제외, 무료(`0`)는 확인된 경우만 포함.
- [ ] 예매가·현장가 중 하나만 존재, 두 가격 동가, 대표 가격 불일치(422) 처리.
- [ ] 공연별 좌석 미확인은 좌석 필수 조건에 일치시키지 않음.
- [ ] 공연 시작 시각만 있을 때 입장 시각을 추정하지 않음.
- [ ] 입구 사진·영문 정책·상세 안내 미확인은 placeholder/명확한 라벨.
- [ ] Vision 장애 → 사용자 수동 입력; AI 추천 장애 → 수동 칩 검색 또는 오류.
- [ ] 이미지 5MB 초과·PDF·손상·비이미지 업로드는 각각 오류.
- [ ] 장소 미매칭·잘못된 `venue_id`·중복 `upload_id`는 등록 거절/수정 동선.
- [ ] 등록 중 버튼 중복 클릭 방지, 실패 시 이미 입력한 필드 유지.
- [ ] 관리자 POST는 외부 공개에서 인증 없이 접근할 수 없음.
- [ ] 모바일 화면에서 방문 정보, 영문 문장, 가격 라벨이 잘리지 않음.

## 9. 90초 시연·비교 실험

- [ ] 시연 당일 KST 기준으로 미래인 데모 데이터 준비(혹은 테스트 시계 고정).
- [ ] 추천할 공연과 신규 등록할 공연을 구분하며 동일 조건 일치 검증.
- [ ] 포스터 이미지 사용 허가/직접 제작 여부 점검.
- [ ] AI API 활성화·예산/용량/속도 점검, 대체 녹화 영상 확보.
- [ ] 비교 실험: 동일한 공연/요건으로 탐색·입장 정보 확인의 조작 횟수와 수동 입력 필드 개수 기록.
- [ ] 실제로 비교하지 않은 우월성·타사 부재 주장은 발표 자료에서 제외.
- [ ] P0 90초 흐름 단독, P0+P1 전체 흐름 각각 최소 2회 리허설.

## 10. GitHub 협업 규칙

**브랜치 예시:** `main`, `feat/fe-search`, `feat/fe-visit-card`, `feat/be-events`, `feat/ai-parser`, `fix/venue-match`, `docs/api-contract`.

**PR 최소 요건**
- 변경 범위와 담당 기능 설명, 프런트 수정 시 스크린샷 또는 응답 JSON.
- 어떤 테스트를 통과했는지 간단히 명시.
- API/DB 계약 변경 여부 체크.
- API 키·`.env`·`*.db`·업로드 임시 파일 미포함 확인.

초보자 팀원도 `main` 직접 수정 대신 작은 기능 브랜치에서 작업하고 리뷰 후 머지한다.

## 11. 환경변수와 배포

```dotenv
# Backend only; commit하지 않는 .env에 실제 키 보관
LLM_PROVIDER=your_provider
LLM_MODEL=your_supported_model
LLM_API_KEY=
DATABASE_URL=sqlite:///./data/amp.db
APP_TIMEZONE=Asia/Seoul
CORS_ORIGINS=http://localhost:5173
DEMO_MODE=true
MAX_POSTER_MB=5

# Frontend: 공개되어도 안전한 값만
VITE_API_BASE_URL=http://localhost:8000
```

**권장 로컬 데모:** FE Vite `http://localhost:5173`, BE Uvicorn `http://127.0.0.1:8000`, SQLite `backend/data/amp.db`; 실제 실행 명령은 구현 후 README에 반영. `DEMO_MODE=true`는 보안 인증을 대체하지 않으므로 공개 서버에 등록 API를 열지 않는다.

**공개 배포 선택 시:** FE 정적 호스팅, BE 영구 디스크/관리형 DB, 이미지 영구 스토리지, 관리자 인증/인가, AI 비용 제한 및 운영 정책 필요. 영구성이 필요한 DB를 서버리스 로컬 SQLite만으로 운영하지 않는다.

## 12. Definition of Done

**P0 완료:** 관객 정상 흐름 테스트, 좌석/가격/시간/미확인 예외 테스트, KO/EN 카드, 0건/오류 처리까지 검증.

**P1 완료:** 이미지 추출과 장소 유일 매칭/수동 선택, 검수·등록, 목록·조건부 추천 반영과 실패 복구 검증.

**MVP 시연 완료:** 실제 구현 상태가 문서에 맞고 `README.md`에 재현 가능한 실행법·미구현 사항이 표시되며, 90초 흐름을 연속 두 차례 수행하고 백업 데모를 확보.

## 13. v1.1 변경 이력

- 우선순위 P0 관객 핵심 경험 vs P1 등록 기능으로 분리.
- `GET /api/venues`, `venue_matcher.py`, 추천 좌석 선호/필수·가격 종류 반영.
- 방문 준비 카드, 검증된 영어 안내, 포스터 DB 매칭 등 새로운 정상/실패 테스트 추가.
- 초보 팀의 안정적인 병렬 개발을 위해 계약 동결→mock→통합 절차 구체화.

**관련:** [PROJECT.md](./PROJECT.md) · [API.md](./API.md) · [DATABASE.md](./DATABASE.md) · [AI.md](./AI.md)
