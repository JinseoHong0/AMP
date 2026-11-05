# AMP — REST API 명세 (API.md)

> 버전 **v1.1** · 2026-11-06 · **개발 전 프런트↔백엔드 계약** · Base URL: `http://localhost:8000`  
> 원칙: JSON 키 `snake_case`; 금액 원화 정수; 저장 시각 UTC `Z`; KST 표시(`Asia/Seoul`). 샘플 공연·공연장·ID는 모두 **가상의 예시**.

## 0. 공통 규약

- API prefix는 `/api`; FastAPI 실행 후 `/docs`로 OpenAPI를 확인한다.
- `locale`: `ko`(기본) 또는 `en`. **검수된 문장만** 언어 전환하며 번역이 없는 정보는 임의 생성하지 않는다.
- 공개 조회: `GET /api/events`, `GET /api/events/{id}`, `GET /api/venues`, `GET /api/venues/{id}`, `GET /api/health` 및 추천 요청. 추천 API는 공개 시 호출 남용·비용 통제 필요.
- 관리자 전용: `POST /api/posters/parse`, `POST /api/events`. 로컬 데모(backend loopback)에서만 인증 없이 시연. **공개 배포에는 인증·권한·속도 제한을 적용하기 전까지 비활성화**한다.
- 클라이언트에 AI API 키를 넣지 않는다. 이미지/입력값 크기 제한 및 서버 검증을 수행한다.
- 시각 응답 필드 `starts_at`, `ends_at`, `doors_open_at`, `verified_at`은 UTC `Z` 문자열 또는 `null`. 등록 입력 `*_local`은 **KST 로컬 시각**(예: `2026-11-07T19:00:00`)이다.
- `price_krw`는 **검색 기준으로 사용되는 대표 유효 가격**이다. `price_basis`는 `advance`, `door`, `general`, `null`; 세부 의미는 [DATABASE.md](./DATABASE.md)를 참조한다.
- `data_origin`: `verified|demo`; `demo`는 FE에서 명확히 표시한다.
- 이미지 URL은 `/media/...` 상대 경로 또는 허용된 HTTPS 경로. 없으면 `null`.
- 이벤트 `seating_type`: `standing|seated|mixed|null`; `seat_assignment`: `assigned|unassigned|null`.

### 오류 응답

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 값을 확인해 주세요.",
    "details": {"field": "max_price_krw"}
  }
}
```

| HTTP | `code` 예 | 의미 |
|---|---|---|
| 400 | `INVALID_QUERY`, `INVALID_IMAGE` | 입력 의미·파일 내용 오류 |
| 401/403 | `UNAUTHORIZED`, `FORBIDDEN` | 관리자 인증/권한 필요(공개 환경) |
| 404 | `EVENT_NOT_FOUND`, `VENUE_NOT_FOUND` | 리소스 없음 |
| 409 | `UPLOAD_ALREADY_USED` | 동일 임시 업로드 중복 등록 |
| 413 | `FILE_TOO_LARGE` | 포스터 최대 5MB 초과 |
| 415 | `UNSUPPORTED_FILE_TYPE` | JPG/PNG/WebP가 아님 |
| 422 | `VALIDATION_ERROR`, `VENUE_REQUIRED` | Pydantic/비즈니스 규칙 위반 |
| 503 | `AI_UNAVAILABLE` | AI 서비스 실패; 필터 검색/수동 등록 가능 |
| 500 | `INTERNAL_ERROR` | 서버 오류; 키/비밀 데이터 노출 금지 |

FastAPI 기본 422도 동일한 `error` 구조로 변환한다. 모든 예시 코드·메시지는 합의된 제안 계약이다.

## 1. `GET /api/health`

**200 OK**

```json
{"status":"ok","service":"amp-api","version":"1.1.0"}
```

서버 상태만 표시하며 AI 공급자 연결이 정상임을 보장하지 않는다.

## 2. `GET /api/events` — 공연 목록

| 쿼리 | 타입 / 기본값 | 동작 |
|---|---|---|
| `date` | `YYYY-MM-DD`, 선택 | KST 해당 날짜 |
| `area` | `sinchon|hongdae`, 선택 | 공연장 지역 |
| `max_price_krw` | 정수 >= 0, 선택 | 대표 가격 미확인인 공연은 제외 |
| `seating_type` | `standing|seated|mixed`, 선택 | **공연별 확인값**의 정확 일치만 검색 |
| `upcoming` | boolean / `true` | 미래 공연만 |
| `limit` | 1~50 / `20` | 최대 반환 개수 |
| `locale` | `ko|en` / `ko` | 문장 표시 우선 언어 |

`GET /api/events?date=2026-11-07&area=sinchon&max_price_krw=20000`

**200 OK**

```json
{
  "items": [
    {
      "id": 101,
      "title": "밤의 산책",
      "starts_at": "2026-11-07T10:00:00Z",
      "price_krw": 15000,
      "price_basis": "advance",
      "advance_price_krw": 15000,
      "door_price_krw": 20000,
      "genre": "indie",
      "mood_tags": ["calm", "acoustic"],
      "seating_type": "seated",
      "poster_url": "/media/posters/example-101.jpg",
      "venue": {"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"},
      "data_origin": "demo"
    }
  ],
  "total": 1,
  "limit": 20
}
```

`total`은 필터에 맞는 전체 개수, `items`는 `limit` 내 목록. `status=published`만 공개한다.

## 3. `GET /api/events/{event_id}` — 공연 상세·방문 준비 정보

**200 OK**

```json
{
  "id": 101,
  "venue_id": 1,
  "title": "밤의 산책",
  "starts_at": "2026-11-07T10:00:00Z",
  "ends_at": "2026-11-07T12:00:00Z",
  "doors_open_at": "2026-11-07T09:30:00Z",
  "price_krw": 15000,
  "price_basis": "advance",
  "advance_price_krw": 15000,
  "door_price_krw": 20000,
  "booking_url": null,
  "lineup": ["Sample Band A"],
  "genre": "indie",
  "mood_tags": ["calm", "acoustic"],
  "solo_friendly": true,
  "seating_type": "seated",
  "seat_assignment": "unassigned",
  "drink_policy": "공연별 안내 확인 필요",
  "description_ko": "어쿠스틱 중심의 소규모 공연입니다.",
  "description_en": "A small-scale acoustic show.",
  "admission_notes_ko": "좌석은 비지정석입니다. 선착순으로 입장합니다.",
  "admission_notes_en": "Unassigned seating. Entry is first come, first served.",
  "poster_url": "/media/posters/example-101.jpg",
  "status": "published",
  "data_origin": "demo",
  "source_url": null,
  "verified_at": null
}
```

**FE 표시 순서 추천:** 입장 시작 → 공연 시작 → 가격별 구분/예매 링크 → 좌석 방식/배정 → 드링크 및 공연별 규칙 → 장소/입구 → 출처와 검수일. 입장 시작을 공연 시작 시간으로 대체하지 않는다.

**정책:** 이벤트 `seating_type`/`drink_policy`가 있으면 이벤트 우선. 없으면 장소 `default_*`를 **'공연장 기본 정보(공연별 확인 필요)'** 라벨과 함께 표시한다. `admission_notes_*`는 공연별 공지, `entrance_hint_*`는 장소 동선 안내로 별도 표시한다. 영어 텍스트가 없으면 한국어와 `영문 안내 미확인`을 표시한다. 미공개/취소 이벤트는 404.

## 4. `GET /api/venues` — 기존 공연장 목록·검색 **[v1.1 신규]**

포스터 추출 후 매칭 실패·모호함을 처리하기 위한 수동 선택 API이다. 공연장 신규 생성은 MVP에 포함하지 않는다.

| 쿼리 | 타입 / 기본값 | 동작 |
|---|---|---|
| `q` | 문자열 0~100자, 선택 | 공연장 이름 부분검색(서버가 정규화) |
| `area` | `sinchon|hongdae`, 선택 | 지역 제한 |
| `limit` | 1~50 / `20` | 최대 반환 개수 |

**200 OK**

```json
{
  "items": [
    {"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"},
    {"id": 2, "name": "데모 스테이지", "area": "hongdae"}
  ],
  "total": 2
}
```

검색 결과가 0이면 빈 배열. 자동으로 새 공연장을 생성하지 않는다.

## 5. `GET /api/venues/{venue_id}` — 공연장 기본 가이드

**200 OK**

```json
{
  "id": 1,
  "name": "샘플 라이브 클럽",
  "area": "sinchon",
  "address": "(데모) 서울 서대문구 예시 주소",
  "floor": "B1",
  "entrance_image_url": "/media/entrances/example-venue.jpg",
  "default_seating_type": "seated",
  "default_drink_policy": "공연별 확인 필요",
  "entrance_hint_ko": "건물 입구에서 계단으로 내려갑니다.",
  "entrance_hint_en": "Take the stairs down from the building entrance.",
  "description_ko": "동네 이야기 예시입니다.",
  "description_en": "Example neighborhood story.",
  "source_url": null,
  "verified_at": null,
  "data_origin": "demo"
}
```

장소 기본값이 있다고 해서 특정 공연의 좌석 보장이나 입장 규칙이 확인된 것으로 간주하지 않는다.

## 6. `POST /api/recommend` — 상황 맞춤 추천

자연어에서 조건을 추출하고, **하드 필터 → 소프트 랭킹**으로 실제 DB 공연 중 최대 3개 반환한다.

**요청 `application/json`**

```json
{
  "query": "11월 7일 신촌에서 혼자 볼 만한 2만 원 이하 잔잔한 좌석 공연만 추천해 줘",
  "filters": {
    "date": null,
    "area": null,
    "max_price_krw": null,
    "mood_tags": [],
    "solo_friendly": null,
    "seating_preference": null,
    "seating_requirement": null
  },
  "locale": "ko"
}
```

**입력·우선순위**
- `query`: 최대 500자. 공백만 허용하려면 `filters`에 최소 1개 이상의 유효 조건이 필요.
- 명시적인 UI 필터는 해당 필드에서 AI 추출값보다 우선한다.
- `date`: UI는 KST `YYYY-MM-DD`; LLM은 `today|tomorrow|YYYY-MM-DD|null`을 추출하고 서버가 KST로 변환.
- `area`: `sinchon|hongdae|null`. 지원하지 않는 지역은 필터가 적용된 것처럼 속이지 않고 UI 안내한다.
- `max_price_krw`: 정수 >= 0 또는 null. 가격 미확인 공연은 예산 필터에서 제외한다.
- `mood_tags`: 검수된 태그 중 `calm`, `energetic`, `romantic`, `acoustic` 등 사전에 정한 값만 허용.
- `solo_friendly`: boolean|null, **소프트 선호**.
- `seating_preference`: `seated|standing|null`, **소프트 선호**. 예: '좌석이면 좋겠다'.
- `seating_requirement`: `seated|standing|null`, **하드 필터**. 예: '스탠딩은 절대 안 돼', '좌석만'. `mixed`·`null`은 '좌석만' 조건에서 제외한다.
- 같은 좌석 필드의 선호와 필수가 충돌하면 필수 조건을 적용하고 선호 충돌을 `notice`로 알린다.

**200 OK (예시)**

```json
{
  "applied_filters": {
    "date": "2026-11-07",
    "area": "sinchon",
    "max_price_krw": 20000,
    "mood_tags": ["calm"],
    "solo_friendly": true,
    "seating_preference": null,
    "seating_requirement": "seated"
  },
  "total_matches": 1,
  "items": [
    {
      "event": {
        "id": 101,
        "title": "밤의 산책",
        "starts_at": "2026-11-07T10:00:00Z",
        "price_krw": 15000,
        "price_basis": "advance",
        "advance_price_krw": 15000,
        "door_price_krw": 20000,
        "genre": "indie",
        "mood_tags": ["calm", "acoustic"],
        "seating_type": "seated",
        "poster_url": "/media/posters/example-101.jpg",
        "venue": {"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"},
        "data_origin": "demo"
      },
      "score": 60,
      "matched_tags": ["calm"],
      "reason": "신촌 공연이며 예매가 15,000원으로 안내되어 있고, 차분한 분위기와 좌석 관람 정보가 확인된 공연이에요."
    }
  ],
  "notice": "예매 가능 여부는 예매처에서 확인해 주세요.",
  "used_fallback": false
}
```

`score=60`: `calm` +40, `solo_friendly=true` +20, 하드 좌석 필터는 점수에 더하지 않는다. 카드에 '예매 시 15,000원'처럼 **가격 출처**를 표시하고 구매 가능을 보장하지 않는다.

**0건 응답도 200 OK**

```json
{
  "applied_filters": {"date":"2026-11-07","area":"sinchon","max_price_krw":20000,"mood_tags":["calm"],"solo_friendly":true,"seating_preference":null,"seating_requirement":"seated"},
  "total_matches": 0,
  "items": [],
  "notice": "조건에 맞는 공연이 없습니다.",
  "used_fallback": false
}
```

추천 근거는 DB 필드만으로 구성하며, 미확인 내용을 생성하지 않는다. LLM으로 추천 문장 작성에 실패해도 사실 기반 템플릿을 반환하고 `used_fallback=true`. 의도 추출 실패 시 수동 필터가 있으면 필터 검색으로 진행, 없으면 `503 AI_UNAVAILABLE`.

## 7. `POST /api/posters/parse` — 포스터 추출 + 공연장 자동 매칭 **[확장]**

**요청:** `multipart/form-data`의 `file`; MIME `image/jpeg`, `image/png`, `image/webp`, 최대 5MB. 실제 파일 시그니처 확인. **이 단계는 DB 이벤트 생성이 아니다.**

**200 OK**

```json
{
  "upload_id": "a2d54f46-1fd5-49ee-8f39-3cf9f9f12c61",
  "extracted": {
    "title": "토요일 인디 라이브",
    "starts_at_local": "2026-11-07T20:00:00",
    "doors_open_at_local": null,
    "venue_name": "샘플 라이브 클럽",
    "price_krw": 18000,
    "advance_price_krw": 18000,
    "door_price_krw": 22000,
    "lineup": ["Sample Band A", "Sample Band B"],
    "genre": null
  },
  "venue_match": {
    "status": "matched",
    "venue_id": 1,
    "candidates": [{"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"}]
  },
  "needs_review": ["doors_open_at_local"],
  "warnings": ["입장 시작 시각은 포스터에서 확인되지 않았습니다."]
}
```

`venue_match.status`: `matched`(유일한 이름 일치), `ambiguous`(여러 후보), `not_found`(없음), `no_name`(포스터에 장소명 없음). **`matched`일 때만 `venue_id`가 ID**, 나머지는 `null`. `candidates`는 식별된 기존 장소의 간단한 목록이며 없으면 `[]`.

**매칭 알고리즘:** 추출 `venue_name`을 서버가 유니코드 NFKC/대소문자/공백/일부 구두점 정규화한 뒤 `venues.name`과 유일한 정확 일치를 찾는다. 모호하거나 못 찾으면 수동 선택(`GET /api/venues`), AI가 ID 생성·유사 문자열 자동 확정 금지.

**추출 규칙:** 읽을 수 없는 값은 `null`; 자유롭게 가격·연도·라인업·장르를 추정하지 않는다. 포스터에 구분 가격이 있으면 그 값을 나누어 반환하고 `price_krw`는 최소 확인값. 단일 가격만 있으면 `price_krw`만 채운다. `needs_review`는 **관리자 폼 필드명**을 사용한다(장소 미매칭 시 `venue_id`). 날짜의 연도가 누락되거나 여러 일정이 있으면 검수가 필요함을 알린다. `upload_id`는 안전한 임시 이미지 식별자로 취급한다.

**AI 장애:** 오류를 보여준 뒤 수동 입력 폼으로 복구한다. `upload_id`가 없으면 `POST /api/events` 요청에서 `null`로 보낸다.

## 8. `POST /api/events` — 검수한 공연 등록

**요청 `application/json`**

```json
{
  "upload_id": "a2d54f46-1fd5-49ee-8f39-3cf9f9f12c61",
  "venue_id": 1,
  "title": "토요일 인디 라이브",
  "starts_at_local": "2026-11-07T20:00:00",
  "ends_at_local": null,
  "doors_open_at_local": null,
  "price_krw": 18000,
  "advance_price_krw": 18000,
  "door_price_krw": 22000,
  "booking_url": null,
  "lineup": ["Sample Band A", "Sample Band B"],
  "genre": "indie",
  "mood_tags": ["energetic"],
  "solo_friendly": null,
  "seating_type": null,
  "seat_assignment": null,
  "drink_policy": null,
  "description_ko": null,
  "description_en": null,
  "admission_notes_ko": null,
  "admission_notes_en": null,
  "source_url": null,
  "data_origin": "demo",
  "review_confirmed": true
}
```

**서버 검증:**
1. `venue_id`는 DB에 존재하는 양의 정수 필수. 새 공연장 생성 불가.
2. `title` 1~120자, `starts_at_local` (KST) 필수. `ends_at_local`, `doors_open_at_local`이 있으면 시간 순서 확인.
3. `review_confirmed=true` 필수. 자동 분석 결과를 확인 없이 게시하지 않음.
4. 단일 가격만 있으면 `price_krw`를 대표(`general`). 예매·현장가가 있으면 이들 중 최저를 대표로 계산하며, 요청 `price_krw`가 그와 다르면 422.
5. `price_basis`는 **클라이언트 입력 금지, 서버에서 산출**. 가격 확인 불가이면 금액/기준 모두 `null`. 0원은 검증된 무료.
6. `seating_type`, `seat_assignment`는 정의된 enum. 미확인인 정보는 `null` 허용. 검수되지 않은 영어 안내는 입력 금지.
7. `data_origin=verified`는 실제 출처·확인 과정이 있는 관리자만 설정. 시연 데이터는 `demo`.
8. `upload_id`는 서버가 발급한 미사용 임시 파일 ID 또는 `null`; 파일 이동은 DB 저장과 장애 복구를 고려해 처리.
9. 성공하면 `status=published`, 일시·생성/갱신 시각을 UTC로 저장. 이후 `GET /api/events`에서 조회되고, 추천 하드 조건에 맞으면 추천 가능.

**201 Created**

```json
{"id":121,"status":"published","poster_url":"/media/posters/121.webp","message":"공연이 등록되었습니다."}
```

수동 등록으로 `upload_id=null`이면 `poster_url=null`일 수 있다. 중복 `upload_id` 재사용은 409로 처리한다.

## 9. 정적 미디어·보안·실행 환경

- `GET /media/posters/{filename}`, `GET /media/entrances/{filename}`: 로컬 환경에서 정적 서빙. 공개 배포는 별도 저장소/허용 정책을 검토한다.
- FE: `VITE_API_BASE_URL=http://localhost:8000`; BE: `CORS_ORIGINS=http://localhost:5173`처럼 Origin 제한.
- 이미지 크기뿐 아니라 실제 포맷·업로드 ID 경로 조작을 검증한다. 임시 파일은 주기적으로 정리한다.
- 외부 공개 시 영구 DB/파일 저장, 등록 API 인증, 비용 및 호출량 제한이 필요하다.

## 10. 필수 계약 테스트

1. `GET /api/venues` 목록/검색에서 기존 장소 선택 가능; 없는 장소는 생성되지 않는다.
2. 포스터 장소명 유일 일치 → `matched/venue_id`, 모호함 → `ambiguous/null`, 미일치 → `not_found/null`.
3. 검수 없는 등록·없는 `venue_id` 등록은 거절한다. 정상 등록 후 목록/추천 조건 반영을 확인한다.
4. 예매 20,000원/현장 25,000원이면 `price_krw=20000`, `price_basis=advance`; 2만 원 상한 검색에 포함한다.
5. 가격 `null`은 예산 필터에서 제외; `0`원은 무료에만 사용.
6. 명시적인 '좌석만'은 `seating_requirement=seated` 하드 필터, '좌석이면 좋음'은 `seating_preference=seated` 소프트 랭킹.
7. 행사 좌석 정보가 없는 경우 좌석 필수 조건에 일치시키지 않는다.
8. 공연 시작 `starts_at`과 입장 `doors_open_at`을 혼동하지 않는다.
9. 영문 안내가 없으면 원문+미확인 표기. AI가 공연장 규칙을 생성하지 않는다.
10. 0건 응답은 200/빈 배열, AI 장애 시 명시적 폴백, 잘못된 이미지·JSON은 공통 오류 구조.
11. `demo` 레이블이 프런트에서 표시되고, 관리자 POST가 공개 환경에서 인증 없이 호출되지 않는다.

**연계:** [DATABASE.md](./DATABASE.md) · [AI.md](./AI.md) · [PROJECT.md](./PROJECT.md)
