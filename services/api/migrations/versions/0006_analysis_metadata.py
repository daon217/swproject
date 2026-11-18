"""Preserve extracted ingredient evidence and recommendation explanations."""
from alembic import op
revision='0006_analysis_metadata'
down_revision='0005_efficiency'
branch_labels=None
depends_on=None
def upgrade():
    op.execute("ALTER TABLE app.analyses ADD COLUMN result_metadata jsonb NOT NULL DEFAULT '{}'::jsonb")
def downgrade():
    op.execute('ALTER TABLE app.analyses DROP COLUMN result_metadata')
