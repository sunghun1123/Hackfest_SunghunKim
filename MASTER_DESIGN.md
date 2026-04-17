# Broken Lunch GR — 전체 설계 문서

> 해커톤 프로젝트 · Grand Rapids, Michigan · 일요일 11시 마감

---

## 0. One-liner

"내 주변에 $5 이하로 먹을 수 있는 메뉴가 어디 있지?" — 3초 만에 답을 주는 Android 앱.

한국의 거지맵(Broken Map)에서 영감을 받은, **가격 투명성 + AI 데이터 파이프라인 + 커뮤니티 검증**을 결합한 극가성비 식당 지도.

---

## 1. 왜 이 프로젝트인가

### 문제
- Google Maps: 가격 필터가 `$ / $$ / $$$`뿐. 너무 대충
- Yelp: 메뉴별 가격 안 보여줌. 리뷰 중심
- UberEats/DoorDash: 배달 수수료 때문에 인스토어보다 15~30% 비쌈. "진짜 가격" 아님
- 대학생/자취생/저소득층은 정확한 메뉴 가격 정보가 없어서 매번 식당 홈페이지 뒤져야 함

### 해결
- 메뉴 **단위**로 가격 표시 (식당 단위 X)
- 3개 티어로 필터링: `Survive` / `Cost-effective` / `Luxury`
- 거지맵 스타일 — 지도 핀에 **가격이 그대로 박혀있음**
- AI가 데이터 자동 수집, 커뮤니티가 검증

### 타겟 사용자
- Calvin/GVSU/MSU 대학생
- GR 거주 저소득층/자취생
- 출장/여행자 중 예산 타이트한 사람

---

## 2. 해커톤 전략

### 노릴 상

**Best Use of Gemini API** (메인 타겟)
- Google Swag Kits
- 기준: "**프로젝트가** Gemini를 창의적으로 사용했는가"
- 네 앱은 Gemini를 3가지 방식으로 사용 (섹션 6 참고)

**Best Use of DigitalOcean** (보조 타겟)
- Retro Wireless Mouse
- 기준: DigitalOcean 인프라로 앱 배포
- 자연스럽게 충족 가능

### 제외한 상
- **Solana** — 앱 주제와 무관
- **ElevenLabs** — 음성 기능 억지로 넣으면 어색함
- **Snowflake** — 데이터 규모가 작아서 오버킬
- **Most Useless Hack** — 실용적 앱이라 해당 없음
- **Best Beginner Hack** — 해당 없음

---

## 3. 핵심 설계 원칙

### 3.1 디자인 원칙
- 거지맵 스타일 — 가격이 핀에 직접 박힌 알약 모양
- 3개 티어 시각적 구분 (green / amber / red)
- 사용 언어: 영어 (미시간이니까)
- Android 전용 (iOS/Web 제외)

### 3.2 가격 티어

| Tier | Range | 서브카피 | 색상 |
|------|-------|---------|------|
| `survive` | $0 — $5 | eat to live | Green (#639922) |
| `cost_effective` | $5 — $10 | best value | Amber (#BA7517) |
| `luxury` | $10 — $15 | treat day | Red (#A32D2D) |

`$15+`는 스코프 밖. 일반 식당 앱에서 찾으면 됨.

### 3.3 지역 범위
- **Grand Rapids 반경 15mi** (인접 교외 포함: Kentwood, Wyoming, Walker, East GR 등)
- 식당 수집 목표: **1500~2500개** (카테고리 × 지역 매트릭스 쿼리)
- 미시간 전체 확장은 해커톤 후

### 3.4 식당 & 메뉴 데이터 상태

**전략:** 식당 정보는 최대한 다 긁어서 지도에 표시. 메뉴/가격은 점진적으로 채워짐.

#### 식당 (pin) 3가지 상태

| 상태 | 의미 | UI |
|------|------|-----|
| `populated_verified` | 메뉴 있고 사용자 확인 완료 | 컬러 핀 + 실선 border + 가격 |
| `populated_ai` | 메뉴 있지만 AI 파싱만 됨 | 컬러 핀 + 점선 border + 가격 |
| `empty` | 식당만 등록됨, 메뉴 없음 | 회색 핀 + "?" 아이콘 + "+15 pts" |

빈 식당 핀 클릭 시: "아직 메뉴가 등록되지 않았어요 → 📷 첫 제보하기 (+15 pts)"

#### 메뉴 아이템 신뢰도 4단계

핵심 차별화 포인트. 가격 옆에 출처 배지 표시.

| 상태 | 의미 | UI |
|------|------|-----|
| `ai_parsed` | AI가 웹사이트/사진에서 파싱, 미검증 | 보라 별표 배지 `AI parsed` |
| `human_verified` | 사용자 confirmation weight ≥ 5 | 초록 체크 배지 `Human verified` |
| `disputed` | 서로 다른 가격 제보 | 노란 경고 배지 `Disputed` |
| `needs_verification` | AI parsed + 오래되거나 확인 안 됨 | 노란 텍스트 `needs verification` |

#### "Show empty restaurants" 필터
지도 상단 토글. 기본값 ON. 사용자가 지저분해 보이면 OFF 가능.

---

## 4. 데이터 전략 (가장 중요)

### 4.1 닭-달걀 문제 해결

**문제:** 데이터가 있어야 사용자가 쓰고, 사용자가 써야 데이터가 쌓임.

**해결:** 해커톤 전에 Gemini + 웹 크롤링으로 데이터 미리 쌓기.

### 4.2 4단계 데이터 수집 파이프라인

**전략: 식당은 최대한 다 긁고, 메뉴는 가능한 만큼 파싱.**
메뉴 없는 식당도 지도에 표시 → 사용자 제보 유도.

```
┌──────────────────────────────────────────────┐
│ 1단계: Places API 공격적 수집                │
│ → GR 반경 15mi, 카테고리 × 지역 매트릭스     │
│   - 카테고리 쿼리 15개                       │
│     (pizza, mexican, asian, burger, coffee,  │
│      sandwich, sushi, breakfast, deli, etc)  │
│   - 격자 기반 Nearby Search 20~30개 포인트   │
│ → google_place_id로 중복 제거                │
│ → OpenStreetMap Overpass API로 보완           │
│ → 예상: 1500~2500개 식당                     │
│ → DB: source='places_api'                    │
└──────────────┬───────────────────────────────┘
               ↓
┌──────────────────────────────────────────────┐
│ 2단계: website 있는 식당만 크롤링            │
│ → 1500개 중 ~800개 website 있음              │
│ → /menu, /menus 경로 탐색                    │
│ → HTML 또는 PDF 다운로드                     │
│ → 성공률 ~50% (400개 식당)                   │
│ → robots.txt 준수, User-Agent 명시           │
└──────────────┬───────────────────────────────┘
               ↓
┌──────────────────────────────────────────────┐
│ 3단계: Gemini로 메뉴 파싱                     │
│ - HTML이면 텍스트 추출 → Gemini Text         │
│ - PDF면 페이지별 이미지 → Gemini Vision       │
│ → 각 식당당 5~20개 메뉴 추출                 │
│ → DB: source='gemini_web', status=AI         │
│ → 예상 총 2000~4000개 메뉴                   │
└──────────────┬───────────────────────────────┘
               ↓
┌──────────────────────────────────────────────┐
│ 4단계: 사용자 제보 + 포인트/레벨             │
│ → 메뉴 없는 ~1100개 식당이 "첫 제보 보너스"   │
│   대상 (기본 +10 + 첫 제보 +5 = +15 pts)     │
│ → AI parsed → Human verified 전환            │
└──────────────────────────────────────────────┘
```

**1~3단계는 해커톤 전 & 초반에 배치 작업.**
**4단계는 앱 런칭 후 지속 운영.**

**결과적으로 데모 시점에 앱 상태:**
- 지도에 ~1500~2500개 식당 핀 표시
- 그중 ~400개는 메뉴 데이터 있음 (컬러 핀)
- 나머지 ~1100~2100개는 빈 핀 (회색, "첫 제보 +15 pts")
- 심사위원이 지도 어디를 찍어도 식당 핀이 있음 → 커버리지 임팩트

### 4.3 법적 체크리스트

비영리 학술 해커톤 프로젝트 → 리스크 낮음. 단, F-1 비자 상태 고려해서 조심:

- robots.txt 준수 (`reppy` 또는 `urllib.robotparser`)
- User-Agent: `BrokenLunchHackathonBot/1.0 (academic project - contact: your_email)`
- 요청 간격: 식당당 2~3초
- 앱에 데이터 출처 명시 ("Source: restaurant's official website")
- 소송 우려 큰 사이트 제외 (Grubhub, DoorDash, UberEats는 절대 안 함)

---

## 5. 포인트/레벨 시스템

### 5.1 왜 이 시스템이 필요한가

**3가지 문제 동시 해결:**
1. **데이터 수집** — 사용자가 사진 찍을 동기 부여
2. **데이터 품질** — 레벨 높은 사용자 = 검증된 기여자
3. **리텐션** — 앱에 다시 돌아올 이유

### 5.2 포인트 획득

| 액션 | 포인트 |
|------|--------|
| 메뉴판 사진 업로드 + Gemini 파싱 성공 | +10 |
| ↳ 해당 식당의 **첫 제보**일 때 추가 보너스 | +5 |
| 기존 메뉴 가격 확인 ("맞아요" 버튼) | +3 |
| 내 제보를 다른 사용자가 확인 | +5 |
| 식당 Rating (Level 3+ 만 가능) | +2 |
| 매일 첫 앱 실행 (리텐션) | +1 |

**첫 제보 보너스**가 핵심 게이미피케이션 장치.
메뉴 없는 빈 식당(~1100개)을 다 채우면 +5500 포인트 = Level 7.
자연스럽게 데이터 커버리지 확보.

### 5.3 레벨 구간

| Level | 이름 | 포인트 | 획득 권한 | Rating 가중치 |
|-------|------|--------|-----------|--------------|
| 1 | Newbie | 0 ~ 49 | 기본 제보 | 1x |
| 2 | Scout | 50 ~ 149 | 사진 없이 가격만 제보 | 1x |
| 3 | Regular | 150 ~ 399 | 식당 Rating | 1x |
| 4 | Explorer | 400 ~ 999 | — | 2x |
| 5 | Expert | 1000 ~ 2499 | — | 3x |
| 7 | Veteran | 2500 ~ 9999 | — | 5x |
| 10 | Legend | 10000+ | 배지 표시 | 10x |

### 5.4 Rating 가중치 계산

```python
# 식당/메뉴의 최종 Rating
total_weighted_score = sum(rating * level_weight for each rating)
total_weight = sum(level_weight for each rating)
final_rating = total_weighted_score / total_weight

# 예시:
# Newbie 5점 rating  → 5 × 1 = 5 weighted
# Expert 5점 rating  → 5 × 3 = 15 weighted
# Legend 5점 rating  → 5 × 10 = 50 weighted
```

### 5.5 가격 검증 전환 로직

```
menu_item 초기 상태: ai_parsed
  ↓
사용자 confirm 누를 때마다:
  confirmation_weight += user_level_weight
  ↓
if confirmation_weight >= 5:
  status → human_verified
  ↓
서로 다른 가격 제보 감지 시:
  status → disputed
```

**AI parsed → Human verified 전환 조건:**
- Newbie 5명 OR
- Expert 2명 OR
- Legend 1명

### 5.6 해커톤 내 구현 범위

**시간 부족 대비 우선순위:**

**구현 완료 (필수):**
- `verification_status` 필드 + UI 배지
- `confirmation_weight` 저장 로직
- "이 가격 맞아요" 버튼

**발표 슬라이드에만 (미래 비전):**
- 포인트 획득 UI
- 레벨업 애니메이션
- 배지 시스템
- 프로필 화면

발표 때: "이게 지금 구현된 부분, 이게 다음 단계" 명확히 구분.

---

## 6. Gemini API 사용 방식 (3-in-1)

**Best Use of Gemini 상의 핵심 어필 포인트.**

### 6.1 Use Case 1: 데이터 파이프라인 (배치)
**언제:** 해커톤 전 & 진행 중 배치 작업
**무엇:** GR 식당 ~400개 웹사이트에서 메뉴 자동 파싱
**결과:** ~1500~3000개 메뉴 데이터

### 6.2 Use Case 2: 실시간 제보 (사용자)
**언제:** 사용자가 앱에서 메뉴판 사진 업로드 시
**무엇:** Gemini Vision으로 메뉴명 + 가격 추출
**결과:** 수동 입력 없이 제보 완료, 포인트 지급

### 6.3 Use Case 3: 자연어 추천
**언제:** 사용자가 "비 오는 날 따뜻한 거 $10 이하" 같은 쿼리 입력
**무엇:** Gemini가 주변 메뉴 리스트에서 상황에 맞는 5개 큐레이션
**결과:** 단순 필터링 이상의 추천

### 발표 문구
> "저희 앱은 Gemini를 3가지 방식으로 씁니다:
> 1. 데이터 파이프라인: GR 400개 식당 웹사이트에서 메뉴 자동 파싱
> 2. 사용자 제보: 메뉴판 사진 → 자동 구조화
> 3. 자연어 추천: 상황/기분 기반 메뉴 큐레이션
> 
> 단순 챗봇이 아닌, **AI가 데이터를 만들고 커뮤니티가 검증하는 시스템**입니다."

---

## 7. 기술 스택

### Frontend (Android)
- Kotlin 1.9+
- Jetpack Compose (BOM 2024.09+)
- Google Maps Compose
- Retrofit + OkHttp + Moshi
- CameraX
- Hilt (DI)
- Coil (이미지 로딩)
- Navigation Compose

### Backend
- Python 3.11
- FastAPI
- SQLAlchemy 2.x + asyncpg
- Alembic (마이그레이션)
- GeoAlchemy2 (PostGIS)
- google-genai (Gemini SDK)
- httpx (Places API + 웹 크롤링)
- BeautifulSoup4 + pdfplumber (메뉴 페이지 파싱)
- reppy (robots.txt)

### Infra
- DigitalOcean App Platform (FastAPI)
- DigitalOcean Managed PostgreSQL + PostGIS
- DigitalOcean Spaces (이미지 스토리지, S3 호환)
- Google Cloud (Gemini API, Places API, Maps SDK)

### 개발 도구
- Claude Code (Claude Max 플랜)
- GitHub
- Android Studio
- Postman/Bruno (API 테스트)

---

## 8. 아키텍처

```
┌────────────────────────────────────────────────┐
│ Android App (Kotlin + Compose)                 │
│ ├ Map Screen (커스텀 가격 핀)                   │
│ ├ List Screen (Survive/Cost-effective/Luxury)  │
│ ├ Detail Screen (verification badges)          │
│ ├ Submit Screen (Camera + Gemini)              │
│ └ Recommend Screen (자연어 쿼리)                │
└─────────────────┬──────────────────────────────┘
                  │ HTTPS
                  ▼
┌────────────────────────────────────────────────┐
│ FastAPI Backend (DigitalOcean App Platform)    │
│ ├ GET  /restaurants/nearby                     │
│ ├ GET  /restaurants/{id}                       │
│ ├ POST /submissions                            │
│ ├ POST /confirmations (가격 확인)              │
│ ├ POST /parse-menu-image                       │
│ ├ POST /recommend                              │
│ └ GET  /me (사용자 레벨/포인트)                │
└─────────────────┬──────────────────────────────┘
                  │
      ┌───────────┼───────────┬──────────┐
      ▼           ▼           ▼          ▼
  PostgreSQL  Gemini API  Places API  DO Spaces
  +PostGIS    (Vision+Text)           (이미지)
```

---

## 9. 리포지토리 구조

```
broken-lunch-gr/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/              # SQLAlchemy ORM
│   │   │   ├── restaurant.py
│   │   │   ├── menu.py
│   │   │   ├── submission.py
│   │   │   └── device.py
│   │   ├── schemas/             # Pydantic
│   │   ├── routers/
│   │   │   ├── restaurants.py
│   │   │   ├── submissions.py
│   │   │   ├── confirmations.py
│   │   │   └── gemini.py
│   │   └── services/
│   │       ├── places.py        # Google Places 클라이언트
│   │       ├── gemini.py        # Gemini 래퍼 (3 use cases)
│   │       └── crawler.py       # 식당 웹사이트 크롤러
│   ├── scripts/
│   │   ├── 01_seed_places.py    # Places API로 식당 수집
│   │   ├── 02_crawl_menus.py    # 식당 웹사이트 크롤링
│   │   └── 03_parse_with_gemini.py  # Gemini 파싱
│   ├── migrations/              # Alembic
│   ├── .env.example
│   ├── requirements.txt
│   └── Dockerfile
├── android/
│   ├── app/src/main/java/com/brokenlunch/gr/
│   │   ├── MainActivity.kt
│   │   ├── ui/
│   │   │   ├── map/
│   │   │   ├── list/
│   │   │   ├── detail/
│   │   │   ├── submit/
│   │   │   └── recommend/
│   │   ├── data/
│   │   │   ├── api/
│   │   │   ├── model/
│   │   │   └── repository/
│   │   └── di/
│   ├── build.gradle.kts
│   └── local.properties         # API 키 (git 제외)
└── docs/
    ├── MASTER_DESIGN.md         # 이 문서
    ├── SCHEMA.sql
    ├── API.md
    ├── GEMINI_PROMPTS.md
    └── CLAUDE_CODE_TASKS.md
```

---

## 10. 타임라인 (일요일 11시 마감 역산)

### Phase 0: 준비 (오늘 지금 ~ 1시간)
- [ ] Google Cloud 프로젝트 + Places API + Maps SDK + Gemini API 활성화
- [ ] Google AI Studio에서 Gemini API 키 발급
- [ ] DigitalOcean 계정 + $200 학생 크레딧
- [ ] DigitalOcean Managed PostgreSQL 생성 + PostGIS 활성화
- [ ] GitHub 리포 `broken-lunch-gr` 생성
- [ ] 이 5개 문서를 `docs/`에 커밋

### Phase 1: Backend (오늘 저녁 ~ 새벽, 6시간)
- [ ] FastAPI 스캐폴딩 (Claude Code)
- [ ] DB 스키마 + 마이그레이션
- [ ] Places API 수집 스크립트 실행 → 500개 식당 DB에 저장
- [ ] 식당 웹사이트 크롤러 + Gemini 파싱 파이프라인
- [ ] REST API 엔드포인트 5개
- [ ] Gemini 래퍼 서비스 (Vision + Text)
- [ ] DigitalOcean에 배포

### Phase 2: Android (토요일 오전 ~ 저녁, 10시간)
- [ ] Android 프로젝트 초기화 (Claude Code)
- [ ] Retrofit + API 클라이언트
- [ ] Map Screen (커스텀 핀, 가격 박힌 알약 모양)
- [ ] List Screen (3 티어 섹션)
- [ ] Restaurant Detail (verification 배지)
- [ ] Submit Screen (카메라 + Gemini)
- [ ] Recommend Screen (자연어)

### Phase 3: 통합 & 데모 (토요일 저녁 ~ 일요일 오전, 6시간)
- [ ] 시드 데이터 검수 + 수동 보정
- [ ] 데모 시나리오 리허설 (3분)
- [ ] 발표 슬라이드 (Google Slides, 6장)
- [ ] 백업 계획 (백엔드 죽으면 ngrok)
- [ ] Devpost 제출
- [ ] Demo video 녹화 (3분)

**총 예상: ~22시간. 여유 ~10시간 (디버깅, 휴식).**

---

## 11. 데모 시나리오 (3분)

### 타임라인
```
0:00 — 문제 제시 (30초)
  "Calvin 학생인 저는 점심 $10 이하로 먹을 데 찾기 힘들어요.
   Google Maps는 $$ 같은 대충 필터만 있고, Yelp도 메뉴 가격을 안 보여줘요."

0:30 — 앱 overview (30초)
  지도 화면 → 3티어 필터 토글 → 핀 클릭 → 식당 상세
  Verification 배지 포인팅: "AI parsed vs Human verified"

1:00 — 라이브 Gemini 데모 #1 (60초)
  심사장 벽에 GR 식당 메뉴판 프린트해서 붙여놓기
  → 폰으로 사진 찍기
  → 5초 안에 "12 items parsed" 토스트
  → 지도에 새 핀 등장

2:00 — 라이브 Gemini 데모 #2 (45초)
  심사위원에게 "뭐 드시고 싶으세요?"
  → 그 답을 자연어로 입력
  → Gemini가 주변 메뉴 5개 추천

2:45 — 마무리 (15초)
  "Gemini가 데이터를 만들고, 커뮤니티가 검증하는 시스템.
   해커톤 48시간 동안 GR 전체 식당의 메뉴를 DB화 했습니다."
```

### 백업 계획
- 인터넷 끊기면? 로컬 백엔드 ngrok 터널링
- Gemini 응답 느리면? 미리 찍어둔 사진으로 캐시된 응답 보여주기
- Android 빌드 죽으면? 스크린 레코딩 영상으로 대체

---

## 12. 발표 슬라이드 (Google Slides, 6장)

1. **제목** — Broken Lunch GR · One-liner · 팀 이름
2. **문제** — 대학생/저소득층 식비 통계, 기존 앱의 한계
3. **솔루션** — 핵심 스크린샷 3장 (Map / List / Submit)
4. **Gemini 3-in-1 사용** — 파이프라인 다이어그램
5. **기술 스택** — 로고 + 한 줄 설명
6. **팀 + 링크** — GitHub, Devpost, Demo URL

---

## 13. 리스크 & 대응

| 리스크 | 확률 | 대응 |
|--------|------|------|
| Android Maps SDK 설정 막힘 | 중 | OSM + osmdroid 폴백 준비 |
| Gemini가 메뉴판 잘못 파싱 | 높음 | **Pydantic 스키마 검증** + safe default + 수동 입력 폴백 |
| Gemini 응답이 이상한 JSON 형식 | 중 | `response_mime_type='application/json'` + Pydantic으로 2차 검증 |
| 웹 크롤링 중 429 Too Many Requests | 중 | **tenacity exponential backoff** + 동시성 3으로 낮춤 |
| 크롤러 스크립트 중간에 죽음 | 중 | **crawl_log 활용한 resume logic** (--retry-failed, --fresh 플래그) |
| PostGIS 세팅 실패/버그 | 중 | **Haversine Plan B 준비** (lat/lng 컬럼 병행 저장) |
| DigitalOcean 배포 실패 | 낮음 | 로컬 + ngrok 폴백 |
| 시간 부족 | 중 | 자연어 추천 → Gemini 파싱 → 제보 UI 순으로 cut |
| Gemini API 쿼터 | 낮음 | Flash 모델 쓰고, 학생 혜택 받기 |
| 악성 유저의 가짜 가격 제보 | 낮음 | **Reports 기능 + 3회 이상 신고 시 자동 disputed** |

### 방어적 설계 요약

이번 설계 리뷰에서 보강된 5가지 failure mode 대응:

1. **Gemini 출력 검증** — Pydantic `ParsedMenuResponse`, `RecommendResponse` 모델로 응답을 2차 검증. 스키마 안 맞으면 safe default 반환하고 앱은 계속 작동.

2. **PostGIS Plan B** — 모든 식당에 lat/lng 컬럼을 PostGIS와 병행 저장. PostGIS 세팅이 실패해도 Python Haversine으로 거리 계산 가능. 2500개 식당이면 100ms 안에 쿼리.

3. **Rate limit 방어** — `tenacity` 라이브러리로 exponential backoff. Places API/Gemini API 둘 다. 동시성도 5 → 3으로 보수적.

4. **재시작 가능 파이프라인** — `crawl_log` 테이블에 식당별 처리 상태 기록. 스크립트 재실행 시 완료된 것은 skip. `--retry-failed`, `--fresh` 플래그.

5. **Reports 기능** — 신고 테이블 + 3회 이상 시 자동 `disputed` 전환. 심사위원이 "악성 유저 방지는요?" 물으면 방어 가능.

---

## 14. 성공 지표 (발표 기준)

**반드시 보여줘야 할 것:**
1. ✅ 지도에 GR 500개 식당 핀 표시
2. ✅ 3티어 필터 작동
3. ✅ 식당 상세에 verification 배지 표시
4. ✅ 라이브 Gemini 메뉴 파싱 성공 (최소 1번)
5. ✅ 자연어 추천 응답

**있으면 좋지만 없어도 OK:**
- 포인트/레벨 UI (슬라이드에만)
- 사용자 계정 프로필
- 리뷰 시스템

---

## 15. 해커톤 후 로드맵 (발표 언급용)

### v1.1 (해커톤 후 1주일)
- 포인트/레벨 시스템 완전 구현
- 사용자 프로필 화면
- 배지 시스템

### v1.2 (2주)
- 미시간 주요 도시 확장 (Holland, Lansing, Detroit)
- 식당 파트너십 프로그램 (식당이 직접 가격 업데이트)

### v2 (1~2개월)
- iOS 버전
- 웹 버전 (PWA)
- 대학 캠퍼스별 특화 기능 (meal plan 연동)

---

## 16. 참고 자료

- 거지맵 (한국 레퍼런스): https://broke-map.com
- Google Places API New: https://developers.google.com/maps/documentation/places/web-service/overview
- Gemini API Docs: https://ai.google.dev/gemini-api/docs
- DigitalOcean App Platform: https://docs.digitalocean.com/products/app-platform/
- Jetpack Compose Maps: https://github.com/googlemaps/android-maps-compose

---

## 17. 연락 & 팀

- GitHub: https://github.com/Huni-code
- 팀: Solo (Claude Code 활용)
- 학교: Calvin University
