from alembic import op
revision='support_0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''
    CREATE TABLE app.conversations (
      conversation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner_id uuid NOT NULL,
      status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','pending_customer','pending_agent','resolved','closed')),
      version integer NOT NULL DEFAULT 1, next_sequence bigint NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX one_open_conversation ON app.conversations(owner_id)
      WHERE status IN ('open','pending_customer','pending_agent');
    CREATE INDEX conversations_owner_page ON app.conversations(owner_id,conversation_id);
    CREATE INDEX conversations_retention ON app.conversations(updated_at) WHERE status IN ('resolved','closed');
    CREATE TABLE app.messages (
      message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      conversation_id uuid NOT NULL REFERENCES app.conversations ON DELETE CASCADE,
      client_message_id uuid NOT NULL, sequence_no bigint NOT NULL,
      sender text NOT NULL CHECK(sender IN ('member','agent')), sender_id uuid NOT NULL,
      body text NOT NULL CHECK(length(btrim(body)) BETWEEN 1 AND 10000), created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(conversation_id,client_message_id), UNIQUE(conversation_id,sequence_no)
    );
    ''')

def downgrade():
    op.execute('DROP TABLE app.messages,app.conversations')
