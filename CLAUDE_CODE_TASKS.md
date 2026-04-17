# Claude Code Task List

각 태스크는 독립적으로 실행 가능. Claude Code에 순서대로 던지면 됨.

---

## Phase 0: Setup (수동, ~30분)

네가 직접 해야 하는 사전 준비:

- [ ] Google Cloud 프로젝트 생성
- [ ] Places API (New) 활성화
- [ ] Maps SDK for Android 활성화
- [ ] API 키 발급 (제한: 내 IP + Android 패키지)
- [ ] Google AI Studio에서 Gemini API 키 발급 (https://ai.google.dev)
- [ ] Google AI Pro 학생 무료 1년 신청 (Calvin 이메일)
- [ ] DigitalOcean 계정 ($200 학생 크레딧)
- [ ] DigitalOcean Managed PostgreSQL 생성 (Basic)
- [ ] DigitalOcean Spaces 생성 (이미지 스토리지)
- [ ] PostGIS extension 활성화
- [ ] GitHub 리포지토리 생성: `broken-lunch-gr`
- [ ] 로컬에 Python 3.11 + Android Studio 설치 확인

---

## Phase 1: Backend

### Task 1.1: 프로젝트 스캐폴딩

```
다음 구조로 FastAPI 프로젝트를 생성해줘:

backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py         # pydantic-settings
│   ├── db.py             # SQLAlchemy async engine
│   ├── models/
│   ├── schemas/
│   ├── routers/
│   └── services/
├── migrations/
├── scripts/
├── .env.example
├── requirements.txt
└── Dockerfile

의존성:
- fastapi
- uvicorn[standard]
- sqlalchemy[asyncio]
- asyncpg
- alembic
- pydantic-settings
- google-genai
- httpx
- python-multipart
- geoalchemy2
- beautifulsoup4
- pdfplumber
- pdf2image
- reppy
- boto3  # DO Spaces용
- tenacity  # rate limit exponential backoff

README에 로컬 실행 방법 명시.
```

### Task 1.2: 데이터베이스 스키마 & 마이그레이션

```
docs/SCHEMA.sql을 참고해서 Alembic 마이그레이션 + SQLAlchemy ORM 모델을 작성해.

테이블:
- restaurants
- menu_items (verification_status, confirmation_weight 포함)
- devices (points, level, level_weight)
- submissions
- confirmations
- ratings
- point_history
- crawl_log

모든 트리거도 마이그레이션에 포함 (op.execute로 raw SQL):
- compute_tier (menu_items)
- auto_verify_menu (menu_items)
- compute_level (devices)

GeoAlchemy2의 Geography(geometry_type='POINT', srid=4326) 사용.
```

### Task 1.3: Places API 공격적 수집 스크립트

```
scripts/01_seed_places.py를 작성해.

목적: Grand Rapids 반경 15mi 내 식당을 최대한 많이 수집. 목표 1500~2500개.

1. Places API (New) 엔드포인트 2종 사용:
   a. Text Search: https://places.googleapis.com/v1/places:searchText
   b. Nearby Search: https://places.googleapis.com/v1/places:searchNearby
   
   공통 헤더:
   - X-Goog-Api-Key
   - X-Goog-FieldMask: places.id,places.displayName,places.formattedAddress,
     places.location,places.nationalPhoneNumber,places.websiteUri,
     places.rating,places.priceLevel,places.regularOpeningHours,places.types

2. 수집 전략 (공격적):
   
   a. Text Search 카테고리 × 지역 매트릭스 (~45 쿼리):
      카테고리 (15개): pizza, mexican, asian, burger, sandwich, coffee, 
        sushi, breakfast, deli, bakery, mediterranean, thai, chinese,
        indian, chicken
      지역 (3개): "Grand Rapids MI", "Kentwood MI", "Wyoming MI"
      → "{category} in {region}" 형태로 쿼리
      → 각 쿼리에 대해 nextPageToken으로 최대 60개까지
   
   b. Nearby Search 격자 기반 (~20 포인트):
      GR 중심 (42.9634, -85.6681) 기준 ±0.05도 간격 그리드
      각 포인트에서 반경 2000m로 type='restaurant' 검색
      페이지네이션 3페이지까지
   
   c. OpenStreetMap Overpass API 보완 (공짜):
      [out:json];
      node["amenity"="restaurant"](42.85,-85.80,43.05,-85.50);
      out body;
      → Google 데이터와 이름/좌표 fuzzy match로 중복 제거
      → 새로운 식당만 DB 추가 (source='osm')

3. 중복 제거:
   - google_place_id로 1차 dedup
   - OSM 데이터는 이름(lowercase) + 좌표(±50m) 매칭으로 Google과 대조
   
4. DB 저장:
   - location = ST_GeogFromText(f'POINT({lng} {lat})')
   - category = types에서 'restaurant', 'food', 'point_of_interest' 제외한 첫 번째
   - hours_json = regularOpeningHours 그대로
   - website 필드 있는 식당 따로 카운트 (다음 단계 크롤링 후보)

5. 예상 API 호출 비용:
   - Text Search: 45 쿼리 × 평균 2페이지 = 90 호출
   - Nearby Search: 20 포인트 × 평균 2페이지 = 40 호출
   - 총 ~130 호출 × $32/1000 = $4.16
   - $200 무료 크레딧 안에서 해결

6. **Rate limit 방어 (tenacity 사용):**
   ```python
   from tenacity import retry, stop_after_attempt, wait_exponential
   
   @retry(
       stop=stop_after_attempt(5),
       wait=wait_exponential(multiplier=1, min=2, max=30),
       retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ReadTimeout)),
   )
   async def call_places_api(...):
       ...
   ```
   - 429 Too Many Requests → 2초, 4초, 8초, 16초, 30초 간격으로 재시도
   - 동시성은 5가 아니라 **3으로 낮춤** (해커톤 API 한도 보수적)

7. **재시작 가능 (resume logic):**
   - 시작 시: `SELECT google_place_id FROM restaurants` 로 이미 있는 것 조회
   - 각 쿼리 결과에서 중복 place_id는 skip
   - 스크립트 중간에 죽어도 `python 01_seed_places.py` 재실행하면 이어서 진행
   - --fresh 플래그로 처음부터 다시 돌릴 수 있게

8. 실행 결과 리포트:
   - 수집된 식당 총 수 (목표: 1500+)
   - Google Places 수집 수
   - OSM 추가 수
   - website 필드 있는 식당 수 (크롤링 후보)
   - 카테고리 분포 top 10
   - 좌표 분포 확인 (지도에 플롯된 CSV 출력)

.env: GOOGLE_PLACES_API_KEY
dry-run 모드: --dry-run 플래그
재시작 가능: 이미 DB에 있는 place_id는 skip
병렬 처리: asyncio.gather, 동시성 3 (429 방어)
```

### Task 1.4: 웹 크롤러 + Gemini 파싱 파이프라인

```
핵심 태스크. scripts/02_crawl_and_parse.py 작성.

목적: DB에 저장된 식당의 website를 크롤링 → 메뉴 페이지 찾기 → Gemini로 파싱.

단계:
1. DB에서 website 있는 식당 조회

2. 각 식당에 대해:
   a. robots.txt 체크 (reppy 라이브러리)
   b. 홈페이지 방문해서 /menu, /menus, /food, /our-menu 등 경로 탐색
   c. 메뉴 페이지 URL 발견:
      - HTML이면 텍스트 추출 (BeautifulSoup)
      - PDF 링크면 다운로드 (httpx)
   d. 없으면 홈페이지 자체를 Gemini에게 보내서 "메뉴가 있나?" 확인
   e. crawl_log 테이블에 결과 기록

3. 메뉴 데이터 확보되면 Gemini 파싱 (docs/GEMINI_PROMPTS.md Use Case 1):
   - HTML → Gemini Text
   - PDF → pdf2image로 이미지 변환 → Gemini Vision
   
4. 파싱 결과를 menu_items에 저장:
   - source = 'gemini_web'
   - verification_status = 'ai_parsed'
   - 가격 $15 초과는 skip

5. 매너 지키기:
   - User-Agent: "BrokenLunchHackathonBot/1.0 (academic project)"
   - 식당당 2~3초 대기
   - 동시성 3 (asyncio.Semaphore) — 429 방어
   - 타임아웃 10초

6. **Rate limit 방어 (tenacity):**
   - Gemini API 호출에 exponential backoff 적용
   - 429, 500, 503 에러 재시도 (2초 → 4초 → 8초 → 16초 → 30초)
   - 최대 5회 재시도 후 실패하면 crawl_log에 'parse_failed' 기록

7. **재시작 가능 (resume logic):**
   - 시작 시: `SELECT restaurant_id FROM crawl_log WHERE status IN ('success', 'no_menu_found', 'robots_blocked')` 
   - 이 ID들은 skip
   - 스크립트 중간에 죽으면 재실행으로 이어서 진행
   - 각 식당 처리 완료 즉시 crawl_log에 기록 (나중에 몰아서 저장하지 않기)
   - --retry-failed 플래그: 실패한 것만 다시 시도
   - --fresh 플래그: 처음부터 다시

8. 개별 식당 처리 단위 트랜잭션:
   - 한 식당 처리 = (크롤링 + Gemini 파싱 + DB 저장 + crawl_log 기록)
   - 이 전체가 하나의 DB transaction
   - 실패 시 rollback → 다음 재시도 때 해당 식당만 재처리

진행상황 print + 최종 통계:
- 시도한 식당 수
- 크롤링 성공 수
- 메뉴 추출 성공 수  
- 총 메뉴 아이템 수
- Gemini API 호출 비용 추정

.env: GEMINI_API_KEY
실행 시간: 400개 식당 대상 약 30분~1시간 예상.
```

### Task 1.5: Restaurants API (+ PostGIS Plan B)

```
app/services/distance.py (신규, Plan B):

PostGIS 세팅 실패 시 fallback용 순수 Python Haversine 구현.

import math

def haversine_distance_m(lat1, lng1, lat2, lng2) -> float:
    '''두 좌표 간 거리 (미터). 지구 반지름 6371km 사용.'''
    R = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (math.sin(dphi / 2) ** 2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))

def bounding_box(lat, lng, radius_m) -> tuple:
    '''radius 안의 식당만 미리 필터링 (lat/lng 인덱스 활용).
    Haversine 정확하지만 모든 식당 계산하면 느림.
    bounding box로 pre-filter한 뒤 Haversine으로 정확한 거리 계산.'''
    lat_delta = radius_m / 111_320  # 1도 ≈ 111.32km
    lng_delta = radius_m / (111_320 * math.cos(math.radians(lat)))
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)


app/routers/restaurants.py:

config.POSTGIS_ENABLED 플래그 도입. settings에서 읽음.
앱 시작 시 SELECT 1 FROM pg_extension WHERE extname='postgis' 으로 자동 감지.

GET /restaurants/nearby
  - query params: lat, lng, radius_m (default 2000), tier (optional), 
    verified_only (default false), include_empty (default true), limit (default 100)
  
  분기:
  if settings.POSTGIS_ENABLED:
    # Plan A: PostGIS ST_DWithin + ST_Distance
    WHERE ST_DWithin(location, ST_GeogFromText(f'POINT({lng} {lat})'), radius_m)
    ORDER BY menu_status ASC, ST_Distance(location, user_point) ASC
  else:
    # Plan B: Haversine fallback
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius_m)
    WHERE lat BETWEEN :lat_min AND :lat_max
      AND lng BETWEEN :lng_min AND :lng_max
    # 쿼리 결과를 Python에서 haversine_distance_m 계산 후 radius_m 미만만 필터
    # 정렬도 Python에서
  
  restaurants_map_view 뷰 사용 (LEFT JOIN, 메뉴 없는 식당 포함)
  include_empty=false면 WHERE menu_status != 'empty' 추가
  tier 필터 있으면 cheapest_tier 매칭
  verified_only=true이면 cheapest_verification_status='human_verified'만
  응답에 menu_status 필드 포함, cheapest_menu는 empty면 null

GET /restaurants/{restaurant_id}
  - 메뉴를 tier별 그룹으로 반환 (빈 식당도 detail 조회 가능)
  - 각 tier 내 price_cents ASC
  - is_active=TRUE 필터
  - 빈 식당이면 menu 객체 전체가 빈 tier들
  - verification_status + confirmation_count 포함
  - 404 처리

Pydantic 스키마는 app/schemas/restaurant.py에.

2500개 식당이어도 Python Haversine으로 100ms 안에 쿼리 가능.
해커톤 규모에서 성능 차이 미미. 안전하게 가자.
```

### Task 1.6: Submissions API

```
app/routers/submissions.py:

POST /submissions
  헤더: X-Device-Id (required)
  
  로직:
  1. devices upsert (없으면 생성, last_seen 갱신)
  2. 유사 메뉴 검색:
     - 같은 restaurant_id
     - menu_name 유사도 (SQL LOWER/TRIM 후 비교 or 간단한 fuzzy)
  3. 분기:
     a. 유사 메뉴 있고 가격 차 < $1: 기존 menu_item의 confirmation_weight += level_weight
     b. 유사 메뉴 있고 가격 차 $1~$3: 기존 + 새로운 모두 verification_status='disputed'
     c. 유사 메뉴 없음: 새 menu_item 생성 (source='gemini_photo' or 'user_manual', status='ai_parsed')
  4. **첫 제보 보너스 판정**:
     - 해당 restaurant_id에 is_active=TRUE menu_item이 지금 이 제보 이전에 0개였으면 is_first_submission=TRUE
     - 포인트: +10 (기본) + 5 (첫 제보면) = +15
  5. submissions 테이블 기록 (is_first_submission 포함)
  6. 포인트 지급 (point_history 기록)
  7. 레벨업 체크 후 응답에 반영
  8. 응답에 bonus_message 포함 (is_first_submission이면
     "🎉 First to register this restaurant! +5 bonus")

이 로직은 transaction으로 묶어.
```
```

### Task 1.7: Confirmations API

```
app/routers/confirmations.py:

POST /confirmations
  헤더: X-Device-Id (required)
  body: menu_item_id, is_agreement, reported_price (optional)
  
  로직:
  1. 동일 device_id + menu_item_id 이미 존재 → 409
  2. confirmations 테이블에 기록 (weight_applied = current level_weight)
  3. is_agreement=true:
     - menu_items.confirmation_weight += level_weight
     - menu_items.confirmation_count += 1
     - 트리거가 status 자동 전환 (weight >= 5 → human_verified)
  4. is_agreement=false:
     - menu_items.verification_status = 'disputed'
     - reported_price 있으면 새 menu_item 생성
  5. 포인트 +3 지급
```

### Task 1.8: Gemini Service (+ Pydantic 응답 검증)

```
app/schemas/gemini_responses.py (신규):

Gemini 응답을 엄격하게 검증할 Pydantic 모델. response_mime_type='application/json'
만 써도 JSON은 나오지만 키 이름/타입이 미묘하게 달라질 수 있음. 이걸로 2차 방어.

from pydantic import BaseModel, Field, field_validator

class ParsedMenuItem(BaseModel):
    name: str
    description: str | None = None
    price_cents: int = Field(ge=1, le=1500)  # $0.01 ~ $15
    category: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    
    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError('empty name')
        return v.strip()

class ParsedMenuResponse(BaseModel):
    items: list[ParsedMenuItem]
    restaurant_name_detected: str | None = None
    warnings: list[str] = []

class Recommendation(BaseModel):
    menu_item_id: str  # UUID string
    reason: str = Field(max_length=120)

class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]


app/services/gemini.py:

from app.schemas.gemini_responses import ParsedMenuResponse, RecommendResponse
from pydantic import ValidationError
import json
import logging

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
    
    async def _call_and_validate(
        self, 
        model_name: str,
        contents: list,
        response_schema: type[BaseModel],
        system_instruction: str | None = None,
    ) -> BaseModel:
        '''Gemini 호출 + Pydantic 검증 + 실패 시 safe default.'''
        config = types.GenerateContentConfig(
            response_mime_type='application/json',
        )
        if system_instruction:
            config.system_instruction = system_instruction
        
        try:
            response = self.client.models.generate_content(
                model=model_name,
                config=config,
                contents=contents,
            )
            raw_json = json.loads(response.text)
            return response_schema.model_validate(raw_json)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f'Gemini response validation failed: {e}')
            # safe default
            if response_schema is ParsedMenuResponse:
                return ParsedMenuResponse(items=[], warnings=['parse_error'])
            if response_schema is RecommendResponse:
                return RecommendResponse(recommendations=[])
            raise
    
    async def parse_web_menu(self, html_text: str) -> ParsedMenuResponse:
        # docs/GEMINI_PROMPTS.md Use Case 1-A
        return await self._call_and_validate(...)
    
    async def parse_pdf_menu(self, pdf_bytes: bytes) -> ParsedMenuResponse:
        # pdf2image로 변환 후 각 페이지 Vision 호출
        # 모든 페이지 결과 합쳐서 단일 ParsedMenuResponse 반환
    
    async def parse_photo(self, image_bytes: bytes, mime_type: str) -> ParsedMenuResponse:
        # docs/GEMINI_PROMPTS.md Use Case 2
    
    async def recommend(self, query: str, menus: list[dict]) -> RecommendResponse:
        # docs/GEMINI_PROMPTS.md Use Case 3
        result = await self._call_and_validate(...)
        # 화이트리스트 검증: menus에 있는 id만 통과
        valid_ids = {m['id'] for m in menus}
        result.recommendations = [
            r for r in result.recommendations if r.menu_item_id in valid_ids
        ]
        return result

이 구조의 장점:
- Gemini가 이상한 JSON 반환해도 앱이 안 죽음
- 가격 범위($0-$15) DB 저장 전에 검증
- 타입 안정성 (int vs float 헷갈림 방지)
```

### Task 1.9: Gemini Routers

```
app/routers/gemini.py:

POST /parse-menu-image
  multipart/form-data: image
  헤더: X-Device-Id (rate limit용)
  
  로직:
  1. 디바이스별 분당 5회 rate limit (인메모리 Counter)
  2. image.read() → GeminiService.parse_photo()
  3. 결과 반환 (DB 저장 안 함, 이건 사용자가 확인 후 /submissions 호출)

POST /recommend
  body: lat, lng, query, max_results
  
  로직:
  1. 주변 50개 메뉴 조회 (verified 우선, distance ASC)
  2. GeminiService.recommend() 호출
  3. 응답 enrichment (DB 정보로 채움)
  4. 반환
```

### Task 1.10: Ratings, Reports & Me APIs

```
app/routers/ratings.py:

POST /ratings
  - Level < 3이면 403
  - 이미 rating 있으면 409
  - restaurants.app_rating 재계산 (가중평균)
  - 포인트 +2

app/routers/reports.py:

POST /reports
  헤더: X-Device-Id (required)
  body: menu_item_id, reason, comment (optional)
  
  로직:
  1. devices 테이블에 device 있는지 확인 (없으면 auto create)
  2. 동일 device_id + menu_item_id 이미 존재 → 409
  3. reports 테이블에 INSERT
  4. 해당 메뉴의 pending reports 카운트 조회
  5. 3건 이상이면 menu_items.verification_status = 'disputed' (트리거가 처리)
  6. 응답에 menu_item_auto_disputed 포함

레이트 리밋: 디바이스당 하루 10건 (스팸 신고 방지)

app/routers/me.py:

GET /me
  - devices 테이블에서 현재 디바이스 조회 (없으면 auto create)
  - 오늘 첫 방문이면 daily bonus +1 (last_daily_bonus 업데이트)
  - level_name 매핑: 1=Newbie, 2=Scout, 3=Regular, 4=Explorer, 5=Expert, 7=Veteran, 10=Legend
  - next_level_points 계산
```

### Task 1.11: DigitalOcean 배포

```
Dockerfile + docker-compose.yml 작성.

DigitalOcean App Platform용 .do/app.yaml:
- FastAPI 서비스 1개
- Managed DB 연결 string 주입
- 환경변수 리스트

환경변수:
- DATABASE_URL
- GEMINI_API_KEY
- GOOGLE_PLACES_API_KEY
- DO_SPACES_KEY, DO_SPACES_SECRET, DO_SPACES_BUCKET, DO_SPACES_REGION
- CORS_ORIGINS

README에 배포 가이드:
1. `doctl apps create --spec .do/app.yaml`
2. 환경변수 설정
3. 데이터 수집 스크립트 실행 (일회성)
```

---

## Phase 2: Android

### Task 2.1: 프로젝트 초기화

```
Android Studio 새 프로젝트:
- Package: com.brokenlunch.gr
- minSdk 26, targetSdk 34
- Jetpack Compose
- Kotlin 1.9+

build.gradle.kts 의존성 (version catalog):
- androidx.compose.bom
- androidx.compose.material3
- androidx.navigation:navigation-compose
- com.google.maps.android:maps-compose
- com.google.android.gms:play-services-maps + location
- androidx.camera:camera-camera2, camera-lifecycle, camera-view
- com.squareup.retrofit2:retrofit + converter-moshi
- com.squareup.okhttp3:logging-interceptor
- com.google.dagger:hilt-android + hilt-compiler
- io.coil-kt:coil-compose

local.properties:
MAPS_API_KEY=xxxxx
BACKEND_URL=https://broken-lunch-gr.ondigitalocean.app

AndroidManifest.xml에 권한:
- ACCESS_FINE_LOCATION
- CAMERA
- INTERNET
```

### Task 2.2: Device ID 관리 + API 클라이언트

```
data/DeviceIdManager.kt:
- SharedPreferences에서 device_id 읽기
- 없으면 UUID.randomUUID() 생성 후 저장
- 이 값이 앱 설치 후 변하지 않음 (앱 재설치하면 새 ID)

data/api/BrokenLunchApi.kt: Retrofit 인터페이스
- 모든 엔드포인트 (docs/API.md 참고)
- @Header("X-Device-Id") 자동 주입 (Interceptor)

data/model/: @JsonClass(generateAdapter = true) DTO:
- Restaurant, MenuItem, NearbyResponse, RestaurantDetail,
  SubmissionResponse, ConfirmationResponse, ParsedMenuResponse,
  RecommendResponse, MeResponse, VerificationStatus (enum),
  Tier (enum)

di/NetworkModule.kt: Hilt로 Retrofit + OkHttpClient 제공
- DeviceIdInterceptor (헤더 자동 추가)
- HttpLoggingInterceptor (디버그용)
```

### Task 2.3: 지도 화면 (거지맵 스타일 + 빈 핀)

**가장 중요한 화면. 시간 많이 걸림.**

```
ui/map/MapScreen.kt:

구조:
┌─ Scaffold
├── TopBar (검색 아이콘 + "Show empty" 토글)
├── 필터 Row (tier chips: Survive/Cost-effective/Luxury)
├── GoogleMap (fillMaxSize)
│   └── 커스텀 Marker (3가지 상태)
└── BottomBar (네비게이션)

커스텀 Marker (menu_status별 3종):

1. populated_verified (실선 + 가격):
   - 형태: Pill with Row
   - 왼쪽: Circle with category 아이콘 (22dp, white bg)
   - 오른쪽: "$4.50" 텍스트
   - 색상 (tier 기반):
     - survive: bg #EAF3DE, border #639922, text #27500A
     - cost_effective: bg #FAEEDA, border #BA7517, text #633806
     - luxury: bg #FCEBEB, border #A32D2D, text #791F1F
   - Border: solid 1.5dp

2. populated_ai (점선 + 가격):
   - 위와 동일하되 border: dashed 1.5dp
   - Canvas로 직접 그리기 (Compose의 Border는 dashed 지원 안 함)
   - 또는 drawBehind {} 로 path effect 사용

3. empty (회색 + "?" + bonus 표시):
   - bg: #F1EFE8 (gray 50)
   - border: solid 1.5dp #B4B2A9
   - 왼쪽: Circle with "?" 텍스트 (#888780)
   - 오른쪽: "+15 pts" 텍스트 (11sp, #5F5E5A)

"Show empty restaurants" 토글 (TopBar):
- ON (기본): 빈 식당도 표시
- OFF: include_empty=false로 API 호출

하단 오른쪽 FAB: "내 위치로 이동" (Material FAB Small)
상단 왼쪽: "이 지역 더 보기" 버튼 (지도 중심 기준 재검색)

빈 핀 클릭 시 특수 처리:
- BottomSheet 대신 식당 상세로 바로 이동
- 상세 화면에서 "메뉴가 없어요" + "첫 제보 (+15 pts)" CTA

ViewModel: MapViewModel (Hilt + StateFlow)
- FusedLocationProviderClient로 현재 위치
- state: filter (tier), showEmpty (bool), markers (list)
- loadNearby() 호출 시 include_empty 파라미터 반영
- 핀 클릭 → navigation to detail

권한:
- 앱 시작 시 ACCESS_FINE_LOCATION 요청
- 거부 시 fallback: GR 중심 좌표 (42.9634, -85.6681), zoom 12

성능:
- 1500+ 마커 렌더링 부담 → Marker Clustering 사용
  (com.google.maps.android:android-maps-utils)
- 줌 레벨 낮으면 클러스터로, 높으면 개별 핀
```

### Task 2.4: 리스트 화면

```
ui/list/ListScreen.kt:

LazyColumn with sticky headers:

Section: Survive ($0-$5)
  - Header: border-left 3dp #639922, "Survive" + "eat to live · N spots"
  - Items: MenuItemCard
    - Leading: 원형 카테고리 아이콘
    - Title: 식당명
    - Subtitle: 메뉴명 · 거리
    - Trailing: 가격 + 작은 verification 배지

Section: Cost-effective ($5-$10)
  - 같은 구조, amber 색상

Section: Luxury ($10-$15)
  - 같은 구조, red 색상

Section: Help us! (menu_status='empty' 식당들)
  - Header: border-left 3dp gray, "Help us!" + "메뉴가 없는 근처 식당 · N spots"
  - Items: EmptyRestaurantCard
    - Leading: 회색 원형 "?" 아이콘
    - Title: 식당명
    - Subtitle: 카테고리 · 거리
    - Trailing: "+15 pts" 배지 (보라 배경)
    - 클릭 → 상세 화면 (CTA)

상단 필터: 거리순/가격순 토글 + "Include empty" 토글

ViewModel: ListViewModel
- /restaurants/nearby 호출 (verified_only 토글 + include_empty 토글)
- populated 식당: 메뉴 단위로 flatten해서 tier별 그룹화
- empty 식당: 거리순으로 별도 섹션
```

### Task 2.5: 식당 상세 화면 (빈 식당 처리 포함)

```
ui/detail/RestaurantDetailScreen.kt:

Header:
- 식당 이름 (h2)
- 카테고리 · 거리 · Google rating · App rating (있으면)
- 주소, 전화번호, 웹사이트 (클릭하면 외부 링크)

**빈 식당 (menu_status='empty') 특수 처리:**
- 메뉴 섹션 대신 큰 CTA 카드:
  ┌─────────────────────────────────────┐
  │ 📋 아직 메뉴가 등록되지 않았어요      │
  │                                      │
  │ 첫 제보자가 되어 +15 포인트 받기    │
  │                                      │
  │ [📷 Take menu photo]                │
  └─────────────────────────────────────┘
- 버튼 클릭 → /submit 화면으로 이동 (restaurant_id 전달)

**메뉴 있는 식당 (populated_*):**
메뉴 섹션 (tier별):
- tier 비어있으면 해당 섹션 숨김
- 각 메뉴 MenuCard:
  ┌─ Row
  │ ├ Left: 메뉴명 (h3) + 설명 (body small)
  │ └ Right: 가격 + 🏴 신고 아이콘 (작게, 오른쪽 끝)
  └ Row (bottom):
    ├ Verification badge (AI parsed / Human verified / Disputed / needs verification)
    └ Meta text ("3 users · last checked today" 또는 "needs verification")
  
  배지 스타일:
    human_verified: bg #E1F5EE, text #04342C, 체크 아이콘
    ai_parsed: bg #EEEDFE, text #26215C, 별 아이콘
    disputed: bg #FAEEDA, text #412402, 경고 아이콘
    needs_verification: 노란 텍스트만, 배지 없음

신고 아이콘 (🏴 flag, 16dp, 회색) 클릭 시:
  → BottomSheet 띄우기: "Report this price"
  → reason radio group:
    ○ Wrong price
    ○ Not on menu
    ○ Spam
    ○ Inappropriate
    ○ Other
  → comment 필드 (optional)
  → [Submit report] 버튼
  → POST /reports
  → 성공 시 "Thanks for reporting. We'll review." 토스트
  → 해당 메뉴가 3건 이상 신고되면 자동 disputed 전환

각 메뉴 하단에 두 버튼:
  [✓ Confirm price] [✗ Different price]
  
  Confirm 클릭:
    → POST /confirmations (is_agreement=true)
    → 성공 시 로컬 state 업데이트 + "+3 points" 토스트
  
  Different 클릭:
    → 다이얼로그: 새 가격 입력
    → POST /confirmations (is_agreement=false, reported_price=X)

하단 (Level 3+ 만):
  [★ Rate this restaurant] 버튼
  → Rating dialog (1-5 별점 + 코멘트)
  → POST /ratings

**메뉴 있어도 하단에 "Add more menu items" 버튼** — 누락된 메뉴 추가 유도
```

### Task 2.6: 제보 화면 (카메라 + Gemini)

**Gemini 데모의 핵심 기능.**

```
ui/submit/SubmitScreen.kt:

플로우:
1. 식당 선택
   - 현재 위치 기준 nearby 리스트에서 검색/선택
   - 선택되면 상단에 식당 카드 고정

2. "Take menu photo" 버튼
   - 클릭 → CameraX 화면으로 전환
   - Preview + 캡처 버튼
   - 캡처 시 local file 저장

3. Gemini 파싱 (자동)
   - ProgressIndicator with "Parsing menu with AI..."
   - multipart/form-data로 POST /parse-menu-image
   - 응답 받으면 결과 화면으로

4. 파싱 결과 화면
   - LazyColumn with 편집 가능한 아이템들
   - 각 아이템: name (TextField), price (TextField), [X] 삭제 버튼
   - "Add manual item" 버튼 (Gemini가 놓친 거 추가)
   - 하단 "Submit all (N items)" 버튼

5. Submit
   - 각 아이템마다 POST /submissions 호출
   - 총 N개 × 10점 = N*10 포인트 지급 토스트
   - 지도 화면으로 복귀

로딩/에러 상태:
- Gemini 느림 → "Still parsing..." 3초 후
- 파싱 결과 빈 items → "메뉴를 읽지 못했어요. 수동 입력해주세요"
- 네트워크 에러 → 재시도 버튼

ViewModel: SubmitViewModel
- 상태 enum: IDLE, SELECTING_RESTAURANT, CAMERA_OPEN, PARSING, EDITING, SUBMITTING, DONE
```

### Task 2.7: 자연어 추천 화면 (시간 남으면)

```
ui/recommend/RecommendScreen.kt:

구조:
- 상단: 큰 SearchBar
  Placeholder: "어떤 음식이 땡기세요? (예: 비 오는 날 따뜻한 거)"
- [Find my meal ↗] 버튼

2. 결과 카드 리스트 (최대 5개):
  각 카드: 메뉴명, 식당, 가격, 거리, Gemini의 추천 이유 (italic)
  
3. 결과 없으면: "Try different words or expand your search"

ViewModel: RecommendViewModel
- POST /recommend 호출
- 로딩/에러 상태 처리
```

### Task 2.8: 프로필 화면 (시간 남으면)

```
ui/profile/ProfileScreen.kt:

구조:
- 상단: 레벨 배지 (Newbie / Scout / Regular...)
- 포인트: "235 / 400 pts" + ProgressBar
- 다음 레벨까지: "165 pts to Explorer"
- 통계 카드:
  - 제보한 메뉴: 12개
  - 확인한 가격: 18회
  - 연속 접속: 3일
- 권한 체크리스트:
  ✓ 기본 제보
  ✓ Rating (Level 3+)
  ○ Expert 가중치 (Level 5+)
  ○ Legend 배지 (Level 10+)

GET /me 엔드포인트로 정보 조회.
```

### Task 2.9: 네비게이션

```
ui/navigation/BrokenLunchNavHost.kt:

NavHost:
- map (start)
- list
- restaurant/{id}
- submit (with optional restaurant_id arg)
- recommend
- profile

BottomNavigation:
- Map (icon: location)
- List (icon: list)
- Submit (icon: add, 가운데 FAB 스타일로 돋보이게)
- Recommend (icon: sparkle, Gemini 강조)
- Profile (icon: person)
```

---

## Phase 3: 통합 & 데모

### Task 3.1: 데이터 검수

```
해커톤 중 중간에 한 번 돌려서 데이터 품질 체크:

scripts/04_audit_data.py:
- 이상한 가격 ($0, $15+) 찾기
- 같은 이름인데 가격 매우 다른 메뉴 (disputed 후보) 찾기
- verification_status별 분포
- 카테고리별 분포
- restaurant 중 메뉴 0개인 곳

결과 print + CSV export.

수동 검수: 데모할 식당 5~10개는 직접 가격 확인해서 
verification_status='human_verified'로 세팅.
```

### Task 3.2: 데모 준비

```
docs/DEMO.md 작성:

1. 데모 스크립트 (3분)
   - 시간대별 멘트
   - 시연 순서
   - 백업 플랜

2. 테스트할 메뉴판 사진 3장 미리 준비
   (심사장에서 Gemini 실패 시 대비)

3. 테스트할 자연어 쿼리 5개 미리 테스트:
   - "비 오는 날 따뜻한 거 $10 이하"
   - "quick cheap lunch near Calvin"
   - "vegetarian under $8"
   - "late night food"
   - "something sweet"

4. 백엔드 연결 확인 체크리스트
```

### Task 3.3: 발표 슬라이드

```
Google Slides 6장:

1. 표지: Broken Lunch GR / One-liner / 너 이름
2. 문제: 기존 앱들 한계 (Yelp/Maps/UberEats 비교표)
3. 솔루션: 핵심 3 스크린샷 (Map / Detail / Submit)
4. Gemini 3-in-1:
   - Use Case 1: Web pipeline (400 식당)
   - Use Case 2: Photo parsing (실시간)
   - Use Case 3: NL recommendation
5. 기술 스택 + 아키텍처 다이어그램
6. What's next + GitHub + 데모 링크
```

### Task 3.4: Devpost 제출

```
Devpost 제출 형식:

- Project name: Broken Lunch GR
- Tagline: AI-powered cheap eats discovery for Grand Rapids
- Built with: Python, FastAPI, Kotlin, Jetpack Compose, Google Gemini API,
  Google Places API, PostgreSQL, PostGIS, DigitalOcean
- What inspired: 한국의 거지맵 + 미국 대학생 예산 현실
- What it does: 메뉴 단위 가격 지도, AI 데이터 파이프라인, 커뮤니티 검증
- How we built it: 3-phase 접근 (설계 → 데이터 수집 → 앱 구현)
- Challenges: 웹 크롤링 일관성, Gemini 프롬프트 튜닝
- Accomplishments: 48시간 만에 GR 전체 식당 커버
- What's next: 레벨 시스템, 식당 파트너십, 미시간 확장

Video (3분):
- OBS로 화면 녹화
- 데모 시나리오 그대로
- 자막 옵션 (한국어 섞일 수 있음)
```

---

## 작업 순서 & 시간 배분

| 시점 | 누적 시간 | 태스크 |
|------|---------|--------|
| 지금 | 0h | Phase 0 (키 발급) |
| +0.5h | 0.5h | Task 1.1, 1.2 (스캐폴딩 + DB) |
| +1h | 1.5h | Task 1.3 (Places API 수집) — 실행 중 다른 작업 |
| +2h | 3.5h | Task 1.4 (크롤러 + Gemini 파이프라인) — 실행 시작 |
| +1h | 4.5h | Task 1.5, 1.6, 1.7 (API 라우터) |
| +1h | 5.5h | Task 1.8, 1.9 (Gemini 서비스) |
| +0.5h | 6h | Task 1.10 (Ratings, Me) |
| +0.5h | 6.5h | Task 1.11 (DO 배포) |
| **수면/휴식 4~6시간** |  |  |
| 토요일 | 12h | Task 2.1, 2.2 (Android 기반) |
| +2h | 14h | Task 2.3 (지도 화면 — 제일 복잡) |
| +1h | 15h | Task 2.4, 2.5 (리스트, 상세) |
| +2h | 17h | Task 2.6 (제보) |
| +1h | 18h | Task 2.7 (추천) — 보너스 |
| +0.5h | 18.5h | Task 2.9 (네비게이션) |
| **수면** |  |  |
| 일요일 오전 | 22h | Task 3.1 (데이터 검수) |
| +2h | 24h | Task 3.2, 3.3 (데모, 슬라이드) |
| +1h | 25h | Task 3.4 (Devpost 제출 + 영상) |
| **오전 11시 마감** |  |  |

**여유: ~10시간 (디버깅 + 휴식 + 삽질)**

---

## 막힐 때 우선순위

시간 부족하면 이 순서로 cut:
1. Task 2.8 (프로필 화면) — 발표에 슬라이드만 있어도 됨
2. Task 2.7 (자연어 추천) — Gemini 2가지 use case로 축소
3. Task 1.10 (Ratings) — 레벨 3 이상만 하는 거니까 데모에서 빼도 됨
4. Task 2.4 (리스트) — 지도만 있어도 OK (bottom sheet로 리스트 가능)

**절대 포기 안 할 것:**
- Task 2.3 (지도) — 앱의 얼굴
- Task 2.6 (제보 + Gemini 파싱) — 상 노리는 핵심
- Task 1.4 (Gemini 파이프라인) — 데이터가 있어야 앱이 의미있음
