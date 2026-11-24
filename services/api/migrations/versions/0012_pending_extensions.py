"""Hold listing extensions that arrive before the offer's first observation."""
from alembic import op

revision = '0012_pending_extensions'
down_revision = '0011_embedding_snapshot_v2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        ALTER TABLE app.listing_extensions
          ADD COLUMN source_listing_id text,
          ADD COLUMN variant_key text;
        UPDATE app.listing_extensions SET source_listing_id=normalized_payload->>'source_listing_id',
          variant_key=coalesce(normalized_payload->>'variant_key','default');
        CREATE INDEX listing_extensions_pending
          ON app.listing_extensions(source, source_listing_id, variant_key, observed_at)
          WHERE state='pending';
    ''')


def downgrade():
    op.execute('''
        DROP INDEX app.listing_extensions_pending;
        ALTER TABLE app.listing_extensions DROP COLUMN source_listing_id, DROP COLUMN variant_key;
    ''')
