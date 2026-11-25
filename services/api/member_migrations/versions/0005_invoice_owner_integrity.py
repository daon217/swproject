"""Schema review (2026-11-26): an invoice's user must be its subscription's user.

invoices.user_id repeats subscriptions.user_id (kept on purpose: payment history is read per user
without joining subscriptions). Nothing in the database stopped the two from disagreeing; a composite
foreign key now does. The supporting index also serves the plain subscription foreign key, which had
none (deleting or checking a subscription scanned invoices).
"""
from alembic import op

revision = 'member_0005'
down_revision = 'member_0004'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        ALTER TABLE app.subscriptions ADD CONSTRAINT subscriptions_id_user UNIQUE (subscription_id, user_id);
        CREATE INDEX invoices_by_subscription ON app.invoices (subscription_id, user_id);
        ALTER TABLE app.invoices ADD CONSTRAINT invoices_subscription_owner_fkey
            FOREIGN KEY (subscription_id, user_id) REFERENCES app.subscriptions (subscription_id, user_id) NOT VALID;
        ALTER TABLE app.invoices VALIDATE CONSTRAINT invoices_subscription_owner_fkey;
    ''')


def downgrade():
    op.execute('''
        ALTER TABLE app.invoices DROP CONSTRAINT invoices_subscription_owner_fkey;
        DROP INDEX app.invoices_by_subscription;
        ALTER TABLE app.subscriptions DROP CONSTRAINT subscriptions_id_user;
    ''')
