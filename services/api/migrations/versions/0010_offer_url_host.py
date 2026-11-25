"""Index the host-case fallback used by recommendation catalog-context matching."""
from alembic import op

revision = '0010_offer_url_host'
down_revision = '0009_catalog_details'
branch_labels = None
depends_on = None

# Must stay textually equivalent to the WHERE expression in
# services/recommendation/http_service.py catalog_context, or the planner cannot use it.
HOST = "lower(substring(current_url from '^[a-zA-Z]+://([^/:?#]+)'))"


def upgrade():
    op.execute(f'CREATE INDEX offers_url_host ON app.offers ({HOST})')


def downgrade():
    op.execute('DROP INDEX app.offers_url_host')
