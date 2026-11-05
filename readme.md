# 🎸 AMP — 작은 무대의 울림을 세계로

> **Amplify Local Stages.**
>
> 작은 공연과 관객의 연결을 증폭하는 AI 기반 로컬 공연 큐레이터

**2026 명지대학교 해커톤 | AI × K-콘텐츠: Local to Global | 5조**

---

## 1. 프로젝트 소개 (Overview)

### 🎵 What is AMP?

**AMP**는 서울 신촌·홍대 지역의 인디 라이브 클럽과 소규모 공연을 쉽게 발견하고 방문할 수 있도록 돕는 AI 기반 공연 큐레이션 서비스입니다.

기타 앰프(Amplifier)가 작은 소리를 증폭해 더 많은 사람에게 전달하듯, AMP는 작은 공연장의 목소리를 더 크게 전달하고 밴드와 관객, 서울의 로컬 문화와 세계를 연결합니다.

**"소비자는 정보가 없어서 못 가고, 제공자는 알릴 길이 없어서 무너진다. 우리는 정보를 먼저 연결한다."**

### 🎯 문제 정의 (Problem)

**관객의 문제**
- 공연 정보가 인스타그램 등 여러 SNS에 분산되어 탐색하기 어려움
- 공연장 입구, 층수, 스탠딩 여부, 드링크 정책 등 현장 정보 부족
- 혼자 공연장을 방문하거나 처음 라이브 클럽을 이용하는 데 심리적 부담
- 외국인 관광객에게는 언어와 로컬 문화의 장벽까지 존재

**공연 제공자의 문제**
- 소규모 공연은 홍보 채널과 노출 기회가 제한적
- 공연 정보를 여러 플랫폼에 반복 등록하는 과정이 번거로움
- 잠재 관객에게 공연의 매력과 분위기를 전달하기 어려움

### 🌏 Local to Global

서울의 인디 공연 문화는 해외 여행객에게도 매력적인 로컬 K-콘텐츠입니다.

AMP는 파편화된 공연 정보를 AI로 구조화하고, 사용자 맞춤형 추천과 다국어 입장 가이드를 제공하여 서울의 작은 무대를 전 세계 관객과 연결하는 것을 목표로 합니다.

---

## 2. 핵심 기능 (Core Features)

### ① AI 상황 맞춤형 공연 추천

사용자가 자연어로 원하는 공연을 설명하면 AI가 의도를 분석하고, 실제 등록된 공연 DB를 바탕으로 적합한 공연을 추천합니다.

**검색 예시**

> "오늘 신촌에서 혼자 2만 원 이하로 볼 만한 잔잔한 공연 있어?"

**추천 프로세스**
1. 사용자 자연어 입력
2. LLM을 통한 검색 의도 및 조건 추출
3. 공연 DB에서 날짜·위치·가격 등 필수 조건 필터링
4. 분위기와 사용자 상황을 고려한 후보 점수 계산
5. 상위 공연 최대 3개와 AI 추천 이유 제공

**핵심 원칙**
- 실제 등록된 공연 데이터만 추천
- 확인되지 않은 공연 정보 생성 금지
- 추천 이유는 DB에 존재하는 사실을 기반으로 생성
- 조건에 일치하는 공연이 없으면 결과가 없음을 명확히 안내

### ② 공연장 입장 가이드 & Global Toggle

공연장에 처음 방문하는 사람과 외국인 여행객을 위한 실용적인 입장 가이드를 제공합니다.

**제공 정보**
- 공연장 위치 및 입구 사진
- 건물 층수 및 입장 방법
- 스탠딩 / 좌석 여부
- 드링크 정책
- 공연장 분위기 태그
- 동네 및 공연장 이야기
- 한국어 / 영어 안내 전환

공연별로 달라질 수 있는 정책은 별도로 관리하고, 확인되지 않은 정보는 임의로 생성하지 않습니다.

### ③ AI 포스터 자동 등록

공연 제공자가 포스터 이미지를 업로드하면 Vision AI가 주요 정보를 자동으로 추출합니다.

**추출 항목**
- 공연명
- 공연 날짜 및 시간
- 공연 장소
- 티켓 가격
- 출연진 / 라인업
- 장르 및 관련 정보

**등록 프로세스**
1. 공연 포스터 이미지 업로드
2. Vision LLM으로 이미지 분석
3. 구조화된 JSON 데이터 반환
4. 제공자가 추출 결과 확인 및 수정
5. 공연 DB에 저장
6. 등록된 공연을 추천 검색에 즉시 반영

AI 분석 결과는 반드시 검수한 후 등록합니다.

---

## 3. MVP 범위 (Scope)

### ✅ Must-Have
- 자연어 기반 AI 공연 추천
- 날짜·지역·가격 조건 필터링
- 공연 추천 카드 및 상세 정보
- 공연장 입장 가이드
- 한국어 / 영어 전환
- 공연 포스터 AI 정보 추출
- 검수 후 공연 등록
- 신규 등록 공연의 DB 검색 반영

### ❌ Out of Scope
- 세션 및 밴드 멤버 매칭
- 사용자 커뮤니티
- 북마크 및 개인 컬렉션
- 공연 예매 및 결제
- 주변 관광 코스 추천
- 실시간 SNS 자동 크롤링

제외된 기능은 향후 확장 계획으로 제시합니다.

---

## 4. 기술 스택 (Tech Stack)

| Category | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Styling | Tailwind CSS |
| Backend | Python, FastAPI |
| Data Validation | Pydantic |
| Database | SQLite |
| AI | Multimodal Vision LLM |
| AI Output | Structured JSON |
| Collaboration | Git, GitHub |
| Deployment | Vercel / Backend Hosting (TBD) |

### 기술 선택 이유

**React + TypeScript + Vite**
- 컴포넌트 단위 UI 개발 및 협업
- 빠른 개발 환경 구축
- 검색·상세·등록 화면 분리

**FastAPI**
- Python 기반 AI 모델 및 외부 LLM API 연동
- REST API 개발에 적합
- Pydantic을 통한 입력 데이터 검증
- 자동 API 문서 제공

**SQLite**
- 별도 DB 서버 구축 불필요
- 소규모 해커톤 데이터 관리에 적합
- 신규 공연 등록 및 검색 결과 반영 가능

---

## 5. 시스템 아키텍처 (Architecture)

```text
                ┌─────────────────────┐
                │       User          │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ React + TypeScript  │
                │      Frontend       │
                └──────────┬──────────┘
                           │ REST API
                           ▼
                ┌─────────────────────┐
                │  Python FastAPI     │
                │      Backend        │
                └──────────┬──────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
     AI Recommendation  Venue Guide   Poster Parser
            │              │              │
            ▼              │              ▼
      LLM + Filtering      │          Vision LLM
            │              │              │
            └──────────────┼──────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │   SQLite Database   │
                │   Events / Venues   │
                └─────────────────────┘
```

---

## 6. 데이터 구조 (Database)

### Events — 공연 정보

| Field | Description |
|---|---|
| id | 공연 고유 ID |
| venue_id | 공연장 ID |
| title | 공연명 |
| starts_at | 공연 시작 일시 |
| price | 티켓 가격 |
| genre | 음악 장르 |
| mood_tags | 분위기 태그 |
| lineup | 출연진 |
| seating_type | 관람 방식 |
| drink_policy | 해당 공연 드링크 정책 |
| poster_url | 포스터 이미지 |
| source_url | 공연 정보 출처 |

### Venues — 공연장 정보

| Field | Description |
|---|---|
| id | 공연장 고유 ID |
| name | 공연장명 |
| area | 지역 |
| address | 주소 |
| floor | 층수 |
| entrance_image | 입구 이미지 |
| default_guide | 기본 입장 안내 |
| source_url | 정보 출처 |
| verified_at | 정보 최종 확인 일시 |

공연과 공연장을 분리하여 하나의 공연장에 여러 공연을 등록할 수 있도록 설계합니다.

---

## 7. API 설계 (API Endpoints)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/recommend` | AI 맞춤형 공연 추천 |
| GET | `/api/events` | 공연 목록 조회 |
| GET | `/api/events/{id}` | 공연 상세 조회 |
| GET | `/api/venues/{id}` | 공연장 가이드 조회 |
| POST | `/api/posters/parse` | 포스터 AI 정보 추출 |
| POST | `/api/events` | 공연 등록 |
| GET | `/api/health` | 서버 상태 확인 |

---

## 8. 프로젝트 구조 (Directory Structure)

```text
amp-seoul/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   └── types/
│   └── package.json
│
├── backend/
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── database.py
│   ├── services/
│   │   ├── recommender.py
│   │   ├── poster_parser.py
│   │   └── llm.py
│   └── seed.py
│
├── assets/
│   ├── posters/
│   └── entrances/
│
├── docs/
│   ├── PROJECT.md
│   ├── API.md
│   └── DATABASE.md
│
├── .gitignore
├── .env.example
└── README.md
```

---

## 9. 개발 로드맵 (Roadmap)

### Phase 1 — 프로젝트 초기화
- [ ] GitHub Repository 생성
- [ ] 프런트엔드 및 백엔드 초기 환경 구성
- [ ] 협업 규칙 및 API 명세 확정
- [ ] 데이터 구조 설계

### Phase 2 — 핵심 서비스
- [ ] 공연 및 공연장 시드 데이터 구축
- [ ] 공연 조회 API 구현
- [ ] 메인 검색 화면 개발
- [ ] AI 검색 조건 추출 및 추천 구현
- [ ] 추천 카드 및 상세 화면 연결

### Phase 3 — 글로벌 & 제공자 기능
- [ ] 입장 가이드 카드 구현
- [ ] 한국어 / 영어 전환
- [ ] 포스터 업로드 및 Vision AI 연결
- [ ] 추출 데이터 검수 및 등록
- [ ] 신규 공연 검색 반영 검증

### Phase 4 — 통합 및 발표
- [ ] 프런트엔드 / 백엔드 통합 테스트
- [ ] API 오류 및 예외 상황 처리
- [ ] 90초 시연 시나리오 완성
- [ ] 발표 자료 제작
- [ ] 백업 데모 준비

---

## 10. 90초 데모 시나리오

| Time | Demo |
|---|---|
| 0~10초 | 문제 정의 및 AMP 소개 |
| 10~30초 | 자연어 기반 AI 공연 추천 |
| 30~45초 | 공연장 입장 가이드 및 영어 전환 |
| 45~65초 | 포스터 업로드 및 AI 정보 추출 |
| 65~80초 | 등록 공연의 검색 반영 확인 |
| 80~90초 | 서비스 가치 및 비전 전달 |

---

## 11. 향후 확장 계획 (Future Work)

- 공연장 및 공연 데이터 지역 확대
- 실제 공연 제공자와의 정보 연동
- 사용자 취향 기반 개인화 추천
- 다국어 지원 확대
- 공연 예매 플랫폼 연계
- 밴드 및 세션 매칭
- 지역 관광·문화 콘텐츠 연계

---

## 12. 팀 소개 (Team)

**2026 명지대학교 AI × K-콘텐츠 해커톤 — 5조**

팀원 및 세부 담당 역할은 추후 업데이트 예정입니다.

---

## 🌏 Our Vision

### Amplify Local Stages.

기타 앰프가 작은 신호를 증폭해 더 많은 사람에게 음악을 전달하듯, AMP는 작은 공연의 가능성을 증폭합니다.

밴드에게는 더 많은 관객을, 관객에게는 새로운 음악적 경험을, 해외 여행객에게는 서울의 진짜 로컬 문화를 만날 기회를 제공합니다.

**작은 무대의 울림을 세계로. AMP.**