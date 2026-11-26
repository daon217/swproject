"""Admin signup requests can be rejected, and stale requests are cleaned up (devlog #60).

Both run as SECURITY DEFINER functions like approve_admin_signup (member_0004): the API role cannot
change admin_identities directly. Only pending requests (role IS NULL AND NOT enabled) are touched.
"""
from alembic import op

revision = 'member_0007'
down_revision = 'member_0006'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE FUNCTION app.reject_admin_signup(reviewer_hash text, target_id uuid)
            RETURNS text
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog
            AS $$
            DECLARE reviewer_id uuid;
            BEGIN
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

                DELETE FROM app.admin_identities
                WHERE user_id = target_id AND role IS NULL AND NOT enabled;
                IF NOT FOUND THEN
                    IF EXISTS (SELECT 1 FROM app.admin_identities WHERE user_id = target_id) THEN
                        RETURN 'not_pending';
                    END IF;
                    RETURN 'missing';
                END IF;

                INSERT INTO app.admin_audit(actor_id, target_id, action) VALUES (reviewer_id, target_id, 'reject');
                RETURN 'rejected';
            END;
            $$;
        REVOKE ALL ON FUNCTION app.reject_admin_signup(text, uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app.reject_admin_signup(text, uuid) TO kkulpick_member_app;

        CREATE FUNCTION app.purge_stale_admin_signups(max_age_days int, batch int)
            RETURNS int
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = pg_catalog
            AS $$
            WITH gone AS (
                DELETE FROM app.admin_identities WHERE user_id IN (
                    SELECT user_id FROM app.admin_identities
                    WHERE role IS NULL AND NOT enabled
                        AND created_at < now() - make_interval(days => greatest(max_age_days, 1))
                    LIMIT greatest(batch, 1))
                RETURNING 1)
            SELECT count(*)::int FROM gone
            $$;
        REVOKE ALL ON FUNCTION app.purge_stale_admin_signups(int, int) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app.purge_stale_admin_signups(int, int) TO kkulpick_member_app;
    ''')


def downgrade():
    op.execute('DROP FUNCTION app.purge_stale_admin_signups(int, int)')
    op.execute('DROP FUNCTION app.reject_admin_signup(text, uuid)')
