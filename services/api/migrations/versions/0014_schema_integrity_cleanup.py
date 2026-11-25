"""Schema review (2026-11-26): enforce run/source consistency, index run cleanup, drop dead columns.

Normalization: crawl_observations.source and listing_extensions.source repeat crawl_runs.source.
The API already rejects a run reused for another source (RUN_SOURCE_CONFLICT); a composite foreign
key now makes the database guarantee it, so a code path that forgets the check cannot store a
contradicting row.

Index: run cleanup (maintenance.py) runs NOT EXISTS on listing_extensions.run_id for every old run,
and deleting a run checks the same column for the foreign key; there was no index for it.

Dead columns (no runtime reader, verified against all services/apps/tools):
- catalog_items.identity_status: never read or written (always the default)
- offers.url_version: only incremented; the URL history table carries URL changes
- analyses.image_expires_at: only written; images expire by file age (images.py)
"""
from alembic import op

revision = '0014_schema_integrity_cleanup'
down_revision = '0013_offer_condition_unknown'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        ALTER TABLE app.crawl_runs ADD CONSTRAINT crawl_runs_run_source UNIQUE (run_id, source);
        ALTER TABLE app.crawl_observations ADD CONSTRAINT crawl_observations_run_source_fkey
            FOREIGN KEY (run_id, source) REFERENCES app.crawl_runs (run_id, source) NOT VALID;
        ALTER TABLE app.crawl_observations VALIDATE CONSTRAINT crawl_observations_run_source_fkey;
        -- run_id is optional for extensions; MATCH SIMPLE skips the check when it is null.
        ALTER TABLE app.listing_extensions ADD CONSTRAINT listing_extensions_run_source_fkey
            FOREIGN KEY (run_id, source) REFERENCES app.crawl_runs (run_id, source) NOT VALID;
        ALTER TABLE app.listing_extensions VALIDATE CONSTRAINT listing_extensions_run_source_fkey;
        CREATE INDEX listing_extensions_by_run ON app.listing_extensions (run_id) WHERE run_id IS NOT NULL;

        ALTER TABLE app.catalog_items DROP COLUMN identity_status;
        ALTER TABLE app.offers DROP COLUMN url_version;
        ALTER TABLE app.analyses DROP COLUMN image_expires_at;
    ''')


def downgrade():
    op.execute('''
        ALTER TABLE app.analyses ADD COLUMN image_expires_at timestamptz;
        ALTER TABLE app.offers ADD COLUMN url_version bigint NOT NULL DEFAULT 1;
        ALTER TABLE app.catalog_items ADD COLUMN identity_status text NOT NULL DEFAULT 'source_only';

        DROP INDEX app.listing_extensions_by_run;
        ALTER TABLE app.listing_extensions DROP CONSTRAINT listing_extensions_run_source_fkey;
        ALTER TABLE app.crawl_observations DROP CONSTRAINT crawl_observations_run_source_fkey;
        ALTER TABLE app.crawl_runs DROP CONSTRAINT crawl_runs_run_source;
    ''')
