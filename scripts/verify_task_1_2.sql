-- Task 1.2 verification script — run against a fresh broken_lunch DB
-- Exits with row-level output that should be inspected by a human.

BEGIN;

-- Clean up any prior verification run
DELETE FROM reports      WHERE device_id = 'dev_verify';
DELETE FROM confirmations WHERE device_id = 'dev_verify';
DELETE FROM ratings      WHERE device_id = 'dev_verify';
DELETE FROM submissions  WHERE device_id = 'dev_verify';
DELETE FROM menu_items   WHERE restaurant_id IN (SELECT id FROM restaurants WHERE google_place_id LIKE 'verify_%');
DELETE FROM restaurants  WHERE google_place_id LIKE 'verify_%';
DELETE FROM devices      WHERE device_id = 'dev_verify';

-- =======================================================================
-- 1. Restaurant insert with lat/lng -> location auto-populated (sync_location trigger)
-- =======================================================================
INSERT INTO restaurants (google_place_id, name, lat, lng, category)
VALUES ('verify_pita', 'Pita House', 42.9534, -85.6681, 'mediterranean');

SELECT '1_location_filled' AS test,
       CASE WHEN location IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS result,
       ST_AsText(location::geometry) AS location_text
FROM restaurants WHERE google_place_id = 'verify_pita';

-- =======================================================================
-- 2. Menu items: tier auto-computed by compute_tier trigger
-- =======================================================================
INSERT INTO menu_items (restaurant_id, name, price_cents, source)
VALUES (
    (SELECT id FROM restaurants WHERE google_place_id = 'verify_pita'),
    'Hummus pita', 450, 'seed'
);
INSERT INTO menu_items (restaurant_id, name, price_cents, source)
VALUES (
    (SELECT id FROM restaurants WHERE google_place_id = 'verify_pita'),
    'Shawarma plate', 950, 'seed'
);
INSERT INTO menu_items (restaurant_id, name, price_cents, source)
VALUES (
    (SELECT id FROM restaurants WHERE google_place_id = 'verify_pita'),
    'Mixed grill', 1400, 'seed'
);

SELECT '2_tier_autocomputed' AS test,
       name, price_cents, tier,
       CASE
           WHEN price_cents = 450  AND tier = 'survive'         THEN 'PASS'
           WHEN price_cents = 950  AND tier = 'cost_effective'  THEN 'PASS'
           WHEN price_cents = 1400 AND tier = 'luxury'          THEN 'PASS'
           ELSE 'FAIL'
       END AS result
FROM menu_items
WHERE restaurant_id = (SELECT id FROM restaurants WHERE google_place_id = 'verify_pita')
ORDER BY price_cents;

-- =======================================================================
-- 3. Device level auto-computed by compute_level trigger
-- =======================================================================
INSERT INTO devices (device_id, points) VALUES ('dev_verify', 500);
SELECT '3_level_autocomputed' AS test,
       points, level, level_weight,
       CASE WHEN level = 4 AND level_weight = 2 THEN 'PASS' ELSE 'FAIL' END AS result
FROM devices WHERE device_id = 'dev_verify';

UPDATE devices SET points = 15000 WHERE device_id = 'dev_verify';
SELECT '3b_level_updates'  AS test,
       points, level, level_weight,
       CASE WHEN level = 10 AND level_weight = 10 THEN 'PASS' ELSE 'FAIL' END AS result
FROM devices WHERE device_id = 'dev_verify';

-- =======================================================================
-- 4. auto_verify_menu: confirmation_weight >= 5 flips ai_parsed -> human_verified
-- =======================================================================
UPDATE menu_items SET confirmation_weight = 6
WHERE restaurant_id = (SELECT id FROM restaurants WHERE google_place_id = 'verify_pita')
  AND price_cents = 450;
SELECT '4_auto_verify' AS test,
       name, verification_status,
       CASE WHEN verification_status = 'human_verified' THEN 'PASS' ELSE 'FAIL' END AS result
FROM menu_items
WHERE restaurant_id = (SELECT id FROM restaurants WHERE google_place_id = 'verify_pita')
  AND price_cents = 450;

-- =======================================================================
-- 5. auto_dispute_on_reports: 3 pending reports -> verification_status='disputed'
-- =======================================================================
INSERT INTO devices (device_id) VALUES
  ('dev_verify_r1'), ('dev_verify_r2'), ('dev_verify_r3')
ON CONFLICT DO NOTHING;

INSERT INTO reports (menu_item_id, device_id, reason) VALUES
  ((SELECT id FROM menu_items WHERE name='Shawarma plate' AND restaurant_id=(SELECT id FROM restaurants WHERE google_place_id='verify_pita')), 'dev_verify_r1', 'wrong_price'),
  ((SELECT id FROM menu_items WHERE name='Shawarma plate' AND restaurant_id=(SELECT id FROM restaurants WHERE google_place_id='verify_pita')), 'dev_verify_r2', 'wrong_price'),
  ((SELECT id FROM menu_items WHERE name='Shawarma plate' AND restaurant_id=(SELECT id FROM restaurants WHERE google_place_id='verify_pita')), 'dev_verify_r3', 'wrong_price');

SELECT '5_auto_dispute' AS test,
       name, verification_status,
       CASE WHEN verification_status = 'disputed' THEN 'PASS' ELSE 'FAIL' END AS result
FROM menu_items WHERE name = 'Shawarma plate'
  AND restaurant_id = (SELECT id FROM restaurants WHERE google_place_id = 'verify_pita');

-- =======================================================================
-- 6. restaurants_map_view returns empty restaurants with menu_status='empty'
-- =======================================================================
INSERT INTO restaurants (google_place_id, name, lat, lng) VALUES ('verify_empty', 'Empty Cafe', 42.96, -85.67);
SELECT '6_map_view_empty' AS test,
       name, menu_status,
       CASE WHEN menu_status = 'empty' THEN 'PASS' ELSE 'FAIL' END AS result
FROM restaurants_map_view WHERE name = 'Empty Cafe';

-- Populated restaurant should show cheapest menu + populated_verified or populated_ai
SELECT '6b_map_view_populated' AS test,
       name, menu_status, cheapest_menu_name, cheapest_price_cents, cheapest_tier,
       CASE WHEN menu_status IN ('populated_ai', 'populated_verified') AND cheapest_price_cents = 450 THEN 'PASS' ELSE 'FAIL' END AS result
FROM restaurants_map_view WHERE name = 'Pita House';

ROLLBACK;
