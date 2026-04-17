-- ========================================================================
-- Broken Lunch GR — Database Schema
-- PostgreSQL 15+ with PostGIS extension
-- ========================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ========================================================================
-- restaurants: Google Places에서 수집한 식당 뼈대
-- ========================================================================
CREATE TABLE restaurants (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    google_place_id VARCHAR(255) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    address         TEXT,
    
    -- 좌표는 2가지 방식으로 저장 (PostGIS 세팅 실패 대비 Plan B)
    -- Plan A: PostGIS (빠른 spatial query)
    location        GEOGRAPHY(POINT, 4326),             -- 세팅 성공하면 사용
    -- Plan B: Raw lat/lng (항상 저장, Haversine fallback용)
    lat             DOUBLE PRECISION NOT NULL,
    lng             DOUBLE PRECISION NOT NULL,
    
    phone           VARCHAR(50),
    website         TEXT,
    google_rating   NUMERIC(2, 1),                    -- 4.3
    price_level     SMALLINT,                          -- Google's 1-4
    category        VARCHAR(100),                      -- 'pizza', 'mexican', etc.
    hours_json      JSONB,                             -- Google Places opening_hours
    
    -- 앱 자체 Rating (사용자 가중치 반영)
    app_rating      NUMERIC(3, 2),                     -- 4.35
    rating_count    INTEGER DEFAULT 0,
    
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- PostGIS가 활성화된 경우 INSERT 시 location 자동 채우기 (트리거)
CREATE OR REPLACE FUNCTION sync_location_from_latlng() RETURNS TRIGGER AS $$
BEGIN
    -- PostGIS extension이 있을 때만 동작
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        NEW.location = ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326)::geography;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_sync_location
    BEFORE INSERT OR UPDATE OF lat, lng ON restaurants
    FOR EACH ROW EXECUTE FUNCTION sync_location_from_latlng();

-- lat/lng 기본 인덱스 (Haversine fallback용)
CREATE INDEX idx_restaurants_lat ON restaurants (lat);
CREATE INDEX idx_restaurants_lng ON restaurants (lng);

-- PostGIS GIST 인덱스 (PostGIS 활성화된 경우만 생성)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_restaurants_location ON restaurants USING GIST (location)';
    END IF;
END $$;

CREATE INDEX idx_restaurants_category ON restaurants (category);

-- ========================================================================
-- menu_items: 식당의 메뉴 + 가격 + 검증 상태
-- ========================================================================
CREATE TABLE menu_items (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id           UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    name                    VARCHAR(255) NOT NULL,
    description             TEXT,
    price_cents             INTEGER NOT NULL,          -- $4.50 = 450
    tier                    VARCHAR(20) NOT NULL,      -- auto-computed
    category                VARCHAR(100),              -- 'burger', 'pizza', etc.
    photo_url               TEXT,
    
    -- 데이터 소스 추적
    source                  VARCHAR(30) NOT NULL,
    -- 'gemini_web'       : 식당 웹사이트에서 Gemini로 파싱
    -- 'gemini_photo'     : 사용자 메뉴판 사진을 Gemini로 파싱
    -- 'user_manual'      : 사용자가 수동 입력
    -- 'seed'             : 수기 시드 데이터
    -- 'places_api'       : Google Places API (드물지만 가능)
    
    -- 검증 상태 (핵심 차별화)
    verification_status     VARCHAR(20) NOT NULL DEFAULT 'ai_parsed',
    -- 'ai_parsed'        : AI가 파싱, 미검증
    -- 'human_verified'   : confirmation_weight >= 5
    -- 'disputed'         : 서로 다른 가격 제보
    -- 'needs_verification': AI parsed + 오래됨 (30일+)
    
    confirmation_weight     INTEGER DEFAULT 0,         -- 레벨 가중치 합
    confirmation_count      INTEGER DEFAULT 0,         -- 단순 카운트
    last_verified_at        TIMESTAMPTZ,
    
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT check_tier CHECK (tier IN ('survive', 'cost_effective', 'luxury')),
    CONSTRAINT check_price_positive CHECK (price_cents > 0),
    CONSTRAINT check_price_in_scope CHECK (price_cents <= 1500),
    CONSTRAINT check_source CHECK (source IN (
        'gemini_web', 'gemini_photo', 'user_manual', 'seed', 'places_api'
    )),
    CONSTRAINT check_verification CHECK (verification_status IN (
        'ai_parsed', 'human_verified', 'disputed', 'needs_verification'
    ))
);

CREATE INDEX idx_menu_items_restaurant ON menu_items (restaurant_id);
CREATE INDEX idx_menu_items_tier ON menu_items (tier) WHERE is_active = TRUE;
CREATE INDEX idx_menu_items_status ON menu_items (verification_status) WHERE is_active = TRUE;
CREATE INDEX idx_menu_items_category ON menu_items (category) WHERE is_active = TRUE;

-- tier 자동 계산 트리거
CREATE OR REPLACE FUNCTION compute_tier() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.price_cents <= 500 THEN
        NEW.tier = 'survive';
    ELSIF NEW.price_cents <= 1000 THEN
        NEW.tier = 'cost_effective';
    ELSE
        NEW.tier = 'luxury';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_compute_tier
    BEFORE INSERT OR UPDATE OF price_cents ON menu_items
    FOR EACH ROW EXECUTE FUNCTION compute_tier();

-- verification_status 자동 전환 트리거
-- confirmation_weight가 5 이상이 되면 human_verified로 승격
CREATE OR REPLACE FUNCTION auto_verify_menu() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.confirmation_weight >= 5 AND NEW.verification_status = 'ai_parsed' THEN
        NEW.verification_status = 'human_verified';
        NEW.last_verified_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auto_verify
    BEFORE UPDATE OF confirmation_weight ON menu_items
    FOR EACH ROW EXECUTE FUNCTION auto_verify_menu();

-- ========================================================================
-- devices: 사용자 (로그인 없는 경량 인증 + 포인트/레벨)
-- ========================================================================
CREATE TABLE devices (
    device_id           VARCHAR(128) PRIMARY KEY,
    display_name        VARCHAR(50),                   -- 선택적 닉네임
    
    -- 포인트/레벨 시스템
    points              INTEGER DEFAULT 0,
    level               SMALLINT DEFAULT 1,
    level_weight        INTEGER DEFAULT 1,             -- Rating에 쓸 가중치
    
    -- 통계
    submission_count    INTEGER DEFAULT 0,
    confirmation_count  INTEGER DEFAULT 0,
    
    -- 리텐션
    first_seen          TIMESTAMPTZ DEFAULT NOW(),
    last_seen           TIMESTAMPTZ DEFAULT NOW(),
    daily_streak        SMALLINT DEFAULT 0,
    last_daily_bonus    DATE
);

CREATE INDEX idx_devices_level ON devices (level);

-- 레벨 자동 계산 트리거
CREATE OR REPLACE FUNCTION compute_level() RETURNS TRIGGER AS $$
BEGIN
    -- 레벨 구간 (MASTER_DESIGN.md 섹션 5.3 참고)
    IF NEW.points < 50 THEN
        NEW.level = 1; NEW.level_weight = 1;
    ELSIF NEW.points < 150 THEN
        NEW.level = 2; NEW.level_weight = 1;
    ELSIF NEW.points < 400 THEN
        NEW.level = 3; NEW.level_weight = 1;
    ELSIF NEW.points < 1000 THEN
        NEW.level = 4; NEW.level_weight = 2;
    ELSIF NEW.points < 2500 THEN
        NEW.level = 5; NEW.level_weight = 3;
    ELSIF NEW.points < 10000 THEN
        NEW.level = 7; NEW.level_weight = 5;
    ELSE
        NEW.level = 10; NEW.level_weight = 10;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_compute_level
    BEFORE INSERT OR UPDATE OF points ON devices
    FOR EACH ROW EXECUTE FUNCTION compute_level();

-- ========================================================================
-- submissions: 사용자 제보 기록 (감사 로그 + 포인트 추적)
-- ========================================================================
CREATE TABLE submissions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    menu_item_id    UUID REFERENCES menu_items(id) ON DELETE SET NULL,
    restaurant_id   UUID NOT NULL REFERENCES restaurants(id),
    device_id       VARCHAR(128) NOT NULL REFERENCES devices(device_id),
    
    -- 제보 내용
    menu_name       VARCHAR(255) NOT NULL,
    price_cents     INTEGER NOT NULL,
    photo_url       TEXT,                               -- DO Spaces URL
    gemini_parsed   JSONB,                              -- Gemini raw response
    
    -- 포인트 지급 내역
    points_awarded          INTEGER DEFAULT 0,
    is_first_submission     BOOLEAN DEFAULT FALSE,  -- 해당 식당의 첫 제보?
    
    status          VARCHAR(20) DEFAULT 'accepted',
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT check_submission_status CHECK (status IN ('accepted', 'flagged', 'rejected'))
);

CREATE INDEX idx_submissions_restaurant ON submissions (restaurant_id);
CREATE INDEX idx_submissions_device ON submissions (device_id);
CREATE INDEX idx_submissions_created ON submissions (created_at DESC);

-- ========================================================================
-- confirmations: 가격 확인 ("이 가격 맞아요" 버튼)
-- ========================================================================
CREATE TABLE confirmations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    menu_item_id    UUID NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    device_id       VARCHAR(128) NOT NULL REFERENCES devices(device_id),
    
    -- 확인 당시 사용자 레벨의 가중치 (레벨 올라가도 소급 적용 안 함)
    weight_applied  INTEGER NOT NULL,
    
    is_agreement    BOOLEAN NOT NULL,                   -- true = "맞아요", false = "다른데요"
    reported_price  INTEGER,                            -- "다른데요"면 새 가격 제보 가능
    
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    -- 한 사용자는 한 메뉴에 대해 1번만 confirm 가능
    CONSTRAINT unique_confirmation UNIQUE (menu_item_id, device_id)
);

CREATE INDEX idx_confirmations_menu ON confirmations (menu_item_id);

-- ========================================================================
-- ratings: 식당에 대한 별점 (Level 3+ 만 가능)
-- ========================================================================
CREATE TABLE ratings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id   UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    device_id       VARCHAR(128) NOT NULL REFERENCES devices(device_id),
    
    score           SMALLINT NOT NULL,                  -- 1 ~ 5
    weight_applied  INTEGER NOT NULL,                   -- rating 당시 사용자 가중치
    comment         TEXT,
    
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT check_rating_score CHECK (score BETWEEN 1 AND 5),
    CONSTRAINT unique_rating UNIQUE (restaurant_id, device_id)
);

CREATE INDEX idx_ratings_restaurant ON ratings (restaurant_id);

-- ========================================================================
-- point_history: 포인트 지급/차감 로그 (감사/디버깅용)
-- ========================================================================
CREATE TABLE point_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id       VARCHAR(128) NOT NULL REFERENCES devices(device_id),
    action          VARCHAR(50) NOT NULL,               -- 'submit_photo', 'confirm', 'rating', 'daily'
    points          INTEGER NOT NULL,                   -- 양수 or 음수
    reference_id    UUID,                               -- 관련 submission/confirmation/rating ID
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_point_history_device ON point_history (device_id, created_at DESC);

-- ========================================================================
-- reports: 사용자 신고 (잘못된 가격/스팸/이상한 메뉴)
-- 어뷰징 방지의 마지막 방어선.
-- ========================================================================
CREATE TABLE reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    menu_item_id    UUID NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    device_id       VARCHAR(128) NOT NULL REFERENCES devices(device_id),
    
    reason          VARCHAR(30) NOT NULL,
    -- 'wrong_price'      : 가격이 틀림
    -- 'not_on_menu'      : 메뉴에 없음
    -- 'spam'             : 스팸
    -- 'inappropriate'    : 부적절한 내용
    -- 'other'            : 기타
    
    comment         TEXT,                            -- 선택적 설명
    
    status          VARCHAR(20) DEFAULT 'pending',
    -- 'pending'    : 접수됨
    -- 'reviewed'   : Legend 유저 또는 관리자가 확인
    -- 'dismissed'  : 무효 처리
    
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,
    
    -- 한 사용자가 같은 메뉴 여러 번 신고 불가
    CONSTRAINT unique_report UNIQUE (menu_item_id, device_id)
);

CREATE INDEX idx_reports_menu ON reports (menu_item_id);
CREATE INDEX idx_reports_status ON reports (status, created_at DESC);

-- 3회 이상 신고되면 자동으로 menu_item을 disputed 상태로 전환
CREATE OR REPLACE FUNCTION auto_dispute_on_reports() RETURNS TRIGGER AS $$
DECLARE
    report_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO report_count 
    FROM reports 
    WHERE menu_item_id = NEW.menu_item_id AND status = 'pending';
    
    IF report_count >= 3 THEN
        UPDATE menu_items 
        SET verification_status = 'disputed'
        WHERE id = NEW.menu_item_id AND verification_status != 'disputed';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auto_dispute
    AFTER INSERT ON reports
    FOR EACH ROW EXECUTE FUNCTION auto_dispute_on_reports();

-- ========================================================================
-- crawl_log: 웹 크롤링 기록 (중복 방지 + 디버깅)
-- ========================================================================
CREATE TABLE crawl_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id   UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    status          VARCHAR(20),                        -- 'success', 'robots_blocked', 'no_menu_found', 'parse_failed'
    items_extracted INTEGER DEFAULT 0,
    error_message   TEXT,
    crawled_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_crawl_log_restaurant ON crawl_log (restaurant_id);

-- ========================================================================
-- 뷰: 지도에 표시할 "식당 + 최저가 메뉴 (없어도 OK)"
-- LEFT JOIN 사용 → 메뉴 없는 식당도 포함됨. menu_status로 구분.
-- ========================================================================
CREATE VIEW restaurants_map_view AS
SELECT
    r.id,
    r.name,
    r.category,
    r.location,
    r.google_rating,
    r.app_rating,
    m.id AS cheapest_menu_id,
    m.name AS cheapest_menu_name,
    m.price_cents AS cheapest_price_cents,
    m.tier AS cheapest_tier,
    m.verification_status AS cheapest_verification_status,
    CASE 
        WHEN m.id IS NULL THEN 'empty'
        WHEN m.verification_status = 'human_verified' THEN 'populated_verified'
        ELSE 'populated_ai'
    END AS menu_status
FROM restaurants r
LEFT JOIN LATERAL (
    SELECT id, name, price_cents, tier, verification_status
    FROM menu_items
    WHERE restaurant_id = r.id AND is_active = TRUE
    ORDER BY price_cents ASC
    LIMIT 1
) m ON TRUE;

-- 이전 이름 호환용 alias (마이그레이션 편의)
CREATE VIEW restaurants_with_cheapest AS
SELECT * FROM restaurants_map_view WHERE menu_status != 'empty';

-- ========================================================================
-- 시드 데이터 예시 (참고용)
-- ========================================================================
-- Phase 1에서 scripts/01_seed_places.py 가 DB를 채움.
-- 이후 scripts/02_crawl_menus.py + 03_parse_with_gemini.py 가 메뉴 데이터를 채움.
--
-- 수동으로 테스트용 데이터 넣으려면:
--
-- INSERT INTO restaurants (google_place_id, name, address, location, category)
-- VALUES (
--     'test_pita_house',
--     'Pita House',
--     '456 Division Ave, Grand Rapids, MI',
--     ST_GeogFromText('POINT(-85.6681 42.9534)'),
--     'mediterranean'
-- );
--
-- INSERT INTO menu_items (
--     restaurant_id, name, price_cents, source, category, verification_status
-- )
-- VALUES (
--     (SELECT id FROM restaurants WHERE google_place_id = 'test_pita_house'),
--     'Hummus pita',
--     450,
--     'seed',
--     'mediterranean',
--     'human_verified'
-- );
--
-- tier는 트리거가 자동 계산 → 'survive'
