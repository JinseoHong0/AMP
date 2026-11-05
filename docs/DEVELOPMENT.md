# AMP — 구현·협업·테스트 계획 (DEVELOPMENT.md)

> 버전 1.0 · 팀 5인/집중 개발 12시간 **가정**. 실제 행사 일정과 팀원 수에 맞춰 조정.

## 1. 우선순위

- **P0(필수):** 시드 20건, 추천 검색, 입장 가이드, 영어 전환, 포스터 추출/수정/등록, 전체 연결, 데모.
- **P1(가능하면):** 모바일 반응형 다듬기, 로딩 UX, 검색 입력 예시, 이미지 플레이스홀더.
- **P2(제외):** 인증 완제품, 지도/예매/결제/북마크/커뮤니티/크롤링/RAG/벡터 DB.

## 2. 팀원별 일감과 소유 파일

| 역할 | 우선 담당 파일/기능 | 완료 산출물 |
|---|---|---|
| PM/통합 | docs, seed 검증, QA, 발표, 공통 계약 | 시드 데이터 검수, 시연 완료 |
| FE 검색 | `frontend/src/pages/Home`, `components/SearchBar`, `EventCard` | 자연어 검색/칩/추천 결과 |
| FE 상세/등록 | `EventDetail`, `VenueGuide`, `PosterUpload`, `ReviewForm` | 가이드/영어/등록 UI |
| BE | `backend/main.py`, `database.py`, `models.py`, API routers | DB+CRUD+목록/상세 API |
| AI | `backend/services/intent.py`, `poster_parser.py`, `reason.py` | 3개 AI 경로+폴백 |

**협업 규칙:** 같은 파일 동시 수정 최소화, API 계약 먼저 머지, PR은 기능 단위로 작게, `main` 직접 푸시보다 PR 권장.

## 3. 폴더 구조

```text
amp-seoul/
├── README.md
├── .gitignore
├── .env.example
├── docs/
│   ├── PROJECT.md
│   ├── API.md
│   ├── DATABASE.md
│   ├── AI.md
│   └── DEVELOPMENT.md
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── api/
│   │   ├── types/
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
│   │   └── poster_parser.py
│   ├── models.py
│   ├── schemas.py
│   ├── database.py
│   ├── seed.py
│   ├── requirements.txt
│   └── data/                  # 런타임 DB, Git 제외
└── assets/
    ├── posters/              # 사용 권한이 확인된 샘플만 커밋
    └── entrances/
```

## 4. 집중 개발 12시간 가정 타임라인

| 시간 | 작업 | 통합 체크포인트 |
|---|---|---|
| 0~1h | 레포, 기초 실행, API 타입·DB 스키마 합의 | 프런트→백엔드 `/api/health` 성공 |
| 1~3h | DB/seed, 목록 API, 카드 UI 목업 | `GET /api/events` 카드 출력 |
| 3~5h | 자연어 파서, DB 필터, 랭킹, 추천 카드 | 조건 일치 3개 결과 확인 |
| 5~7h | 공연 상세·공연장 가이드·영어 전환 | 검색→가이드 완료 |
| 7~9h | 포스터 파서, 검수 폼, 이벤트 등록 | 업로드→저장→목록 반영 |
| 9~10.5h | 통합 오류 수정, 엣지케이스, 반응형 | P0 테스트 통과 |
| 10.5~12h | 시연 리허설, 백업 영상, 발표 준비 | 90초 풀 시연 2회 연속 성공 |

**일정이 부족하면** P1과 UI 장식을 빼고 P0 기능 연결에 집중한다. 실제 시간은 행사 공지 기준으로 조정.

## 5. 병렬 작업을 위한 API 계약 순서

1. BE+AI+FE가 [API.md](./API.md) 요청/응답 JSON을 30분 내 고정.
2. 프런트는 계약 JSON을 `src/api/mockData.ts` 등으로 사용하여 백엔드와 독립 개발.
3. BE는 Pydantic 응답 스키마로 정확히 같은 필드를 제공.
4. 프런트가 API URL만 목업→실제 주소로 바꿔 통합.
5. 필드 변경 시 먼저 API.md 수정 → FE/BE 동시 반영.

## 6. 통합 테스트 체크리스트

### 정상 흐름
- [ ] `/api/health`가 200을 반환한다.
- [ ] DB에서 행사 20건과 공연장 4곳을 읽는다.
- [ ] 필터 칩 + 자연어 검색 결과가 서버 필터와 일치한다.
- [ ] 추천된 카드 상세에서 입장 가이드를 볼 수 있다.
- [ ] EN 토글에서 검수된 영어 안내를 보여준다.
- [ ] 포스터 분석이 실제 JSON 스키마를 준수한다.
- [ ] 사람이 내용을 검수/수정한 뒤 등록한다.
- [ ] 신규 이벤트가 목록에 반영되고, 조건에 맞으면 추천에 나타난다.

### 예외 흐름
- [ ] 추천 0건에서 임의 공연을 표시하지 않는다.
- [ ] 가격 미확인 공연은 가격 상한 검색에서 제외한다.
- [ ] 지난 공연·취소 공연은 추천에서 제외한다.
- [ ] 이미지 5MB 초과/잘못된 확장자/손상 파일을 거절한다.
- [ ] AI 실패 시 추천은 칩 기반 검색으로, 등록은 수동 입력으로 복구한다.
- [ ] 장소 미매칭 시 기존 venue 선택을 요구한다.
- [ ] 관리자 API를 외부에 인증 없이 노출하지 않는다.
- [ ] 등록 중복 클릭 방지 및 성공 시 버튼 비활성화가 동작한다.
- [ ] 모바일 폭에서도 카드와 버튼이 겹치지 않는다.

### 시연 리허설
- [ ] 추천 데모 픽스처의 날짜가 **시연 당일 기준** 유효하다.
- [ ] 업로드용 포스터 내용이 실제 앱 DB와 충돌하지 않는다.
- [ ] AI API 계정 잔액·속도·허용량을 점검했다.
- [ ] 기본 시나리오를 90초에 진행한다(요청 속도 변동 고려).
- [ ] 네트워크 불능 시 사용할 녹화 영상이 있다.

## 7. GitHub 협업

### 브랜치 예시
- `main`: 안정적으로 실행되는 버전
- `feat/fe-search`, `feat/fe-guide`, `feat/be-events`, `feat/ai-parser`
- `fix/recommend-filter`, `docs/api-contract`

### PR 최소 요건
1. 변경 범위 및 스크린샷/샘플 응답.
2. 확인한 테스트 1개 이상.
3. 계약 변경 여부(`docs/API.md`, `docs/DATABASE.md`).
4. 비밀키·DB 파일·대용량 업로드 파일 미포함 확인.

### 커밋 예시
- `feat: add venue guide API`
- `feat: implement poster review form`
- `fix: exclude unknown prices from budget filter`

## 8. 환경변수 예시

```dotenv
# Backend (server-only; 실제 키 값은 .env에만 보관)
LLM_PROVIDER=your_provider
LLM_MODEL=your_supported_model
LLM_API_KEY=
DATABASE_URL=sqlite:///./data/amp.db
APP_TIMEZONE=Asia/Seoul
CORS_ORIGINS=http://localhost:5173
DEMO_MODE=true
MAX_POSTER_MB=5

# Frontend (Vite; 비밀키 입력 절대 금지)
VITE_API_BASE_URL=http://localhost:8000
```

`LLM_API_KEY` 값이 비어 있으면 AI 연결은 사용할 수 없으므로 수동 입력·모의 테스트만 가능. 프런트엔드에 `VITE_LLM_API_KEY`를 만들지 않는다.

## 9. 배포 전략

**기본: 로컬 데모**
- FE Vite: `http://localhost:5173`
- BE Uvicorn: `http://localhost:8000`
- SQLite: `backend/data/amp.db`
- 별도의 영구 서버 운영 없이 현장 시연, 리허설 녹화 백업.

**선택: 공개 웹 배포**
- FE Vercel 등 정적 호스팅.
- BE 영구 디스크 또는 관리형 DB와 연결 가능한 환경.
- 이미지도 영구 스토리지 사용.
- 등록 엔드포인트는 인증·인가 도입 전에는 막는다.
- Vercel Functions 로컬 SQLite는 영구 데이터 저장 설계로 사용하지 않는다.

## 10. 완료 판정(Definition of Done)

**MVP 완료 =**
- 정상 흐름 테스트 8개 모두 통과.
- 필수 예외 흐름(0건, 미확인 가격, 지난/취소 공연, 실패 처리) 검증.
- 90초 데모 2회 이상 연속 성공.
- README에 실제 실행 방법, 현재 구현 여부, 데모 데이터 표시.
- 문서의 API 계약과 실제 반환값이 일치.

**참고:** [프로젝트](./PROJECT.md) · [API](./API.md) · [DB](./DATABASE.md) · [AI](./AI.md)
