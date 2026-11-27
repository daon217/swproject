"""상품 DB에서 쓰이지 않는 테이블·컬럼 정리 (2026-11-27).

지우는 것 — 값이 하나도 없고, 읽는 기능도 없는 것만:
- 테이블: ingredients, ingredient_embeddings (성분 단위 벡터 검색용으로 만들었지만 사용한 적 없음)
- products: gtin, mpn, model_name, model_number, color, size, identifiers, options, variant_signature
  (같은 상품 찾기 API /v2/offers/{id}/matches 전용이었고 그 API를 호출하는 화면·서비스가 없어 함께 제거)
- catalog_items.manufacturer, offers.seller_id, offers.seller_name

products 테이블 자체는 남긴다(상품/식품 구분용 하위 테이블, check_item_subtype 트리거가 사용).
수집기가 위 값을 보내도 API가 받기만 하고 저장하지 않으므로 팀원 수집 코드는 그대로 동작한다.
"""
from alembic import op

revision = '0016_drop_unused_catalog'
down_revision = '0015_guest_analyses'
branch_labels = None
depends_on = None

VECTOR_GUARD = """CREATE OR REPLACE FUNCTION app.vector_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m app.embedding_models; v bigint;
BEGIN
 SELECT * INTO STRICT m FROM app.embedding_models WHERE model_id=NEW.model_id;
 IF m.target<>TG_ARGV[0] OR m.dimensions<>vector_dims(NEW.embedding) OR NOT (vector_norm(NEW.embedding)>0)
   THEN RAISE EXCEPTION 'invalid vector for model'; END IF;
 SELECT content_version INTO STRICT v FROM app.catalog_items WHERE item_id=(to_jsonb(NEW)->>(TG_ARGV[0]||'_id'))::uuid FOR SHARE;
 IF v<>NEW.content_version THEN RAISE EXCEPTION 'stale content version'; END IF;
 RETURN NEW;
END $$"""

BACKFILL = """CREATE OR REPLACE FUNCTION app.backfill_model_embeddings() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT NEW.is_serving THEN RETURN NEW; END IF;
 EXECUTE format('INSERT INTO app.embedding_jobs(item_id,model_id,content_version,snapshot)
   SELECT i.item_id,$1,i.content_version,app.embedding_snapshot(i)
   FROM app.catalog_items i WHERE i.kind=$2 AND NOT EXISTS
     (SELECT 1 FROM app.%I e WHERE e.%I=i.item_id AND e.model_id=$1 AND e.content_version=i.content_version)
   ON CONFLICT(item_id,model_id) DO NOTHING',NEW.target||'_embeddings',NEW.target||'_id')
 USING NEW.model_id,NEW.target;
 RETURN NEW;
END $$"""

PRODUCT_COLUMNS = ('gtin', 'mpn', 'model_name', 'model_number', 'color', 'size', 'identifiers', 'options',
                   'variant_signature')


def upgrade():
    op.execute(VECTOR_GUARD)
    op.execute(BACKFILL)
    op.execute("DELETE FROM app.embedding_models WHERE target='ingredient'")
    op.execute('ALTER TABLE app.embedding_models DROP CONSTRAINT embedding_models_target_check')
    op.execute("ALTER TABLE app.embedding_models ADD CONSTRAINT embedding_models_target_check CHECK (target IN ('product','food'))")
    op.execute('DROP TABLE app.ingredient_embeddings')
    op.execute('DROP TABLE app.ingredients')
    op.execute('DROP INDEX IF EXISTS app.products_gtin_idx, app.products_mpn_idx, app.products_model_number_idx')
    op.execute('ALTER TABLE app.products ' + ', '.join(f'DROP COLUMN {c}' for c in PRODUCT_COLUMNS))
    op.execute('ALTER TABLE app.catalog_items DROP COLUMN manufacturer')
    op.execute('ALTER TABLE app.offers DROP COLUMN seller_id, DROP COLUMN seller_name')


def downgrade():
    # 컬럼·테이블 구조만 되돌린다(지운 값은 원래 비어 있었다).
    op.execute('ALTER TABLE app.offers ADD COLUMN seller_id text, ADD COLUMN seller_name text')
    op.execute('ALTER TABLE app.catalog_items ADD COLUMN manufacturer text')
    op.execute("""ALTER TABLE app.products ADD COLUMN model_name text, ADD COLUMN model_number text, ADD COLUMN mpn text,
        ADD COLUMN gtin text, ADD COLUMN identifiers jsonb NOT NULL DEFAULT '[]', ADD COLUMN color text, ADD COLUMN size text,
        ADD COLUMN options jsonb NOT NULL DEFAULT '{}', ADD COLUMN variant_signature text""")
    op.execute('CREATE INDEX products_gtin_idx ON app.products (gtin) WHERE gtin IS NOT NULL')
    op.execute('CREATE INDEX products_mpn_idx ON app.products (lower(mpn)) WHERE mpn IS NOT NULL')
    op.execute('CREATE INDEX products_model_number_idx ON app.products (lower(model_number)) WHERE model_number IS NOT NULL')
    op.execute("""CREATE TABLE app.ingredients (ingredient_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE,
        canonical_name text NOT NULL, content_version bigint NOT NULL DEFAULT 1 CHECK(content_version>0))""")
    # ingredient_embeddings는 0001 vectors.sql의 생성 블록과 같은 모양으로 만든다.
    op.execute("""CREATE TABLE app.ingredient_embeddings (embedding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        ingredient_id uuid NOT NULL REFERENCES app.ingredients(ingredient_id) ON DELETE CASCADE,
        model_id text NOT NULL REFERENCES app.embedding_models(model_id), content_version bigint NOT NULL,
        embedding vector NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(ingredient_id, model_id))""")
    op.execute('ALTER TABLE app.embedding_models DROP CONSTRAINT embedding_models_target_check')
    op.execute("ALTER TABLE app.embedding_models ADD CONSTRAINT embedding_models_target_check CHECK (target IN ('product','food','ingredient'))")
