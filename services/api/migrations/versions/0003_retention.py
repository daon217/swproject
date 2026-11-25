"""Bounded retention and minimal deletion markers to prevent stale resurrection."""
from alembic import op

revision = '0003_retention'
down_revision = '0002_arrival_updates'
branch_labels = None
depends_on = None

def upgrade():
    op.execute('''
        CREATE TABLE app.offer_tombstones (
            source text NOT NULL, source_listing_id text NOT NULL, variant_key text NOT NULL,
            observed_at timestamptz NOT NULL, deleted_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(source,source_listing_id,variant_key)
        );
        CREATE INDEX tombstones_expiry ON app.offer_tombstones(deleted_at);
        CREATE INDEX offers_cleanup ON app.offers(status_observed_at,offer_id)
            WHERE availability IN ('out_of_stock','ended');
        CREATE INDEX offers_source_filter_page ON app.offers(kind,source,condition,availability,offer_id);
        CREATE INDEX observations_retention ON app.crawl_observations(received_at,observation_id);
        CREATE INDEX observations_offer ON app.crawl_observations(offer_id);
        CREATE INDEX observations_run ON app.crawl_observations(run_id);
        CREATE INDEX observations_time ON app.crawl_observations(observed_at);
        CREATE INDEX closed_urls_expiry ON app.offer_url_history(valid_to) WHERE valid_to IS NOT NULL;
    ''')

def downgrade():
    op.execute('''DROP TABLE app.offer_tombstones;
      DROP INDEX app.offers_source_filter_page,app.offers_cleanup,app.observations_retention,app.observations_offer,
                 app.observations_run,app.observations_time,app.closed_urls_expiry;''')
