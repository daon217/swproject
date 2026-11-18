from alembic import op
revision='0004_workflows'
down_revision='0003_retention'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''
      CREATE TABLE app.affiliate_offers (
        offer_id uuid PRIMARY KEY REFERENCES app.offers ON DELETE CASCADE,
        partner_name text NOT NULL, affiliate_url text NOT NULL,
        starts_at timestamptz NOT NULL, ends_at timestamptz,
        enabled boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
        updated_by uuid NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
        CHECK(ends_at IS NULL OR ends_at>starts_at)
      );
      CREATE TABLE app.catalog_admin_audit (
        audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), actor_id uuid NOT NULL,
        offer_id uuid NOT NULL, action text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
      );
      REVOKE UPDATE,DELETE ON app.catalog_admin_audit FROM kkulpick_catalog_app;
      CREATE TABLE app.analyses (
        analysis_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner_id uuid NOT NULL,
        request_key text NOT NULL, request_hash text NOT NULL, page_url text NOT NULL,
        page_session_id text NOT NULL, page_revision integer NOT NULL CHECK(page_revision>=0),
        selected_domain text CHECK(selected_domain IN ('product','food')),
        state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','completed','failed','cancelled')),
        attempt integer NOT NULL DEFAULT 0, worker_id text, lease_token uuid, lease_until timestamptz,
        image_id uuid, image_hash text, image_expires_at timestamptz,
        offer_ids uuid[] NOT NULL DEFAULT '{}', error_code text,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        deadline timestamptz NOT NULL DEFAULT now()+interval '10 minutes',
        UNIQUE(owner_id,request_key)
      );
      CREATE INDEX analyses_owner_page ON app.analyses(owner_id,created_at DESC,analysis_id DESC);
      CREATE INDEX analyses_claim ON app.analyses(created_at,analysis_id) WHERE state='queued';
      CREATE INDEX analyses_deadline ON app.analyses(deadline) WHERE state IN ('queued','running');
      CREATE INDEX analyses_lease ON app.analyses(lease_until) WHERE state='running';
      CREATE INDEX analyses_retention ON app.analyses(updated_at);
    ''')

def downgrade():
    op.execute('DROP TABLE app.analyses,app.catalog_admin_audit,app.affiliate_offers')
