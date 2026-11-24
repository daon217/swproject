from alembic import op

revision = 'member_0003'
down_revision = 'member_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE TABLE app.admin_identities (
            user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            login_id text NOT NULL,
            password_hash text NOT NULL,
            consent_version text NOT NULL,
            role text CHECK (role IN ('admin', 'support')),
            enabled boolean NOT NULL DEFAULT false,
            auth_version integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (NOT enabled OR role IS NOT NULL)
        );
        CREATE UNIQUE INDEX admin_identities_login_id_lower
            ON app.admin_identities (lower(login_id));

        CREATE TABLE app.admin_sessions (
            token_hash text PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES app.admin_identities ON DELETE CASCADE,
            auth_version integer NOT NULL,
            expires_at timestamptz NOT NULL
        );
        CREATE INDEX admin_sessions_user_id ON app.admin_sessions (user_id);
        CREATE INDEX admin_sessions_expires_at ON app.admin_sessions (expires_at);

        REVOKE INSERT, UPDATE, DELETE ON app.admin_identities FROM kkulpick_member_app;
        GRANT INSERT (login_id, password_hash, consent_version)
            ON app.admin_identities TO kkulpick_member_app;
    ''')


def downgrade():
    op.execute('DROP TABLE app.admin_sessions, app.admin_identities')
