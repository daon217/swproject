"""Arrival-driven catalog updates, per-field clocks and change audit."""
from alembic import op

revision = "0002_arrival_updates"
down_revision = "0001_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      ALTER TABLE app.offers
        ADD COLUMN condition_observed_at timestamptz,
        ADD COLUMN description_observed_at timestamptz,
        ADD COLUMN shipping_observed_at timestamptz,
        ADD COLUMN last_changed_at timestamptz;
      UPDATE app.offers SET condition_observed_at=content_observed_at,
        shipping_observed_at=price_observed_at,
        description_observed_at=content_observed_at,
        last_changed_at=greatest(price_observed_at,status_observed_at,url_observed_at,content_observed_at);
      ALTER TABLE app.offers ALTER COLUMN condition_observed_at SET NOT NULL,
        ALTER COLUMN last_changed_at SET NOT NULL, DROP COLUMN fresh_until;
      ALTER TABLE app.crawl_observations ADD COLUMN change_kind text,
        ADD COLUMN changed_fields jsonb NOT NULL DEFAULT '[]'::jsonb;
      CREATE TABLE app.offer_changes (
        change_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        offer_id uuid NOT NULL REFERENCES app.offers,
        observation_id uuid NOT NULL UNIQUE REFERENCES app.crawl_observations,
        observed_at timestamptz NOT NULL,
        before_data jsonb NOT NULL, after_data jsonb NOT NULL
      );
      CREATE INDEX changes_by_offer ON app.offer_changes(offer_id,observed_at);
      CREATE INDEX offers_filter_page ON app.offers(kind,condition,availability,offer_id);
    """)


def downgrade():
    op.execute("""
      DROP INDEX app.offers_filter_page;
      DROP TABLE app.offer_changes;
      ALTER TABLE app.crawl_observations DROP COLUMN change_kind, DROP COLUMN changed_fields;
      ALTER TABLE app.offers ADD COLUMN fresh_until timestamptz;
      UPDATE app.offers SET fresh_until=least(price_observed_at,status_observed_at,url_observed_at)+interval '24 hours';
      ALTER TABLE app.offers ALTER COLUMN fresh_until SET NOT NULL,
        DROP COLUMN condition_observed_at, DROP COLUMN description_observed_at,
        DROP COLUMN shipping_observed_at, DROP COLUMN last_changed_at;
    """)
