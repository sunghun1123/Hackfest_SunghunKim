# API Specification

Base URL (dev): `http://localhost:8000`
Base URL (prod): `https://broken-lunch-gr.ondigitalocean.app`

모든 요청/응답은 JSON. 인증은 헤더 `X-Device-Id: <uuid>`.

---

## Endpoints

### GET `/restaurants/nearby`

내 위치 기준 주변 식당 + 각 식당의 최저가 메뉴 반환. 지도/리스트 메인 쿼리.
**메뉴 없는 식당도 포함** (include_empty=true 기본값). `menu_status` 필드로 구분.

**Query params:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `lat` | float | ✅ | — | 사용자 위도 |
| `lng` | float | ✅ | — | 사용자 경도 |
| `radius_m` | int | ❌ | 2000 | 반경 (미터) |
| `tier` | string | ❌ | all | `survive`, `cost_effective`, `luxury` 필터 |
| `verified_only` | bool | ❌ | false | `true`면 human_verified 메뉴만 |
| `include_empty` | bool | ❌ | true | `false`면 메뉴 없는 식당 제외 |
| `limit` | int | ❌ | 100 | 최대 결과 수 (빈 식당 포함되므로 늘림) |

**Response 200:**
```json
{
  "restaurants": [
    {
      "id": "uuid",
      "name": "Jet's Pizza",
      "category": "pizza",
      "lat": 42.9634,
      "lng": -85.6681,
      "distance_m": 320,
      "google_rating": 4.3,
      "app_rating": 4.5,
      "menu_status": "populated_verified",
      "cheapest_menu": {
        "id": "uuid",
        "name": "8-corner slice",
        "price_cents": 450,
        "tier": "survive",
        "verification_status": "human_verified"
      }
    },
    {
      "id": "uuid",
      "name": "Corner Deli",
      "category": "sandwich",
      "lat": 42.9534,
      "lng": -85.6581,
      "distance_m": 450,
      "google_rating": 4.1,
      "app_rating": null,
      "menu_status": "empty",
      "cheapest_menu": null
    }
  ],
  "count": 2
}
```

**`menu_status` 값:**
- `populated_verified` — 메뉴 있음, human_verified
- `populated_ai` — 메뉴 있음, AI parsed만 됨
- `empty` — 식당 등록됐지만 메뉴 없음 (첫 제보 보너스 대상)

**빈 식당 (`menu_status=empty`) 처리:**
- `cheapest_menu`는 `null`
- 프론트에서 회색 핀으로 표시 + "+15 pts 첫 제보" CTA

---

### GET `/restaurants/{restaurant_id}`

식당 상세 + 전체 메뉴 (tier별 그룹).

**Response 200:**
```json
{
  "id": "uuid",
  "name": "Pita House",
  "address": "456 Division Ave, Grand Rapids, MI",
  "phone": "+1-616-555-0123",
  "website": "https://pitahouse.com",
  "lat": 42.9534,
  "lng": -85.6681,
  "google_rating": 4.5,
  "app_rating": 4.2,
  "rating_count": 23,
  "hours": { "monday": "11:00-21:00" },
  "menu": {
    "survive": [
      {
        "id": "uuid",
        "name": "Falafel 2p",
        "description": "two pieces with sauce",
        "price_cents": 399,
        "photo_url": null,
        "verification_status": "human_verified",
        "confirmation_count": 5,
        "source": "gemini_web",
        "last_verified_at": "2026-04-15T10:23:00Z"
      }
    ],
    "cost_effective": [],
    "luxury": []
  }
}
```

---

### POST `/submissions`

사용자가 메뉴 제보. 자동 승인 + 포인트 지급.

**Headers:** `X-Device-Id: <uuid>`

**Request:**
```json
{
  "restaurant_id": "uuid",
  "menu_name": "Falafel wrap",
  "price_cents": 699,
  "photo_url": "https://spaces.digitaloceanspaces.com/...",
  "gemini_parsed": {
    "confidence": 0.92,
    "raw_text": "..."
  },
  "source": "gemini_photo"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "menu_item_id": "uuid",
  "status": "accepted",
  "points_awarded": 15,
  "is_first_submission": true,
  "bonus_message": "🎉 First to register this restaurant! +5 bonus",
  "user_total_points": 240,
  "user_level": 3,
  "level_up": false
}
```

`is_first_submission`이 true면 추가 보너스 +5 (기본 +10 → 총 +15).
프론트에서 셀러브레이션 애니메이션 트리거할 때 사용.

**Behavior:**
- 동일 `restaurant_id` + fuzzy match menu_name + 가격 차이 $1 미만 → `confirmation_weight` 증가 (새 row 생성 안 함)
- 가격 차이 $1 ~ $3 → 해당 메뉴 `verification_status = 'disputed'` 로 전환
- 가격 차이 > $3 또는 완전 새 메뉴 → 새 row 생성, `verification_status = 'ai_parsed'`
- submissions 테이블에 항상 기록 (감사용)
- 디바이스에 포인트 지급 (기본 +10) + `point_history` 기록
- 레벨업 발생 시 `level_up: true`

---

### POST `/confirmations`

"이 가격 맞아요" / "이 가격 달라요" 버튼 액션.

**Headers:** `X-Device-Id: <uuid>`

**Request (동의):**
```json
{
  "menu_item_id": "uuid",
  "is_agreement": true
}
```

**Request (반대 + 새 가격 제보):**
```json
{
  "menu_item_id": "uuid",
  "is_agreement": false,
  "reported_price": 750
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "menu_item_updated": {
    "id": "uuid",
    "verification_status": "human_verified",
    "confirmation_weight": 5,
    "confirmation_count": 3
  },
  "points_awarded": 3,
  "user_total_points": 238
}
```

**Behavior:**
- 동일 사용자가 같은 메뉴에 대해 이미 confirm 했으면 409 Conflict
- `is_agreement = true`: `confirmation_weight += user_level_weight`
- 임계값 (weight 5) 넘으면 자동으로 `verification_status → 'human_verified'` (DB 트리거)
- `is_agreement = false`: 해당 메뉴 status → `'disputed'`, `reported_price` 있으면 새 `menu_item` 생성
- 포인트 +3 지급

---

### POST `/parse-menu-image`

Gemini Vision으로 메뉴판 사진 파싱.

**Headers:** `X-Device-Id: <uuid>` (rate limit용)

**Request (multipart/form-data):**
- `image`: JPEG/PNG 파일

**Response 200:**
```json
{
  "items": [
    {
      "name": "Hummus pita",
      "price_cents": 450,
      "description": "with tahini sauce",
      "confidence": 0.95
    },
    {
      "name": "Falafel wrap",
      "price_cents": 699,
      "description": null,
      "confidence": 0.88
    }
  ],
  "warnings": []
}
```

**Rate limit:** 디바이스당 분당 5회 (Gemini 비용 방어).

---

### POST `/recommend`

자연어 쿼리로 메뉴 추천 (Gemini).

**Request:**
```json
{
  "lat": 42.9634,
  "lng": -85.6681,
  "query": "비 오는 날 따뜻한 거 $10 이하",
  "max_results": 5
}
```

**Response 200:**
```json
{
  "recommendations": [
    {
      "restaurant_id": "uuid",
      "restaurant_name": "Pita House",
      "menu_item_id": "uuid",
      "menu_name": "Lentil soup",
      "price_cents": 450,
      "distance_m": 500,
      "verification_status": "human_verified",
      "reason": "따뜻한 렌틸 수프, $4.50"
    }
  ]
}
```

**Behavior:**
1. 주변 반경 2km 내 메뉴 50개 정도 후보 추출 (verified 우선)
2. 리스트 + 사용자 쿼리를 Gemini에게 전달
3. Gemini가 상황에 맞는 5개 추천 + reason
4. menu_item_id 화이트리스트 검증

---

### POST `/reports`

잘못된 가격이나 부적절한 메뉴 신고. 어뷰징 방지 + 데이터 품질 방어.

**Headers:** `X-Device-Id: <uuid>`

**Request:**
```json
{
  "menu_item_id": "uuid",
  "reason": "wrong_price",
  "comment": "I went there yesterday, it's actually $12 not $6"
}
```

**`reason` 값:**
- `wrong_price` — 가격이 틀림
- `not_on_menu` — 메뉴에 없음
- `spam` — 스팸성 제보
- `inappropriate` — 부적절한 내용
- `other` — 기타

**Response 201:**
```json
{
  "id": "uuid",
  "status": "pending",
  "menu_item_auto_disputed": false
}
```

**Behavior:**
- 같은 사용자가 같은 메뉴 여러 번 신고 불가 (409)
- 해당 메뉴의 pending report가 3개 이상이면 자동으로 `verification_status='disputed'`로 전환 (DB 트리거)
- `menu_item_auto_disputed: true`로 응답에 반영
- Legend 유저 (Level 10+) 또는 관리자가 review해서 결정

---

### POST `/ratings`

식당에 별점 부여 (Level 3+ 만 가능).

**Headers:** `X-Device-Id: <uuid>`

**Request:**
```json
{
  "restaurant_id": "uuid",
  "score": 4,
  "comment": "Great value for the price"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "restaurant_updated": {
    "id": "uuid",
    "app_rating": 4.35,
    "rating_count": 24
  },
  "points_awarded": 2
}
```

**Behavior:**
- 사용자 level < 3이면 403 Forbidden
- 동일 사용자가 이미 rating 했으면 409 Conflict (PUT으로 업데이트는 가능)
- app_rating 재계산: `SUM(score * weight_applied) / SUM(weight_applied)`

---

### GET `/me`

현재 디바이스의 프로필 조회.

**Headers:** `X-Device-Id: <uuid>`

**Response 200:**
```json
{
  "device_id": "uuid",
  "display_name": null,
  "points": 235,
  "level": 3,
  "level_name": "Regular",
  "level_weight": 1,
  "next_level_points": 400,
  "submission_count": 12,
  "confirmation_count": 18,
  "daily_streak": 3,
  "can_rate_restaurants": true,
  "first_seen": "2026-04-15T10:00:00Z"
}
```

**Behavior:**
- 첫 방문이면 자동으로 devices 테이블에 row 생성
- 오늘 첫 방문이면 daily bonus (+1점) 자동 지급

---

### GET `/health`

헬스체크.

**Response 200:**
```json
{
  "status": "ok",
  "timestamp": "2026-04-18T15:23:00Z",
  "db": "connected",
  "gemini": "available"
}
```

---

## Error Format

```json
{
  "error": {
    "code": "INVALID_COORDINATES",
    "message": "Latitude must be between -90 and 90",
    "details": {}
  }
}
```

## Error Codes

| Code | HTTP Status | 의미 |
|------|-------------|------|
| `INVALID_COORDINATES` | 400 | lat/lng 범위 초과 |
| `RESTAURANT_NOT_FOUND` | 404 | 식당 없음 |
| `MENU_ITEM_NOT_FOUND` | 404 | 메뉴 없음 |
| `DEVICE_ID_REQUIRED` | 401 | 제보/확인 엔드포인트에서 헤더 누락 |
| `ALREADY_CONFIRMED` | 409 | 이미 confirm 한 메뉴 |
| `ALREADY_RATED` | 409 | 이미 rating 한 식당 |
| `INSUFFICIENT_LEVEL` | 403 | Level 3 미만이 Rating 시도 |
| `RATE_LIMITED` | 429 | Gemini API 레이트 리밋 |
| `GEMINI_PARSE_FAILED` | 200 | `items: []` with warnings |

## Status Codes

- 200 OK
- 201 Created
- 400 Bad Request
- 401 Unauthorized (X-Device-Id 없음)
- 403 Forbidden (권한 부족)
- 404 Not Found
- 409 Conflict
- 429 Too Many Requests
- 500 Internal Server Error
