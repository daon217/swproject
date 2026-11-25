"""Allow condition='unknown' for listings whose shop does not state new/used.

General shopping malls often do not label a listing as new or used. Storing such a listing as
'new' (the old default) claims something the source never said; 'unknown' keeps that honest.
Used food stays forbidden by the separate table check (condition <> 'used' OR kind = 'product').
"""
from alembic import op

revision = '0013_offer_condition_unknown'
down_revision = '0012_pending_extensions'
branch_labels = None
depends_on = None

# The column check was declared inline in catalog.sql, so PostgreSQL named it offers_condition_check.
# Look it up by definition instead of trusting the generated name.
_DROP_OLD = '''
DO $$
DECLARE c text;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint
           WHERE conrelid = 'app.offers'::regclass AND contype = 'c'
             AND pg_get_constraintdef(oid) LIKE '%condition = ANY%'
             AND pg_get_constraintdef(oid) NOT LIKE '%kind%'
  LOOP
    EXECUTE format('ALTER TABLE app.offers DROP CONSTRAINT %I', c);
  END LOOP;
END $$;
'''


def upgrade():
    op.execute(_DROP_OLD)
    op.execute("ALTER TABLE app.offers ADD CONSTRAINT offers_condition_check "
               "CHECK (condition IN ('new','used','unknown'))")


def downgrade():
    # Rows that were recorded as unknown cannot be proven new or used; refuse instead of guessing.
    op.execute('''
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM app.offers WHERE condition = 'unknown') THEN
            RAISE EXCEPTION 'offers with condition=unknown exist; resolve them before downgrading';
          END IF;
        END $$;
    ''')
    op.execute(_DROP_OLD)
    op.execute("ALTER TABLE app.offers ADD CONSTRAINT offers_condition_check CHECK (condition IN ('new','used'))")
