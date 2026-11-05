# AMP — REST API 명세 (API.md)

> 버전: 1.0 · 상태: 개발 전 계약 · Base URL: `http://localhost:8000`  
> 규칙: JSON `snake_case`, UTF-8, UTC ISO 8601(`Z`) 저장, 표시 시 `Asia/Seoul` 변환

## 0. 공통 정책

- 기본 경로 `/api`; 전체 API 스키마는 FastAPI의 `/docs`에서 확인.
- 공개 읽기 API는 조회만; `POST /api/posters/parse`, `POST /api/events`는 **관리자 데모 환경에서만** 허용.
- 클라이언트에서 백엔드 API 키(LLM 토큰)를 절대로 직접 호출하지 않음.
- `locale`: `ko`(기본) 또는 `en`.
- 오류 응답은 동일한 구조로 통일. FastAPI 기본 validation error도 전역 핸들러로 변환한다.
- 날짜 필터는 **KST 기준 YYYY-MM-DD**, 이벤트 시각은 **UTC ISO 8601** 형식으로 반환.
- 이미지 주소는 상대 `/media/posters/{filename}` 또는 검증된 HTTPS URL. `null` 허용.
- 응답의 `data_origin`은 `verified|demo`이며 `demo`는 반드시 시각적으로 표시.

### 공통 에러

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 값을 확인해 주세요.",
    "details": {"field": "max_price_krw"}
  }
}
```

| HTTP | code 예시 | 처리 |
|---|---|---|
| 400 | `INVALID_QUERY`, `INVALID_IMAGE` | 클라이언트 입력 수정 |
| 401 | `UNAUTHORIZED` | 등록 권한 필요 |
| 404 | `EVENT_NOT_FOUND`, `VENUE_NOT_FOUND` | 없는 리소스 |
| 413 | `FILE_TOO_LARGE` | 5MB 초과 |
| 415 | `UNSUPPORTED_FILE_TYPE` | jpeg/png/webp 이외 |
| 422 | `VALIDATION_ERROR`, `VENUE_REQUIRED` | 필드 형식/필수값 오류 |
| 503 | `AI_UNAVAILABLE` | AI 일시 장애; 수동 입력/필터로 복구 |
| 500 | `INTERNAL_ERROR` | 서버 오류; 키·원본 이미지 등 민감정보 응답 금지 |

> 에러 코드와 HTTP 지위는 **권장 계약안**이며, 팀원이 구현 전에 함께 확정한다.

## 1. `GET /api/health`

**용도:** 백엔드 살아 있는지 확인. AI 공급자 연결 성공 여부를 보장하지 않는다.

**200 OK**
```json
{"status":"ok","service":"amp-api","version":"1.0.0"}
```

## 2. `GET /api/events`

**Query parameters**

| 이름 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `date` | string `YYYY-MM-DD` | 없음 | 해당 KST 날짜 공연 |
| `area` | enum `sinchon|hongdae` | 없음 | 지역 필터 |
| `max_price_krw` | integer `>=0` | 없음 | 상한 이하, 가격 미확인 제외 |
| `upcoming` | boolean | `true` | 현재 시점 이후 공연만 |
| `limit` | integer `1..50` | `20` | 결과 개수 |
| `locale` | enum `ko|en` | `ko` | 출력 언어 우선순위 |

**예시** `GET /api/events?date=2026-11-07&area=sinchon&max_price_krw=20000`

**200 OK**
```json
{
  "items": [
    {
      "id": 101,
      "title": "밤의 산책",
      "starts_at": "2026-11-07T10:00:00Z",
      "price_krw": 15000,
      "genre": "indie",
      "mood_tags": ["calm", "acoustic"],
      "poster_url": "/media/posters/example-101.jpg",
      "venue": {"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"},
      "data_origin": "demo"
    }
  ],
  "total": 1,
  "limit": 20
}
```

> `title`·공연장명 등은 **스키마 설명을 위한 가상 예시**다. 실제 존재하는 공연·공연장이란 뜻이 아니다.

## 3. `GET /api/events/{event_id}`

**200 OK**
```json
{
  "id": 101,
  "title": "밤의 산책",
  "starts_at": "2026-11-07T10:00:00Z",
  "ends_at": null,
  "price_krw": 15000,
  "genre": "indie",
  "mood_tags": ["calm", "acoustic"],
  "solo_friendly": true,
  "lineup": ["Sample Band A"],
  "description_ko": "어쿠스틱 중심의 소규모 공연입니다.",
  "description_en": "A small-scale acoustic show.",
  "seating_type": "standing",
  "drink_policy": "1 drink included",
  "poster_url": "/media/posters/example-101.jpg",
  "venue_id": 1,
  "status": "published",
  "data_origin": "demo",
  "source_url": null,
  "verified_at": null
}
```

`404`: 존재하지 않는 ID 또는 공개되지 않은 공연. `cancelled` 공연은 목록/추천에 미노출; 별도 조회 정책이 필요할 때까지 공개 상세에서도 숨김.

## 4. `GET /api/venues/{venue_id}`

**200 OK**
```json
{
  "id": 1,
  "name": "샘플 라이브 클럽",
  "area": "sinchon",
  "address": "(데모) 서울 서대문구 예시 주소",
  "floor": "B1",
  "entrance_image_url": "/media/entrances/example-venue.jpg",
  "default_seating_type": "standing",
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

**우선순위:** 공연 상세의 `seating_type`, `drink_policy`가 `null`이 아니면 이벤트 값을 우선한다. 값이 둘 다 없으면 `확인 필요`로 표시한다.

## 5. `POST /api/recommend`

**용도:** AI로 검색 의도를 추출하고, 실제 DB 필터링·정렬로 최대 3개 추천.

**Request `application/json`**
```json
{
  "query": "오늘 신촌에서 혼자 2만원 이하 잔잔한 공연 추천해줘",
  "filters": {
    "date": null,
    "area": null,
    "max_price_krw": 20000,
    "mood_tags": [],
    "solo_friendly": null
  },
  "locale": "ko"
}
```

**입력 규칙**
- `query`는 공백만일 수 있으나, 그 경우 `filters`에 최소 하나의 의미 있는 조건이 필요.
- 사용자가 고른 **필터 칩 값은 AI 추출 결과보다 우선**.
- `query` 길이 0..500자; 긴 내용은 422로 거절.
- 모델의 `today`, `tomorrow` 같은 상대 날짜는 서버의 `Asia/Seoul` 시계로 해석.
- `area` 정규 값: `sinchon`, `hongdae` (다른 지역 추출 시 null/경고 처리).
- `mood_tags`는 사전에 정의한 태그만 수용. 예: `calm`, `energetic`, `romantic`, `acoustic`.
- `solo_friendly`는 하드 필터가 아니라 가중치 선호. 미확인 정보는 근거로 사용하지 않음.

**200 OK**
```json
{
  "applied_filters": {
    "date": "2026-11-05",
    "area": "sinchon",
    "max_price_krw": 20000,
    "mood_tags": ["calm"],
    "solo_friendly": true
  },
  "total_matches": 1,
  "items": [
    {
      "event": {
        "id": 101,
        "title": "밤의 산책",
        "starts_at": "2026-11-05T12:00:00Z",
        "price_krw": 15000,
        "genre": "indie",
        "mood_tags": ["calm"],
        "poster_url": null,
        "venue": {"id": 1, "name": "샘플 라이브 클럽", "area": "sinchon"},
        "data_origin": "demo"
      },
      "score": 60,
      "matched_tags": ["calm"],
      "reason": "2만 원 이하이며 차분한 분위기 태그가 확인된 공연이에요."
    }
  ],
  "notice": null,
  "used_fallback": false
}
```

`total_matches`는 하드 필터에 일치한 전체 공연 건수이며, `items`는 최대 3개이다. 위 날짜는 API 예시일 뿐 **행사 날짜를 뜻하지 않는다**.

**0건 응답도 200**
```json
{"applied_filters":{"date":"2026-11-05","area":"sinchon","max_price_krw":20000,"mood_tags":["calm"],"solo_friendly":true},"total_matches":0,"items":[],"notice":"조건에 맞는 공연이 없습니다.","used_fallback":false}
```

**실패 복구:** 추천 이유만 생성 실패하면 `reason`을 사실 기반 템플릿으로 대체하고 `used_fallback=true`; 의도 추출이 실패했지만 수동 칩이 있다면 칩으로만 검색; 둘 다 불가능하면 `503 AI_UNAVAILABLE`.

## 6. `POST /api/posters/parse`

**용도:** 포스터에서 정보 **추출만** 수행. DB 이벤트는 이 단계에서 생성하지 않음.

- Content-Type: `multipart/form-data`
- Form field: `file` (`image/jpeg`, `image/png`, `image/webp`)
- 크기 제한: 5MB (서버에서 콘텐츠 검사 필요)
- 권한: 로컬 시연 관리자만 사용, 외부 공개 시 인증 필수
- 구현 참고: FastAPI `UploadFile` + `python-multipart`

**200 OK**
```json
{
  "upload_id": "a2d54f46-1fd5-49ee-8f39-3cf9f9f12c61",
  "extracted": {
    "title": "토요일 인디 라이브",
    "starts_at_local": "2026-11-07T19:00:00",
    "venue_name": "샘플 라이브 클럽",
    "price_krw": null,
    "lineup": ["Sample Band A", "Sample Band B"],
    "genre": null
  },
  "needs_review": ["price_krw", "venue_name"],
  "warnings": ["가격을 포스터에서 확인하지 못했습니다."]
}
```

**주의사항**
- `upload_id`는 서버가 생성한 임시 파일 식별자이며, 클라이언트가 경로를 조작하지 못함.
- 서버는 임시 이미지 경로를 보관했다가 성공적인 등록 시 최종 경로로 이동한다. 미등록 임시 파일은 정리한다.
- 추출값은 **증거 없는 장르·분위기·드링크 정책을 만들어내지 않음**.
- `starts_at_local`은 `Asia/Seoul` 현지 시각. 시간 정보가 없으면 `null`.
- 추출 실패는 사용자에게 알리고 수동 입력 제공.

## 7. `POST /api/events`

**용도:** 사람이 수정·검수한 데이터를 등록하고, 선택된 공연장과 연결한다.

**Request `application/json`**
```json
{
  "upload_id": "a2d54f46-1fd5-49ee-8f39-3cf9f9f12c61",
  "venue_id": 1,
  "title": "토요일 인디 라이브",
  "starts_at_local": "2026-11-07T19:00:00",
  "ends_at_local": null,
  "price_krw": 15000,
  "lineup": ["Sample Band A", "Sample Band B"],
  "genre": "indie",
  "mood_tags": ["energetic"],
  "solo_friendly": null,
  "seating_type": null,
  "drink_policy": null,
  "description_ko": null,
  "description_en": null,
  "source_url": null,
  "data_origin": "demo",
  "review_confirmed": true
}
```

**검증 규칙**
- `venue_id`, `title`(1..120자), `starts_at_local`, `review_confirmed=true` 필수.
- `venue_id`는 실제 존재하는 공연장만 유효.
- `price_krw`: `null` 허용, 정수 0 이상. 최대 가격 필터 조건에 가격 미확인은 포함되지 않음.
- `data_origin=verified`는 검증된 실제 출처와 확인 프로세스를 거친 관리자만 설정.
- 등록 시 `status=published`, `created_at` 현재 UTC, `starts_at` KST → UTC 변환.
- 임시 이미지 파일 식별자 `upload_id`는 유효한 것만 허용; 미사용이면 `null`.
- `review_confirmed=false`면 등록 거절.

**201 Created**
```json
{
  "id": 121,
  "status": "published",
  "poster_url": "/media/posters/121.webp",
  "message": "공연이 등록되었습니다."
}
```

**409 선택:** 같은 포스터 업로드 ID의 중복 등록 시 `UPLOAD_ALREADY_USED`. DB에 이벤트 레코드가 커밋된 이후 목록에서 조회 가능; 추천 조건 일치는 별도.

## 8. 미디어 및 실행 환경

- `GET /media/posters/{filename}`, `GET /media/entrances/{filename}`: 로컬/개발 시 서버 정적 파일 서빙; 퍼블릭 배포 시 외부 스토리지나 파일 서빙 정책을 명시한다.
- `VITE_API_BASE_URL=http://localhost:8000`을 프런트에서 사용.
- `CORS_ORIGINS=http://localhost:5173` 등 실제 프런트 Origin 목록만 허용.
- 공개된 프런트에 관리자 비밀키나 LLM API 키를 빌드 변수로 삽입하지 않는다.
- 데이터베이스의 이벤트/이미지는 **해커톤 로컬 데모 기준**으로 영구 보관한다. 인터넷 배포 시 별도 영구 스토리지 계획이 필요.

## 9. 프런트↔백엔드 계약 테스트

1. 검색 3개 이상 일치 시 결과 3개, `total_matches`는 실제 개수.
2. `max_price_krw=0`이면 무료 공연만, 가격 `null` 제외.
3. 날짜가 달라지면 해당 날짜의 공연만 검색.
4. `date=today` 추출 시 KST 기준 계산.
5. 새 공연 등록 201 이후 `GET /api/events`에서 확인.
6. 추천과 무관한 신규 공연을 등록해도 추천 결과를 억지로 바꾸지 않음.
7. 포스터 업로드 6MB, PDF, 깨진 이미지에 각각 오류 반환.
8. Vision 서비스 장애 시 등록 폼에서 수동 입력 가능.
9. 존재하지 않는 이벤트/공연장 ID 요청은 404.
10. JSON 유효성 위반은 공통 `error` 구조로 반환.

**참고 자료:** [FastAPI 업로드](https://fastapi.tiangolo.com/tutorial/request-files/) · [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)
