# Gemini Prompts

**모델:** `gemini-2.5-flash` (Vision + Text, 빠름, 저렴)
**SDK:** `google-genai` (Python)

Gemini를 3가지 방식으로 사용. Best Use of Gemini 상의 핵심 어필 포인트.

---

## Use Case 1: Web Menu Parsing (배치, 해커톤 전/초반)

### 목적
식당 공식 웹사이트에서 다운로드한 메뉴 HTML/PDF를 구조화된 JSON으로 변환.

### 1-A: HTML 메뉴 파싱 (Text 모드)

**System instruction:**
```
You are a menu data extractor. You receive HTML text content from a restaurant's
menu page and must extract all menu items with prices.

You MUST respond with valid JSON only. No prose, no markdown code fences.
```

**User prompt:**
```
Below is HTML/text content from a restaurant's menu page.
Extract all food items with clearly stated prices.

Rules:
- Only include items priced $15.00 or less (our app scope).
- Skip drinks unless they're the main item (coffee/tea shops OK).
- Skip "market price" or "varies" items.
- For items with multiple sizes, create separate entries (e.g., "Pizza (small)", "Pizza (medium)").
- Translate prices to cents: $4.50 → 450, $10 → 1000.
- Categorize each item: burger, pizza, sandwich, pasta, salad, soup,
  mexican, asian, mediterranean, breakfast, dessert, drink, other.

Output schema:
{
  "items": [
    {
      "name": "string (clean item name)",
      "description": "string or null (short description if shown)",
      "price_cents": integer,
      "category": "string",
      "confidence": float (0.0 to 1.0)
    }
  ],
  "restaurant_name_detected": "string or null",
  "warnings": ["string", ...]
}

Content:
---
{html_text}
---
```

**Python 호출:**
```python
from google import genai
from google.genai import types
import json

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        system_instruction=WEB_MENU_PARSER_SYSTEM,
        response_mime_type="application/json",
    ),
    contents=user_prompt.format(html_text=cleaned_html),
)

data = json.loads(response.text)
```

### 1-B: PDF 메뉴 파싱 (Vision 모드)

PDF를 페이지별 이미지로 변환 후 Vision API 사용.

```python
import pdf2image

pages = pdf2image.convert_from_path(pdf_path, dpi=200)
all_items = []

for page_num, page_img in enumerate(pages):
    img_bytes = page_img_to_bytes(page_img)
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
            VISION_MENU_PROMPT,
        ],
    )
    
    data = json.loads(response.text)
    all_items.extend(data["items"])
```

---

## Use Case 2: User Photo Menu Parsing (실시간)

### 목적
사용자가 앱에서 메뉴판 사진 찍어 업로드 → Gemini Vision → 자동 제보.

### System instruction
```
You are a menu parser specialized in reading restaurant menu photos taken with
a phone camera. The images may be blurry, angled, or in varied lighting.

Focus on accuracy over completeness — if you can't clearly read a price, skip
that item rather than guessing.

You MUST respond with valid JSON only.
```

### User prompt (with image attached)
```
This is a photo of a restaurant menu board or menu card.

Extract all menu items where you can clearly read both the name AND the price.

Rules:
- Only include items priced $15 or less.
- Skip items where the price is unclear, smudged, or cut off.
- If a single item has multiple sizes/options listed (Small/Medium/Large),
  create separate entries.
- Translate prices to cents.
- Confidence should reflect how sure you are about reading the price correctly.

Output schema:
{
  "items": [
    {
      "name": "string",
      "description": "string or null",
      "price_cents": integer,
      "category": "string",
      "confidence": float (0.0 to 1.0)
    }
  ],
  "warnings": ["string", ...]
}

If the image is unreadable, return {"items": [], "warnings": ["unreadable"]}.
If the image does not appear to be a menu, return {"items": [], "warnings": ["not_a_menu"]}.
```

### Python 호출
```python
with open(photo_path, "rb") as f:
    image_bytes = f.read()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        system_instruction=PHOTO_PARSER_SYSTEM,
        response_mime_type="application/json",
    ),
    contents=[
        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        USER_PROMPT,
    ],
)

data = json.loads(response.text)
```

### Expected output
```json
{
  "items": [
    {
      "name": "Hummus pita",
      "description": "with tahini",
      "price_cents": 450,
      "category": "mediterranean",
      "confidence": 0.95
    },
    {
      "name": "Falafel wrap",
      "description": null,
      "price_cents": 699,
      "category": "mediterranean",
      "confidence": 0.88
    }
  ],
  "warnings": []
}
```

---

## Use Case 3: Natural Language Recommendation

### 목적
사용자의 자연어 쿼리 + 주변 메뉴 리스트 → Gemini가 큐레이션.

### Backend 사전처리
```python
# 1. 주변 반경 2km 내 메뉴 조회 (최대 50개)
nearby_menus = await db.execute(
    """
    SELECT m.id, m.name, m.price_cents, m.category, m.verification_status,
           r.name as restaurant_name,
           ST_Distance(r.location, :user_point) as distance_m
    FROM menu_items m
    JOIN restaurants r ON m.restaurant_id = r.id
    WHERE ST_DWithin(r.location, :user_point, 2000)
      AND m.is_active = TRUE
    ORDER BY 
      CASE m.verification_status 
        WHEN 'human_verified' THEN 1 
        WHEN 'ai_parsed' THEN 2 
        ELSE 3 
      END,
      distance_m ASC
    LIMIT 50
    """,
    {"user_point": user_point},
)

# 2. Gemini에 전달할 구조로 변환
menus_for_gemini = [
    {
        "id": str(m.id),
        "name": m.name,
        "restaurant": m.restaurant_name,
        "price_cents": m.price_cents,
        "category": m.category,
        "distance_m": int(m.distance_m),
        "verified": m.verification_status == "human_verified",
    }
    for m in nearby_menus
]
```

### System instruction
```
You are a restaurant recommendation assistant for "Broken Lunch GR", an app
that helps students and low-budget diners find cheap meals ($15 or less) in
Grand Rapids, Michigan.

You will be given:
1. A user's natural language request (may be in Korean or English).
2. A list of available menu items with restaurant, price, distance, verification status.

Return the top 5 best matches as JSON. Reasoning must be concise (under 80 chars)
and in the same language as the user's query.

Guidelines:
- Match the intent of the query, not just keywords.
  - "warm food" → exclude salads, ice cream
  - "quick" → prefer closer restaurants
  - "healthy" → prefer salads, soups, grilled items
  - "cheap" → prefer sub-$7 items
- Prefer verified items (verified=true) over AI-parsed ones.
- Sort by relevance first, then price ascending.
- If nothing matches well, return fewer than 5 items.
```

### User prompt
```
User query: "{query}"
User location: ({lat}, {lng})

Available menus (JSON):
{menus_json}

Return this schema:
{
  "recommendations": [
    {
      "menu_item_id": "uuid from input (must match exactly)",
      "reason": "short explanation, under 80 chars, same language as query"
    }
  ]
}
```

### 후처리
```python
# Gemini 응답
result = json.loads(response.text)

# 화이트리스트 검증 (Gemini가 잘못된 ID 만들 수 있음)
valid_ids = {m["id"] for m in menus_for_gemini}
filtered = [
    rec for rec in result["recommendations"]
    if rec["menu_item_id"] in valid_ids
]

# DB에서 다시 enrichment
full_recommendations = []
for rec in filtered:
    menu = await get_menu_with_restaurant(rec["menu_item_id"])
    full_recommendations.append({
        **menu.to_dict(),
        "reason": rec["reason"],
    })

return {"recommendations": full_recommendations}
```

---

## 비용 추정

| 작업 | 토큰 (대략) | 비용/건 | 해커톤 예상 건수 | 총 비용 |
|------|------------|---------|----------------|---------|
| 웹 메뉴 파싱 (텍스트) | 3k in + 500 out | ~$0.0003 | 400 | $0.12 |
| PDF 메뉴 파싱 (Vision) | 2k in + 500 out | ~$0.0003 | 200 (페이지) | $0.06 |
| 실시간 사진 파싱 | 2k in + 500 out | ~$0.0003 | 50 | $0.02 |
| 자연어 추천 | 4k in + 300 out | ~$0.0003 | 30 | $0.01 |

**총 예상: $0.21**

해커톤 기간 동안 걱정 0. Google AI Pro 학생 무료 1년 받으면 완전 공짜.

---

## 프롬프트 튜닝 노하우

### response_mime_type="application/json"
반드시 사용. 없으면 Gemini가 ```json ... ``` 이런 마크다운 코드 블록 감싸서 반환함.

### confidence 필드
Gemini에게 confidence 0~1로 넣으라고 하면 재밌게도 **정말로 자기 확신도를 넣어줌**. 낮은 confidence (< 0.6) 항목은 자동으로 `verification_status = 'needs_verification'` 으로 표시.

### 언어 매칭
사용자가 한국어로 쓰면 reason도 한국어로. Gemini는 prompt에서 "same language as query" 지시 잘 따름.

### JSON 파싱 안전장치
```python
try:
    data = json.loads(response.text)
except json.JSONDecodeError:
    # 최악의 경우: "json ... " 같은 prefix 있으면 trim
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)
```

실제로 `response_mime_type="application/json"` 쓰면 이 안전장치 거의 안 걸림.

---

## 실패 케이스 & 폴백

### 메뉴판 파싱 실패
| 상황 | 응답 | 프론트 대응 |
|------|------|-----------|
| JSON 아닌 텍스트 반환 | `items: []`, `warnings: ["parse_error"]` | "파싱 실패, 수동 입력해주세요" |
| 빈 이미지 | `items: []`, `warnings: ["unreadable"]` | "사진이 흐려요. 다시 찍어주세요" |
| 메뉴 아닌 사진 | `items: []`, `warnings: ["not_a_menu"]` | "메뉴판 사진이 아닌 것 같아요" |
| confidence 전부 < 0.5 | `items: [...]`, `warnings: ["low_confidence"]` | 항목 보여주되 "확인해주세요" |

### 추천 실패
- 주변 식당 0개 → `recommendations: []` + 프론트 토스트 "범위를 넓혀보세요"
- Gemini 타임아웃 (10초+) → DB에서 거리순 5개 fallback

---

## 데모용 프롬프트 체크리스트

발표 전 반드시 테스트:
- [ ] GR 인기 식당 메뉴판 사진 10장 → 파싱 성공률 확인
- [ ] 한국어 쿼리 "매운 거 $8 이하" → 적절한 추천 나오는지
- [ ] 영어 쿼리 "something warm under $10" → 같은 식으로 잘 되는지
- [ ] 메뉴판이 아닌 사진 (음식 사진) → `"not_a_menu"` 반환하는지
- [ ] 흐린 사진 → 안전하게 실패하는지 (잘못된 가격 만들지 않는지)
