# Visual Design Spec

앱의 시각적 일관성을 위한 디자인 토큰 + 컴포넌트 스펙.

---

## Color Tokens

### Tier Colors

| Tier | BG (fill 50) | Border (600) | Text (800) | 용도 |
|------|------------|------------|-----------|------|
| Survive | `#EAF3DE` | `#639922` | `#27500A` | $0-5 |
| Cost-effective | `#FAEEDA` | `#BA7517` | `#633806` | $5-10 |
| Luxury | `#FCEBEB` | `#A32D2D` | `#791F1F` | $10-15 |

### Verification Status Colors

| Status | BG | Text | Icon | 의미 |
|--------|-----|------|------|------|
| AI parsed | `#EEEDFE` (purple) | `#26215C` | ⭐ star | AI가 파싱, 미검증 |
| Human verified | `#E1F5EE` (teal) | `#04342C` | ✓ check | 사용자들이 확인 |
| Disputed | `#FAEEDA` (amber) | `#412402` | ⚠️ warning | 가격 제보 불일치 |
| Needs verification | — (text only) | `#854F0B` | — | 확인 필요 |

### Semantic Colors
- Primary action: Material 기본 사용
- Error: `#A32D2D`
- Success: `#0F6E56`
- Info: `#185FA5`

---

## Typography

- Font family: default sans (system)
- 크기:
  - H1 (화면 타이틀): 22sp, weight 500
  - H2 (섹션 헤더): 18sp, weight 500
  - H3 (카드 타이틀): 16sp, weight 500
  - Body: 14sp, weight 400
  - Caption: 12sp, weight 400
  - Micro (배지): 10sp, weight 500
- Line height: 1.4 (body)
- **대문자 사용 금지** (sentence case)

---

## Spacing

- XS: 4dp
- S: 8dp
- M: 16dp
- L: 24dp
- XL: 32dp

컴포넌트 내 padding: 12~16dp
컴포넌트 간 gap: 8~16dp
화면 외곽 padding: 16dp

---

## Component Specs

### 1. 지도 핀 (3가지 상태)

```
populated_verified (실선 + 가격):
┌──────────────────┐
│ [아이콘] $4.50  │  ← solid border
└──────────────────┘

populated_ai (점선 + 가격):
┌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐
│ [아이콘] $4.99  │  ← dashed border
└╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘

empty (회색 + ?):
┌──────────────────┐
│ [ ? ] +15 pts   │  ← gray, CTA
└──────────────────┘
```

공통:
- 높이: 28dp
- 패딩: 좌 3dp, 우 10dp, 상하 3dp
- 아이콘 영역: 22dp 원형 white background
- Border: 1.5dp
- Gap between icon and text: 5dp
- Shadow: 없음 (플랫)

populated_verified:
- bg/border/text: tier 색상 (50/600/800 stops)
- Border style: solid
- 아이콘: 카테고리 이모지 12sp

populated_ai:
- bg/border/text: tier 색상 (같음)
- Border style: dashed (3dp on, 2dp off)
- 아이콘: 카테고리 이모지 12sp

empty:
- bg: #F1EFE8 (gray 50)
- border: #B4B2A9 (gray 200), solid
- 텍스트: "+15 pts", 11sp weight 500, color #5F5E5A
- 아이콘: "?" 12sp weight 500, color #888780

### 2. 메뉴 카드 (식당 상세에서)

```
┌──────────────────────────────────────────────┐
│ Hummus pita                         $4.50  │
│ with tahini sauce                           │
│                                              │
│ [✓ Human verified]  3 users · today        │
│                                              │
│ [✓ Confirm price] [✗ Different price]      │
└──────────────────────────────────────────────┘
```

- 전체 padding: 14dp 16dp
- BG: white, border 0.5dp #E0E0E0, radius 12dp
- 메뉴명 (H3) + 가격 (14sp, weight 500): Row with spaceBetween
- 설명: 13sp, secondary color
- Verification 배지: 
  - 높이 20dp, padding 2dp 8dp, radius 999dp
  - 아이콘 10dp + 텍스트 10sp weight 500
- 하단 버튼 Row:
  - Outlined button 2개, 동일 weight

### 3. 리스트 아이템 카드

```
┌──────────────────────────────────────────────┐
│ ⦿  Jet's Pizza                       $4.50 │
│    8-corner slice · 0.5 mi                  │
└──────────────────────────────────────────────┘
```

- 높이: 56dp
- Padding: 12dp 16dp
- Leading icon: 32dp 원형, 카테고리 배경색 (tier 50 stop)
- 중앙 텍스트: 식당명 (13sp weight 500) + 메뉴 · 거리 (11sp secondary)
- Trailing: 가격 (13sp weight 500, tier color)

### 4. 리스트 섹션 헤더

```
┃ Survive                          8 spots
┃ $0 - $5 · eat to live
```

- Left border: 3dp (tier color)
- Padding: 14dp left, 10dp top/bottom
- Title: 13sp weight 500, tier 800 color
- Subtitle: 10sp secondary
- 오른쪽 counter: 10sp secondary

### 5. 상단 필터 Chip Row

```
[Survive] [Cost-effective] [Luxury]
```

- 각 Chip:
  - 높이 28dp
  - Padding 5dp 10dp
  - Radius 999dp
  - 비활성: 회색 outline (`#E0E0E0` border, text secondary)
  - 활성: tier 색상 (bg 50, border 600, text 800)
  - 폰트: 11sp weight 500
- Gap: 6dp

### 6. FAB (내 위치)

- Material FAB Small (40dp)
- White bg + tertiary border
- Icon: `Icons.Default.MyLocation`
- 위치: 하단 우측, 16dp margin

### 7. Verification Badge (micro)

가격 옆에 작은 배지:

```
[⭐ AI parsed]
```

- 높이 16dp, padding 2dp 8dp, radius 999dp
- 아이콘 10dp + 텍스트 10sp weight 500
- 색상 조합은 위 verification status colors 표 참고

---

## UI Patterns

### 로딩 상태

- 전체 화면 로딩: `CircularProgressIndicator` 중앙
- 리스트 로딩: Shimmer placeholder (상위 3개 아이템 형태)
- Gemini 파싱 중: "Parsing menu with AI..." + indicator
- Pull-to-refresh: 지도/리스트에서 활성화

### 에러 상태

- 네트워크 에러: "Can't reach server" + 재시도 버튼
- 빈 결과: 중앙 일러스트 + 설명 + CTA

### 토스트 vs Snackbar

- 포인트 획득: Snackbar ("+10 points · Level 3 unlocked!")
- 단순 알림: Toast
- 에러: Snackbar with action

### 권한 요청

- 최초 위치 권한:
  - Rationale 다이얼로그 먼저 (왜 필요한지)
  - 허용 → 지도 로딩
  - 거부 → GR 중심 좌표로 fallback
- 카메라 권한: 제보 화면 진입 시점에 요청

---

## 다크 모드

- 지원은 하되 해커톤 우선순위 낮음
- Material3 기본 dark theme 적용
- Tier colors는 light/dark 둘 다 작동 (50 vs 800 stop swap)

---

## 접근성

- 최소 터치 영역: 44dp
- 색상 대비: WCAG AA 이상 (tier 800 on tier 50 fill은 충분)
- Semantic labels 필수:
  - Verification 배지: "AI parsed price" / "Human verified price"
  - 아이콘 버튼: contentDescription 필수

---

## 아이콘

카테고리별:
- pizza: 🍕
- burger: 🍔  
- mexican: 🌮
- asian: 🍜
- sandwich: 🥪
- coffee: ☕
- bakery: 🥐
- mediterranean: 🥙
- breakfast: 🍳
- chicken: 🍗
- dessert: 🍰
- other: 🍴

**주의:** 실제 프로덕션에선 SVG 아이콘 세트로 교체. 이모지는 Android 버전마다 렌더링 달라짐. 해커톤에선 이모지로 빠르게.

---

## 레퍼런스

- 거지맵 (한국): https://broke-map.com
- Google Maps 핀 스타일 (우리 핀 형태 아님)
- Material3 Chips (필터 칩 스타일)
