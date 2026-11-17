"""Indexes for bounded retention and item/URL foreign-key lookups.

Keep applied migrations unchanged. These are normal transactional indexes for
the small local development DB; schedule a maintenance window for large DBs.
"""
from alembic import op

revision = '0005_efficiency'
down_revision = '0004_workflows'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
      CREATE INDEX offers_by_item ON app.offers(item_id);
      CREATE INDEX urls_by_offer ON app.offer_url_history(offer_id);
      CREATE INDEX observations_payload_cleanup ON app.crawl_observations(received_at)
        WHERE normalized_payload<>'{}'::jsonb;
      CREATE INDEX prices_expiry ON app.price_history(observed_at);
      CREATE INDEX changes_expiry ON app.offer_changes(observed_at);
    ''')


def downgrade():
    op.execute('''DROP INDEX app.offers_by_item,app.urls_by_offer,
        app.observations_payload_cleanup,app.prices_expiry,app.changes_expiry''')
