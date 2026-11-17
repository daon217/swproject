from alembic import op
revision='member_0002'
down_revision='member_0001'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''
      ALTER TABLE app.members ADD COLUMN deleted_at timestamptz;
      CREATE TABLE app.admin_accounts (
        user_id uuid PRIMARY KEY REFERENCES app.members,
        role text NOT NULL CHECK(role IN ('admin','support')), enabled boolean NOT NULL DEFAULT true,
        updated_at timestamptz NOT NULL DEFAULT now()
      );
      CREATE TABLE app.admin_audit (
        audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), actor_id uuid, target_id uuid NOT NULL,
        action text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
      );
      REVOKE INSERT,UPDATE,DELETE ON app.admin_accounts FROM kkulpick_member_app;
      REVOKE UPDATE,DELETE ON app.admin_audit FROM kkulpick_member_app;
      CREATE TABLE app.account_deletions (
        request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL UNIQUE REFERENCES app.members,
        state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','completed')),
        created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
      );
    ''')

def downgrade():
    op.execute('DROP TABLE app.account_deletions,app.admin_audit,app.admin_accounts; ALTER TABLE app.members DROP COLUMN deleted_at')
