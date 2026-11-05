# AMP 포스터 추출 API

이번 구현은 **포스터 업로드 → Gemini 이미지 추출 → 기존 공연장 이름 매칭 → 프런트 원문 확인**까지입니다. 공연/공연장 생성, 추천, 영문 번역, 공연 등록은 이 단계에서 수행하지 않습니다. 기준은 루트 README와 `docs/API.md` §7, `docs/AI.md` §6–7입니다.

## 실행

Python 3.11 이상. 아래 명령은 저장소 루트에서 실행합니다.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
```

`backend/.env`에 `GEMINI_API_KEY`, `GEMINI_MODEL`을 입력합니다. 모델은 Google AI Studio 프로젝트에서 이미지 입력·JSON 구조화 출력과 무료 할당량을 사용할 수 있는 모델을 선택합니다. 모델명을 코드에서 고정하거나 유료 모델로 자동 전환하지 않습니다. 키가 없거나 모델 호출/할당량 제한/응답 검증에 실패하면 `503 AI_UNAVAILABLE`입니다. 실제 키는 Git이나 `frontend/.env`에 넣지 않습니다.

`DATABASE_URL`은 **DB 담당자가 만든 기존 SQLite DB**를 가리켜야 합니다. 기본 상대 경로 `sqlite:///./data/amp.db`는 실행 위치에 상관없이 `backend/data/amp.db`입니다. `venues`의 `id`, `name`, `area` 컬럼을 읽으며, 파일/테이블이 없으면 `503 VENUE_DB_UNAVAILABLE`입니다. DB 실패를 장소 미매칭으로 숨기거나 새 DB·시드 데이터를 자동 생성하지 않습니다.

```sh
backend/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

`LOCAL_DEMO=true`일 때 loopback 클라이언트/호스트에서만 포스터 POST를 허용합니다. Origin도 허용 목록과 대조합니다. 외부 공개용 인증은 이번 범위가 아니며, 프록시를 통해 우회 공개하지 않습니다. DB 담당자가 별도 앱을 만든 경우 `main.py`의 설정·에러 처리·업로드 제한과 `posters.router`를 함께 통합합니다.

프런트 `ampApi.parsePoster()`는 이미 실제 `FormData` 요청으로 연결됐습니다. `frontend/.env`의 `VITE_API_BASE_URL`은 기본 `http://localhost:8000`이며, 키는 전달하지 않습니다. 다른 API 어댑터는 기존 `BACKEND_TODO`를 유지합니다.

```sh
curl -F 'file=@/absolute/path/poster.png' http://127.0.0.1:8000/api/posters/parse
```

`http://127.0.0.1:8000/docs`에서 요청/응답 스키마를 확인할 수 있습니다. `/api/health` 성공은 Gemini/DB 준비 완료를 뜻하지 않습니다.

## 구현 동작

- `POST /api/posters/parse`: `file` 하나, JPEG/PNG/WebP, 최대 5MiB(프런트와 동일한 5MB 기준). multipart 전체도 파일 크기 + 64KiB로 제한해 파싱 전에 과도한 업로드를 거절합니다.
- MIME/실제 포맷 일치, 실제 디코딩, 손상/빈 파일 검사. 자원 보호를 위해 정지 이미지·2,500만 화소 이하만 받습니다.
- 실제 이미지 bytes를 Gemini에 전달하고 Pydantic JSON 계약으로 결과를 검증합니다. 업로드 파일명, 사용자 지정 경로, DB ID는 모델에 주지 않습니다. 모델은 도구를 호출하거나 DB에 쓰지 않습니다.
- 명시된 제목·시각·장소명·가격·출연진·장르만 추출합니다. 연도 누락/여러 일정은 날짜를 비우고 검수를 요구합니다. 입장 시간·좌석·분위기 등을 추측하지 않습니다.
- 잘못 읽힌 날짜/금액은 경고에 원래 값을 남기고 해당 폼 필드를 검수 대상으로 표시합니다. 음수는 비우며 무료 0원과 미확인 null을 구별합니다. 예매/현장가가 있으면 최저가를 대표 가격으로 계산합니다.
- 공연장 이름은 NFKC·대소문자·공백·일부 구두점을 정규화한 정확 일치만 사용합니다. 유일 일치 `matched`, 복수 `ambiguous`, 없음 `not_found`, 이름 없음 `no_name`. `matched` 외 ID는 null입니다.
- Gemini 호출은 기본 30초, 요청당 1회이며 자동 재시도/다른 모델로 전환하지 않습니다. 할당량 초과, 차단, 불완전 JSON, 시간 초과는 503으로 반환합니다. 화면에서 재시도 또는 수동 입력이 가능합니다.
- 이미지 분석/장소 매칭 성공 후에만 UUID 업로드를 남깁니다. 추출은 등록 성공이 아니며 영어 번역도 하지 않습니다.

## 파일 담당과 다른 백엔드의 연결점

| 파일 | 역할 |
|---|---|
| `routers/posters.py` | 이미지 검사 → DB 준비 확인 → AI 추출 → 검수 정보 → 장소 매칭 → 임시 저장 |
| `poster_schemas.py` | 모델 출력과 API 응답 계약. 공통 `schemas.py`와 충돌을 줄이도록 분리 |
| `services/llm.py` | Gemini 공식 SDK 호출, 모델/키/시간 제한, JSON 검증 |
| `services/poster_parser.py` | 날짜·가격 정규화, `needs_review`, 경고 |
| `services/venue_matcher.py` | SQLite 읽기 전용 저장소 및 순수 매칭 함수 |
| `services/poster_uploads.py` | 이미지 검사, UUID 임시 저장/경로 검증/만료 정리 |
| `poster_middleware.py` | 로컬 접근 제한, multipart 전체 용량 제한 |
| `main.py`, `config.py`, `errors.py` | 최소 앱 실행, 환경변수, 공통 오류 형식 |

DB 담당자는 `venues`를 준비하고 `GET /api/venues` 및 프런트 `listVenues`를 연결해야 합니다. 매칭 성공 시 응답의 후보를 바로 선택할 수 있지만, 미매칭 시 전체 공연장 검색은 그 API가 필요합니다. 공연을 최종 저장하는 `POST /api/events`는 별도 구현 대상입니다.

등록 담당자는 `PendingUploadStore.resolve(upload_id)`로 유효한 임시 파일을 얻을 수 있습니다. 실제 파일 구조는 `backend/uploads/pending/{uuid}/poster.{ext}`와 `metadata.json`입니다. 사용자 파일명을 경로로 사용하지 않으며 이 디렉터리는 정적 공개하지 않습니다. 기본 24시간 뒤 만료되고 앱 시작 및 매시간 정리합니다.

**등록 API 연결 시 남은 책임:** `resolve()`는 파일 유효성 확인만 합니다. 미사용 ID의 원자적 선점·중복 사용 409, DB 저장과 최종 이미지 이동의 실패 복구, 최종 `/media` 서빙은 등록 서비스에서 구현해야 합니다. 이 함수를 호출했다고 중복 등록이 방지되는 것은 아닙니다. 사용한 임시 업로드는 등록 완료 후 정리해야 합니다.

## 검증

```sh
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/ruff check backend
```

이미지 형식·손상·용량·MIME 위장, 임시 저장/만료/경로, 정확/모호/미일치 장소 매칭, 날짜/가격, DB 누락, 로컬 접근/CORS, Gemini JSON·차단·할당량·시간 초과를 검증합니다. 테스트는 임시 SQLite와 기존 `docs/API.md` 예시, SDK HTTP 모의 응답을 사용하며 실제 AI 호출 비용은 발생하지 않습니다. 모델 인식 품질은 실제 키·모델과 권한 있는 시연 포스터로 별도 확인해야 합니다.

공식 구현 참고: [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/), [Gemini 구조화 출력](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
