# AMP — REST API 명세 (API.md)

> 버전 **v1.1** · 2026-11-06 · **개발 전 프런트↔백엔드 계약** · Base URL: `http://localhost:8000`  
> 원칙: JSON 키 `snake_case`; 금액 원화 정수; 저장 시각 UTC `Z`; KST 표시(`Asia/Seoul`). 샘플 공연·공연장·ID는 모두 **가상의 예시**.

## 0. 공통 규약

- API prefix는 `/api`; FastAPI 실행 후 `/docs`로 OpenAPI를 확인한다.
- `locale`: `ko`(기본) 또는 `en`. 공연 영문은 등록 시 자동 생성한 저장값을 사용하고 `AI-translated`로 표시한다. 영문이 없으면 원문을 표시하며 조회 시 번역을 호출하지 않는다. 장소 안내는 기존 검수본을 사용한다. AI 추천 이유는 조회 근거에 기반해 요청 언어로 생성한다.
- 공개 조회: `GET /api/events`, `GET /api/events/{id}`, `GET /api/venues`, `GET /api/venues/{id}`, `GET /api/health` 및 추천 요청. 추천 API는 공개 시 호출 남용·비용 통제 필요.
- 관리자 전용: `POST /api/posters/parse`, `POST /api/events`, `POST /api/events/{event_id}/translate`. 로컬 데모(backend loopback)에서만 인증 없이 시연. **공개 배포에는 인증·권한·속도 제한을 적용하기 전까지 비활성화**한다.
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
| 409 | `UPLOAD_ALREADY_USED`, `TRANSLATION_SOURCE_CHANGED` | 중복 업로드 또는 번역 중 원문 변경 |
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
      "title_en": "Night Walk",
      "translation": {"status": "generated", "generated_at": "2026-11-06T00:00:00Z"},
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

`total`은 필터에 맞는 전체 개수, `items`는 `limit` 내 목록. `status=published`만 공개한다. 목록·상세·추천 카드에는 `title` 원문과 `title_en`, `translation`을 함께 제공한다. `locale`에 따라 FE가 표시값을 선택하며 원문 필드를 번역문으로 덮어쓰지 않는다.

## 3. `GET /api/events/{event_id}` — 공연 상세·방문 준비 정보

**200 OK**

```json
{
  "id": 101,
  "venue_id": 1,
  "title": "밤의 산책",
  "title_en": "Night Walk",
  "translation": {"status": "generated", "generated_at": "2026-11-06T00:00:00Z"},
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
  "drink_policy_en": "Please check the guidance for this event.",
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

**정책:** 이벤트 `seating_type`/`drink_policy`가 있으면 이벤트 우선. 없으면 장소 `default_*`를 **'공연장 기본 정보(공연별 확인 필요)'** 라벨과 함께 표시한다. `admission_notes_*`는 공연별 공지, `entrance_hint_*`는 장소 동선 안내로 별도 표시한다. 영문은 `translation.status=generated`이면 자동 번역 표시와 원문 보기를 제공하고, `reviewed`이면 검수본으로 표시한다. 영어가 없으면 한국어와 `영문 번역 준비 안 됨`을 표시한다. 미공개/취소 이벤트는 404.

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

## 6. `POST /api/recommend` — AI 조회·상황 맞춤 추천

AI가 원문을 해석하고 내부 DB 조회 도구를 호출해 후보를 탐색·재조회한 뒤 최대 3개를 추천한다. 서버는 조회 실행, 필수 조건 유지, ID·근거 검증을 맡는다. 문장별 판단표와 고정 가중치 점수는 사용하지 않는다. 내부 도구 계약은 [AI.md](./AI.md) §4를 따른다.

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

- `query`: 최대 500자. 공백뿐이면 `filters`에 최소 1개의 유효 조건이 필요하며, 둘 다 없으면 422.
- `filters`는 선택적 UI 입력이다. 생략/`null`/빈 배열은 미설정이며 AI 해석을 덮어쓰지 않는다. 명시한 필드만 같은 의미의 자연어 조건보다 우선한다.
- UI `date`: KST `YYYY-MM-DD`; `area`: `sinchon|hongdae|null`; `max_price_krw`: 정수 >=0 또는 `null`; `seating_requirement`: `seated|standing|null`. 이 값들은 필수 조건으로 적용한다.
- UI `mood_tags`: 검수된 허용 태그 배열, `solo_friendly`: boolean|null, `seating_preference`: `seated|standing|null`은 AI에 전달하는 선호다. 자연어는 이 UI 항목이나 태그에 한정되지 않는다.
- AI는 날짜/시간 구간, 출연진, 장르, 설명 등도 조회 조건으로 사용할 수 있다. 필수/선호 해석이 모호하거나 필수 요청을 지원하지 못하면 질문을 반환한다.
- `seating_requirement=seated`는 공연별 명시값이 같은 경우만 충족하며 `mixed|null`이나 공연장 기본값은 충족으로 간주하지 않는다. 필수와 선호가 충돌하면 필수를 적용하고 `notice`에 알린다.
- UI 필수 필터와 AI가 최초 조회에서 확정한 필수 조건을 서버가 보관하고 모든 후속 도구 호출에 적용한다. 재조회는 탐색 조건만 바꿀 수 있다.

**200 OK (예시)**

```json
{
  "status": "ok",
  "applied_filters": {
    "date": "2026-11-07",
    "area": "sinchon",
    "max_price_krw": 20000,
    "mood_tags": [],
    "solo_friendly": null,
    "seating_preference": null,
    "seating_requirement": "seated"
  },
  "total_matches": 1,
  "items": [
    {
      "event": {
        "id": 101,
        "title": "밤의 산책",
        "title_en": "Night Walk",
        "translation": {"status": "generated", "generated_at": "2026-11-06T00:00:00Z"},
        "starts_at": "2026-11-07T10:00:00Z",
        "price_krw": 15000,
        "price_basis": "advance",
        "advance_price_krw": 15000,
        "door_price_krw": 20000,
        "genre": "indie",
        "mood_tags": [
          "calm",
          "acoustic"
        ],
        "seating_type": "seated",
        "poster_url": "/media/posters/example-101.jpg",
        "venue": {
          "id": 1,
          "name": "샘플 라이브 클럽",
          "area": "sinchon"
        },
        "data_origin": "demo"
      },
      "matched_tags": [
        "calm"
      ],
      "reason": "신촌 공연이며 예매가 15,000원으로 안내되어 있고, 차분한 분위기와 좌석 관람 정보가 확인된 공연이에요."
    }
  ],
  "notice": "예매 가능 여부는 예매처에서 확인해 주세요.",
  "used_fallback": false,
  "applied_conditions": {
    "all": [
      {
        "field": "starts_at",
        "op": "gte",
        "value": "2026-11-07T00:00:00+09:00"
      },
      {
        "field": "starts_at",
        "op": "lt",
        "value": "2026-11-08T00:00:00+09:00"
      },
      {
        "field": "area",
        "op": "eq",
        "value": "sinchon"
      },
      {
        "field": "price_krw",
        "op": "lte",
        "value": 20000
      },
      {
        "field": "seating_type",
        "op": "eq",
        "value": "seated"
      }
    ]
  },
  "preferences": [
    "혼자 관람하기 좋은 공연",
    "잔잔한 분위기"
  ],
  "search_limited": false,
  "clarification": null
}
```

**응답 필드**

| 필드 | 의미 |
|---|---|
| `status` | `ok` 또는 `needs_clarification` |
| `applied_filters` | 기존 UI 필드 형태의 표시용 요약. 단일 날짜/지역/상한/좌석으로 표현 가능한 확정 조건과 명시 UI 선호만 채움. 표현 불가능한 조건은 `applied_conditions`에 보존 |
| `applied_conditions` | 실제 적용된 필수 조건의 `EventQuery` 식. 날짜 구간·복합 조건도 포함. `null`은 조회 전이며, 빈 `all`은 사용자 필수 조건 없음 |
| `preferences` | AI가 원문에서 이해한 선호를 설명하는 문장 배열. 고정 태그/점수로 축약하지 않음 |
| `total_matches` | 공개·미래 공연 중 확정 필수 조건 전체 일치 건수. 탐색 키워드 결과나 추천 개수와 다름. 조회 전은 `null` |
| `items` | AI가 선택한 순서의 최대 3개. `event`는 DB 카드, `matched_tags`는 조회 근거로 검증된 태그, `reason`은 근거 기반 AI 이유. `score` 없음 |
| `search_limited` | 필수 조건 후보 전체를 검토하지 못했으면 `true`; `notice`로 조회 범위/한도 안내 |
| `clarification` | 확인 질문 문자열 또는 `null`. `needs_clarification`이면 필수 |
| `used_fallback` | 검증된 선택 결과의 이유만 템플릿으로 대체했거나, 빈 자연어+수동 필터 검색이면 `true` |
| `notice` | 결과 없음, 탐색 제한, 조건 충돌, 미확인 정보 등의 안내 문자열 또는 `null` |

카드에는 '예매 시 15,000원'처럼 **가격 출처**를 표시하고 구매 가능을 보장하지 않는다. 공연 영문은 등록 시 생성해 저장한 번역을 사용하고, 추천 이유는 조회 사실에 근거해 요청 언어로 생성한다.

**결과 없음·질문·장애**

- 필수 조건 전체가 0건이면 `200`, `status=ok`, `total_matches=0`, `items=[]`, `search_limited=false`, `clarification=null`, `used_fallback=false`와 안내를 반환한다.
- 후보가 있지만 탐색을 끝내지 못했거나 적합한 후보를 고르지 못했다면 `total_matches`를 0으로 바꾸지 않는다. 탐색 미완료는 `search_limited=true`와 사유를 표시하며, 최종 후보가 없으면 `items=[]`다.
- 확인이 필요하면 `200`, `status=needs_clarification`, `items=[]`, 질문을 반환한다. 조회 전이면 `applied_conditions=null`, `total_matches=null`, `search_limited=false`. 조회 후라면 적용 조건/집계를 유지한다. FE는 이를 결과 0건으로 표시하지 않고 사용자가 원문/필터를 수정해 새 요청을 보내게 한다. MVP는 대화 세션을 저장하지 않는다.
- 자연어 검색 도중 AI 실패/시간 초과로 검증된 추천을 완성하지 못하면 `503 AI_UNAVAILABLE`. 수동 필터만으로 자동 대체해 자연어 조건을 무시하지 않는다.
- 이미 ID·순위가 검증됐으나 이유 문구에 문제가 있는 경우에만 사실 템플릿으로 대체하고 `used_fallback=true`를 반환한다.
- `query`가 비어 있고 UI 필터만 있으면 필수 조건에 맞는 시간순 목록 최대 3개와 템플릿 이유를 반환할 수 있다. `used_fallback=true`, 선호에 따른 AI 순위를 적용하지 않았다는 안내를 표시한다. 표시한 개수보다 전체 후보가 많으면 `search_limited=true`.

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

## 8. `POST /api/events` — 원문 확인·영문 자동 생성·공연 등록

포스터 파싱 후 수정한 내용과 수동 입력 모두 같은 경로를 사용한다. 등록자는 최종 원문만 제출하며 서버가 영어 번역을 생성해 함께 저장한다. 포스터 업로드만으로 번역/등록을 완료하지 않는다.

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
  "drink_policy": "음료 1잔 주문이 필요합니다.",
  "description_ko": "어쿠스틱 중심의 소규모 공연입니다.",
  "admission_notes_ko": "좌석은 비지정석입니다. 선착순으로 입장합니다.",
  "source_url": null,
  "data_origin": "demo",
  "review_confirmed": true
}
```

**서버 검증:**
1. `venue_id`는 DB에 존재하는 양의 정수 필수. 새 공연장 생성 불가.
2. `title` 1~120자, `starts_at_local` (KST) 필수. `ends_at_local`, `doors_open_at_local`이 있으면 시간 순서 확인.
3. `review_confirmed=true` 필수. 등록자가 원본 공연 정보를 확인했다는 뜻이며 자동 생성 영문의 사람 검수를 요구하지 않는다.
4. 단일 가격만 있으면 `price_krw`를 대표(`general`). 예매·현장가가 있으면 이들 중 최저를 대표로 계산하며, 요청 `price_krw`가 그와 다르면 422.
5. `price_basis`는 **클라이언트 입력 금지, 서버에서 산출**. 가격 확인 불가이면 금액/기준 모두 `null`. 0원은 검증된 무료.
6. `seating_type`, `seat_assignment`는 정의된 enum. 미확인인 정보는 `null` 허용. `title_en`, `description_en`, `admission_notes_en`, `drink_policy_en`과 번역 메타데이터는 서버 생성 전용이며 요청에 포함하면 422. 한국어 선택 텍스트는 필드별 최대 4,000자이며 공백뿐이면 null로 정규화한다.
7. `data_origin=verified`는 실제 출처·확인 과정이 있는 관리자만 설정. 시연 데이터는 `demo`.
8. `upload_id`는 서버가 발급한 미사용 임시 파일 ID 또는 `null`; 파일 이동은 DB 저장과 장애 복구를 고려해 처리.
9. 검증된 최종 `title`, `description_ko`, `admission_notes_ko`, `drink_policy`로 영어를 생성한다. 전체 번역 처리 한도 15초·최대 1회 재시도. 성공하면 네 영문 필드와 상태/시각/원문 지문을 함께 저장하고, 실패하면 영문은 null, 상태는 `failed`로 원문 공연만 저장한다.
10. 성공하면 `status=published`, 일시·생성/갱신 시각을 UTC로 저장. 이후 `GET /api/events`에서 조회되고, 추천 하드 조건에 맞으면 추천 가능.

**201 Created**

```json
{
  "id": 121,
  "status": "published",
  "poster_url": "/media/posters/121.webp",
  "translation": {"status": "generated", "generated_at": "2026-11-06T00:00:00Z"},
  "warnings": [],
  "message": "공연과 영어 번역이 등록되었습니다."
}
```

수동 등록으로 `upload_id=null`이면 `poster_url=null`일 수 있다. 중복 `upload_id` 재사용은 409로 처리한다.

### 번역 응답·실패 계약

- `translation`은 `{status, generated_at}`. 상태는 `not_requested|generated|failed|reviewed`, 생성 시각은 UTC Z 또는 null이다. 원문 지문은 서버 내부용이다. 영문 본문은 `GET /api/events/{id}`로 조회한다.
- 등록 중 번역만 실패해도 **201**이다. `translation={"status":"failed","generated_at":null}`, `warnings=["공연은 등록되었으나 영어 번역을 생성하지 못했습니다."]`, 등록 성공 메시지와 기존 공연 ID를 반환한다. FE는 공연을 다시 등록하지 않고 아래 번역 재시도를 제공한다.
- 등록 입력 검증/DB 저장 실패는 원래 오류로 반환한다. 번역 생성만 성공한 상태를 공연 등록 성공으로 알리지 않는다.
- 조회에서는 원문 지문이 맞는 `generated|reviewed` 번역만 반환한다. 오래된 번역은 노출하지 않고 `not_requested`와 null 영문을 반환한다. 번역 실패는 원문 데이터의 미확인과 다른 상태다.

### `POST /api/events/{event_id}/translate` — 저장된 공연 번역 재시도

- 관리자 전용, 요청 body 없음. 등록된 원문만 사용하며 영문/원문 텍스트를 이 요청으로 수정하지 않는다. 공개 배포의 인증·권한·호출 제한은 등록 API와 동일하다.
- 성공 **200**: `{"id":121,"translation":{"status":"generated","generated_at":"2026-11-06T00:00:00Z"}}`. 같은 원문에 유효한 `generated|reviewed` 번역이 있으면 모델 호출 없이 저장된 상태/시각을 반환한다.
- 없는 공연은 404. 번역 실패는 `503 AI_UNAVAILABLE`; 원문은 유지하고 정상 번역이 없는 경우 `failed`로 기록한다. 오류 `details`에는 `event_id`와 현재 `translation` 상태를 포함한다.
- 번역 중 원문이 바뀌면 결과를 저장하지 않고 `409 TRANSLATION_SOURCE_CHANGED`. 동시 요청의 정상 번역을 뒤늦은 실패가 지우지 않도록 저장 직전에 재검사한다.
- 새 공연/포스터를 생성하지 않으며 `upload_id`를 다시 소비하지 않는다.

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
6. AI가 원문에서 필수/선호를 구분하고 실제 조회 도구를 호출한다. 재조회가 최초 필수 조건/UI 필터를 완화하지 않는다.
7. 행사 좌석 정보가 없는 경우 좌석 필수 조건에 일치시키지 않는다.
8. 공연 시작 `starts_at`과 입장 `doors_open_at`을 혼동하지 않는다.
9. 영문 입력 없이 등록하면 영어 자동 생성·저장, EN 화면은 자동 번역 표시와 원문 보기 제공. 번역이 없으면 원문 표시, 원문에 없는 규칙은 생성하지 않는다.
10. 0건과 확인 질문/탐색 미완료를 구분한다. 자연어 AI 장애는 503, 이유만 대체한 경우 `used_fallback=true`; 잘못된 이미지·JSON은 공통 오류 구조.
11. `demo` 레이블이 프런트에서 표시되고, 관리자 POST가 공개 환경에서 인증 없이 호출되지 않는다.
12. 조회하지 않은 ID·조작된 근거·취소된 공연을 추천하지 않으며, 응답에 고정 점수를 포함하지 않는다.
13. 포스터 추출값을 수정한 최종 원문으로 번역하며, 선택 원문 null은 영문도 null.
14. 번역 실패도 원문 등록은 201, 재시도는 기존 ID 유지. 원문 변경·동시 성공/실패가 이전 번역으로 덮어쓰지 않는다.

**연계:** [DATABASE.md](./DATABASE.md) · [AI.md](./AI.md) · [PROJECT.md](./PROJECT.md)
