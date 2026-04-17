"""initial schema

Revision ID: 07ce2c8a36fd
Revises:
Create Date: 2026-04-17 18:42:14.563641

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "07ce2c8a36fd"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COMPUTE_TIER_FN = """
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
"""

AUTO_VERIFY_FN = """
CREATE OR REPLACE FUNCTION auto_verify_menu() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.confirmation_weight >= 5 AND NEW.verification_status = 'ai_parsed' THEN
        NEW.verification_status = 'human_verified';
        NEW.last_verified_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

COMPUTE_LEVEL_FN = """
CREATE OR REPLACE FUNCTION compute_level() RETURNS TRIGGER AS $$
BEGIN
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
"""

SYNC_LOCATION_FN = """
CREATE OR REPLACE FUNCTION sync_location_from_latlng() RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        NEW.location = ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326)::geography;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

AUTO_DISPUTE_FN = """
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
"""

RESTAURANTS_MAP_VIEW = """
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
"""

RESTAURANTS_WITH_CHEAPEST_VIEW = """
CREATE VIEW restaurants_with_cheapest AS
SELECT * FROM restaurants_map_view WHERE menu_status != 'empty';
"""


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "restaurants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("google_place_id", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column(
            "location",
            geoalchemy2.types.Geography(
                geometry_type="POINT", srid=4326, spatial_index=False
            ),
            nullable=True,
        ),
        sa.Column("lat", sa.Double, nullable=False),
        sa.Column("lng", sa.Double, nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("website", sa.Text, nullable=True),
        sa.Column("google_rating", sa.Numeric(2, 1), nullable=True),
        sa.Column("price_level", sa.SmallInteger, nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("hours_json", postgresql.JSONB, nullable=True),
        sa.Column("app_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("rating_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_restaurants_lat", "restaurants", ["lat"])
    op.create_index("idx_restaurants_lng", "restaurants", ["lng"])
    op.create_index("idx_restaurants_category", "restaurants", ["category"])
    op.execute(
        "CREATE INDEX idx_restaurants_location ON restaurants USING GIST (location)"
    )

    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("display_name", sa.String(50), nullable=True),
        sa.Column("points", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("level", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("level_weight", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "submission_count", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "confirmation_count", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "daily_streak", sa.SmallInteger, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_daily_bonus", sa.Date, nullable=True),
    )
    op.create_index("idx_devices_level", "devices", ["level"])

    op.create_table(
        "menu_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("price_cents", sa.Integer, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("photo_url", sa.Text, nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'ai_parsed'"),
        ),
        sa.Column(
            "confirmation_weight", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "confirmation_count", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tier IN ('survive', 'cost_effective', 'luxury')", name="check_tier"
        ),
        sa.CheckConstraint("price_cents > 0", name="check_price_positive"),
        sa.CheckConstraint("price_cents <= 1500", name="check_price_in_scope"),
        sa.CheckConstraint(
            "source IN ('gemini_web', 'gemini_photo', 'user_manual', 'seed', 'places_api')",
            name="check_source",
        ),
        sa.CheckConstraint(
            "verification_status IN ('ai_parsed', 'human_verified', 'disputed', 'needs_verification')",
            name="check_verification",
        ),
    )
    op.create_index("idx_menu_items_restaurant", "menu_items", ["restaurant_id"])
    op.create_index(
        "idx_menu_items_tier",
        "menu_items",
        ["tier"],
        postgresql_where=sa.text("is_active = TRUE"),
    )
    op.create_index(
        "idx_menu_items_status",
        "menu_items",
        ["verification_status"],
        postgresql_where=sa.text("is_active = TRUE"),
    )
    op.create_index(
        "idx_menu_items_category",
        "menu_items",
        ["category"],
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "submissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurants.id"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(128),
            sa.ForeignKey("devices.device_id"),
            nullable=False,
        ),
        sa.Column("menu_name", sa.String(255), nullable=False),
        sa.Column("price_cents", sa.Integer, nullable=False),
        sa.Column("photo_url", sa.Text, nullable=True),
        sa.Column("gemini_parsed", postgresql.JSONB, nullable=True),
        sa.Column(
            "points_awarded", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_first_submission",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'accepted'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'flagged', 'rejected')",
            name="check_submission_status",
        ),
    )
    op.create_index("idx_submissions_restaurant", "submissions", ["restaurant_id"])
    op.create_index("idx_submissions_device", "submissions", ["device_id"])
    op.execute("CREATE INDEX idx_submissions_created ON submissions (created_at DESC)")

    op.create_table(
        "confirmations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(128),
            sa.ForeignKey("devices.device_id"),
            nullable=False,
        ),
        sa.Column("weight_applied", sa.Integer, nullable=False),
        sa.Column("is_agreement", sa.Boolean, nullable=False),
        sa.Column("reported_price", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("menu_item_id", "device_id", name="unique_confirmation"),
    )
    op.create_index("idx_confirmations_menu", "confirmations", ["menu_item_id"])

    op.create_table(
        "ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(128),
            sa.ForeignKey("devices.device_id"),
            nullable=False,
        ),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("weight_applied", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="check_rating_score"),
        sa.UniqueConstraint("restaurant_id", "device_id", name="unique_rating"),
    )
    op.create_index("idx_ratings_restaurant", "ratings", ["restaurant_id"])

    op.create_table(
        "reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(128),
            sa.ForeignKey("devices.device_id"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("menu_item_id", "device_id", name="unique_report"),
    )
    op.create_index("idx_reports_menu", "reports", ["menu_item_id"])
    op.execute(
        "CREATE INDEX idx_reports_status ON reports (status, created_at DESC)"
    )

    op.create_table(
        "point_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(128),
            sa.ForeignKey("devices.device_id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("points", sa.Integer, nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX idx_point_history_device ON point_history (device_id, created_at DESC)"
    )

    op.create_table(
        "crawl_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column(
            "items_extracted", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "crawled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_crawl_log_restaurant", "crawl_log", ["restaurant_id"])

    # ---- Functions ----
    op.execute(COMPUTE_TIER_FN)
    op.execute(AUTO_VERIFY_FN)
    op.execute(COMPUTE_LEVEL_FN)
    op.execute(SYNC_LOCATION_FN)
    op.execute(AUTO_DISPUTE_FN)

    # ---- Triggers ----
    op.execute(
        "CREATE TRIGGER trigger_compute_tier "
        "BEFORE INSERT OR UPDATE OF price_cents ON menu_items "
        "FOR EACH ROW EXECUTE FUNCTION compute_tier()"
    )
    op.execute(
        "CREATE TRIGGER trigger_auto_verify "
        "BEFORE UPDATE OF confirmation_weight ON menu_items "
        "FOR EACH ROW EXECUTE FUNCTION auto_verify_menu()"
    )
    op.execute(
        "CREATE TRIGGER trigger_compute_level "
        "BEFORE INSERT OR UPDATE OF points ON devices "
        "FOR EACH ROW EXECUTE FUNCTION compute_level()"
    )
    op.execute(
        "CREATE TRIGGER trigger_sync_location "
        "BEFORE INSERT OR UPDATE OF lat, lng ON restaurants "
        "FOR EACH ROW EXECUTE FUNCTION sync_location_from_latlng()"
    )
    op.execute(
        "CREATE TRIGGER trigger_auto_dispute "
        "AFTER INSERT ON reports "
        "FOR EACH ROW EXECUTE FUNCTION auto_dispute_on_reports()"
    )

    # ---- Views ----
    op.execute(RESTAURANTS_MAP_VIEW)
    op.execute(RESTAURANTS_WITH_CHEAPEST_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS restaurants_with_cheapest")
    op.execute("DROP VIEW IF EXISTS restaurants_map_view")

    op.execute("DROP TRIGGER IF EXISTS trigger_auto_dispute ON reports")
    op.execute("DROP TRIGGER IF EXISTS trigger_sync_location ON restaurants")
    op.execute("DROP TRIGGER IF EXISTS trigger_compute_level ON devices")
    op.execute("DROP TRIGGER IF EXISTS trigger_auto_verify ON menu_items")
    op.execute("DROP TRIGGER IF EXISTS trigger_compute_tier ON menu_items")

    op.execute("DROP FUNCTION IF EXISTS auto_dispute_on_reports()")
    op.execute("DROP FUNCTION IF EXISTS sync_location_from_latlng()")
    op.execute("DROP FUNCTION IF EXISTS compute_level()")
    op.execute("DROP FUNCTION IF EXISTS auto_verify_menu()")
    op.execute("DROP FUNCTION IF EXISTS compute_tier()")

    op.drop_table("crawl_log")
    op.drop_table("point_history")
    op.drop_table("reports")
    op.drop_table("ratings")
    op.drop_table("confirmations")
    op.drop_table("submissions")
    op.drop_table("menu_items")
    op.drop_table("devices")
    op.execute("DROP INDEX IF EXISTS idx_restaurants_location")
    op.drop_table("restaurants")

    # Extensions left installed — they may be used by other databases / migrations.
