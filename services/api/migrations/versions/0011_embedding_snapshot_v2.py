"""Include brand and category in embedding snapshots and content versioning."""
from pathlib import Path
from alembic import op

revision = '0011_embedding_snapshot_v2'
down_revision = '0010_offer_url_host'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_name('embedding_snapshot_v2.sql').read_text(encoding='utf-8'),
                                  execution_options={'no_parameters': True})


def downgrade():
    # Restore the 0009 trigger bodies (name/description/kind only).
    op.get_bind().exec_driver_sql('''
CREATE OR REPLACE FUNCTION app.embedding_content_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.name,NEW.description,NEW.kind) IS DISTINCT FROM (OLD.name,OLD.description,OLD.kind) THEN
   NEW.content_version := OLD.content_version + 1;
 ELSIF NEW.content_version < OLD.content_version THEN
   RAISE EXCEPTION 'content version must not decrease';
 END IF;
 RETURN NEW;
END $$;
''', execution_options={'no_parameters': True})
    catalog = Path(__file__).with_name('catalog_details.sql').read_text(encoding='utf-8')
    op.get_bind().exec_driver_sql('CREATE OR REPLACE FUNCTION app.enqueue_catalog_embedding()'
                                  + catalog.split('CREATE OR REPLACE FUNCTION app.enqueue_catalog_embedding()', 1)[1],
                                  execution_options={'no_parameters': True})
    jobs = Path(__file__).with_name('embedding_jobs.sql').read_text(encoding='utf-8')
    backfill = jobs.split('CREATE FUNCTION app.backfill_model_embeddings()', 1)[1].split('CREATE TRIGGER', 1)[0]
    op.get_bind().exec_driver_sql('CREATE OR REPLACE FUNCTION app.backfill_model_embeddings()' + backfill,
                                  execution_options={'no_parameters': True})
    op.execute('DROP FUNCTION app.embedding_snapshot(app.catalog_items)')
