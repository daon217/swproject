"""Member settings: overseas offers on/off, body sizes (height, weight, foot), premium benefit copy.

- include_overseas: 해외 판매처(원화가 아닌 가격) 상품을 추천에 넣을지. 기존 동작을 유지하도록 기본값은 켜짐.
- height_cm / weight_kg / foot_mm: 회원가입·개인정보 수정에서 받는 선택 항목. 비우면 NULL.
- 프리미엄 혜택 문구: AI 추천 상품 5개(무료 회원은 3개).
"""
from alembic import op

revision = 'member_0006'
down_revision = 'member_0005'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        ALTER TABLE app.members
            ADD COLUMN include_overseas boolean NOT NULL DEFAULT true,
            ADD COLUMN height_cm numeric(4,1) CHECK (height_cm BETWEEN 50 AND 250),
            ADD COLUMN weight_kg numeric(4,1) CHECK (weight_kg BETWEEN 10 AND 300),
            ADD COLUMN foot_mm smallint CHECK (foot_mm BETWEEN 150 AND 350);

        UPDATE app.subscription_plans
            SET benefits = '["AI 추천 상품 5개 보기","기피·선호 재료로 식품 필터","내 취향에 맞는 후보 비교"]'
            WHERE plan_id = 'premium-monthly';
    ''')


def downgrade():
    op.execute('''
        UPDATE app.subscription_plans
            SET benefits = '["AI 추천 상품 3개 전체 보기","기피·선호 재료로 식품 필터","내 취향에 맞는 후보 비교"]'
            WHERE plan_id = 'premium-monthly';

        ALTER TABLE app.members
            DROP COLUMN foot_mm,
            DROP COLUMN weight_kg,
            DROP COLUMN height_cm,
            DROP COLUMN include_overseas;
    ''')
