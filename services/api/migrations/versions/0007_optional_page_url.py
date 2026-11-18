"""Capture-only analyses: the page URL is optional browsing context, not a required input."""
from alembic import op
revision='0007_optional_page_url'
down_revision='0006_analysis_metadata'
branch_labels=None
depends_on=None
def upgrade():
    op.execute('ALTER TABLE app.analyses ALTER COLUMN page_url DROP NOT NULL')
def downgrade():
    # URL 없이 접수된 행은 되돌릴 수 없으므로 빈 문자열로 채운 뒤 제약을 복구한다.
    op.execute("UPDATE app.analyses SET page_url='' WHERE page_url IS NULL")
    op.execute('ALTER TABLE app.analyses ALTER COLUMN page_url SET NOT NULL')
