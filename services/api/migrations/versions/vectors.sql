CREATE TABLE app.embedding_models (
 model_id text PRIMARY KEY CHECK(btrim(model_id)<>''), target text NOT NULL CHECK(target IN ('product','food','ingredient')),
 encoder_name text NOT NULL, revision text NOT NULL, dimensions smallint NOT NULL CHECK(dimensions BETWEEN 1 AND 2000),
 input_template text NOT NULL, query_prefix text NOT NULL, document_prefix text NOT NULL, normalize boolean NOT NULL,
 is_serving boolean NOT NULL DEFAULT false
);
CREATE FUNCTION app.freeze_contract() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-'is_serving') IS DISTINCT FROM (to_jsonb(OLD)-'is_serving') THEN
   RAISE EXCEPTION 'model contract is immutable; register a new id';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_model BEFORE UPDATE ON app.embedding_models FOR EACH ROW EXECUTE FUNCTION app.freeze_contract();
CREATE FUNCTION app.vector_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m app.embedding_models; v bigint;
BEGIN
 SELECT * INTO STRICT m FROM app.embedding_models WHERE model_id=NEW.model_id;
 IF m.target<>TG_ARGV[0] OR m.dimensions<>vector_dims(NEW.embedding) OR NOT (vector_norm(NEW.embedding)>0)
   THEN RAISE EXCEPTION 'invalid vector for model'; END IF;
 IF TG_ARGV[0]='ingredient' THEN
   SELECT content_version INTO STRICT v FROM app.ingredients WHERE ingredient_id=NEW.ingredient_id FOR SHARE;
 ELSE
   SELECT content_version INTO STRICT v FROM app.catalog_items WHERE item_id=(to_jsonb(NEW)->>(TG_ARGV[0]||'_id'))::uuid FOR SHARE;
 END IF;
 IF v<>NEW.content_version THEN RAISE EXCEPTION 'stale content version'; END IF;
 RETURN NEW;
END $$;
DO $$
DECLARE t text; parent text; idcol text;
BEGIN
 FOREACH t IN ARRAY ARRAY['product','food','ingredient'] LOOP
   parent:=CASE t WHEN 'product' THEN 'products' WHEN 'food' THEN 'foods' ELSE 'ingredients' END;
   idcol:=CASE WHEN t='ingredient' THEN 'ingredient_id' ELSE 'item_id' END;
   EXECUTE format('CREATE TABLE app.%I (embedding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
     %I uuid NOT NULL REFERENCES app.%I(%I) ON DELETE CASCADE, model_id text NOT NULL REFERENCES app.embedding_models,
     content_version bigint NOT NULL, embedding vector NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
     UNIQUE(%I,model_id))',t||'_embeddings',t||'_id',parent,idcol,t||'_id');
   EXECUTE format('CREATE TRIGGER verify_vector BEFORE INSERT OR UPDATE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.vector_guard(%L)',t||'_embeddings',t);
 END LOOP;
END $$;
-- Runtime reads model metadata; model registration and index creation belong to migrations/owner.
REVOKE INSERT,UPDATE,DELETE ON app.embedding_models FROM kkulpick_catalog_app;
