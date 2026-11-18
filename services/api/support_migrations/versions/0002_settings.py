from alembic import op
revision='support_0002'
down_revision='support_0001'
branch_labels=None
depends_on=None
def upgrade():
    op.execute('''CREATE TABLE app.support_settings (
        singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
        days text NOT NULL DEFAULT '월요일 ~ 금요일',
        start_time text NOT NULL DEFAULT '09:00', end_time text NOT NULL DEFAULT '18:00',
        away_message text NOT NULL DEFAULT '운영시간에 순서대로 답변드리겠습니다.',
        version integer NOT NULL DEFAULT 1, updated_at timestamptz NOT NULL DEFAULT now()
    ); INSERT INTO app.support_settings(singleton) VALUES(true)''')
def downgrade():
    op.execute('DROP TABLE app.support_settings')
