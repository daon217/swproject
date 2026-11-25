"""Transactional public-catalog embedding outbox and automatic backfill."""
from pathlib import Path
from alembic import op

revision = '0008_embedding_jobs'
down_revision = '0007_optional_page_url'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_name('embedding_jobs.sql').read_text(),
                                  execution_options={'no_parameters': True})


def downgrade():
    op.execute('DROP TRIGGER embedding_content_version ON app.catalog_items')
    op.execute('DROP TRIGGER enqueue_catalog_embedding ON app.catalog_items')
    op.execute('DROP TRIGGER backfill_model_embeddings ON app.embedding_models')
    op.execute('DROP FUNCTION app.embedding_content_version(), app.enqueue_catalog_embedding(), app.backfill_model_embeddings()')
    op.execute('DROP TABLE app.embedding_jobs')
    op.execute('DROP INDEX app.offers_context_url')
