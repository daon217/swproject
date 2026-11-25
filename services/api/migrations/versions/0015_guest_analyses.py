"""Guest (not signed-in) analyses.

A guest sends a random device key (X-Guest-Key). The API derives a stable owner_id from it,
so owner_id stays NOT NULL and the per-owner quota, idempotency and access checks still apply.
guest=true tells the worker not to look the owner up in the member DB and to use default settings.
"""
from alembic import op

revision = '0015_guest_analyses'
down_revision = '0014_schema_integrity_cleanup'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE app.analyses ADD COLUMN guest boolean NOT NULL DEFAULT false')


def downgrade():
    op.execute('DELETE FROM app.analyses WHERE guest')
    op.execute('ALTER TABLE app.analyses DROP COLUMN guest')
