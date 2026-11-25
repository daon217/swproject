"""Allow active administrators to approve pending staff signup requests."""
from alembic import op

revision = 'member_0004'
down_revision = 'member_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE INDEX admin_identities_pending ON app.admin_identities (created_at, user_id)
            WHERE role IS NULL AND NOT enabled;

        CREATE FUNCTION app.approve_admin_signup(reviewer_hash text, target_id uuid, approved_role text)
            RETURNS text
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog
            AS $$
            DECLARE reviewer_id uuid;
            BEGIN
                IF approved_role IS NULL OR approved_role NOT IN ('admin', 'support') THEN
                    RETURN 'invalid_role';
                END IF;

                SELECT s.user_id INTO reviewer_id
                FROM app.admin_sessions s JOIN app.admin_identities a USING (user_id)
                WHERE s.token_hash = reviewer_hash AND s.expires_at > now()
                    AND s.auth_version = a.auth_version AND a.enabled AND a.role = 'admin';
                IF reviewer_id IS NULL THEN
                    SELECT s.user_id INTO reviewer_id
                    FROM app.sessions s JOIN app.members m USING (user_id)
                    JOIN app.admin_accounts a USING (user_id)
                    WHERE s.token_hash = reviewer_hash AND s.expires_at > now()
                        AND m.deleted_at IS NULL AND a.enabled AND a.role = 'admin';
                END IF;
                IF reviewer_id IS NULL THEN
                    RETURN 'forbidden';
                END IF;

                UPDATE app.admin_identities AS applicant
                SET role = approved_role, enabled = true, auth_version = applicant.auth_version + 1
                WHERE applicant.user_id = target_id AND applicant.role IS NULL AND NOT applicant.enabled;
                IF NOT FOUND THEN
                    IF EXISTS (SELECT 1 FROM app.admin_identities WHERE user_id = target_id) THEN
                        RETURN 'not_pending';
                    END IF;
                    RETURN 'missing';
                END IF;

                INSERT INTO app.admin_audit(actor_id, target_id, action)
                VALUES (reviewer_id, target_id, 'approve:' || approved_role);
                RETURN 'approved';
            END;
            $$;
        REVOKE ALL ON FUNCTION app.approve_admin_signup(text, uuid, text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app.approve_admin_signup(text, uuid, text) TO kkulpick_member_app;
    ''')


def downgrade():
    op.execute('DROP FUNCTION app.approve_admin_signup(text, uuid, text)')
    op.execute('DROP INDEX app.admin_identities_pending')
