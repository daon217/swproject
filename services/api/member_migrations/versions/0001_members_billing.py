"""Member credentials, sessions, profile and provisional subscription billing."""
from pathlib import Path
from alembic import op

revision = "member_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_name("member.sql").read_text(encoding="utf-8"),
                                execution_options={"no_parameters": True})

def downgrade():
    op.execute("DROP TABLE app.payments, app.invoices, app.subscriptions, app.subscription_plans, "
               "app.auth_attempts, app.sessions, app.member_preferences, app.members")
