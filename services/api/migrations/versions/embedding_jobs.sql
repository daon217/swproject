-- Only public catalog snapshots belong here. Never OCR, profiles or browsing context.
CREATE TABLE app.embedding_jobs (
 item_id uuid NOT NULL REFERENCES app.catalog_items ON DELETE CASCADE,
 model_id text NOT NULL REFERENCES app.embedding_models ON DELETE CASCADE,
 content_version bigint NOT NULL,
 snapshot jsonb NOT NULL,
 attempts integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT now(),
 lease_token uuid,
 lease_until timestamptz,
 last_error text,
 PRIMARY KEY(item_id,model_id)
);
CREATE INDEX embedding_jobs_ready ON app.embedding_jobs(model_id,available_at);
CREATE INDEX offers_context_url ON app.offers(current_url);

CREATE FUNCTION app.embedding_content_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.name,NEW.description,NEW.kind) IS DISTINCT FROM (OLD.name,OLD.description,OLD.kind) THEN
   NEW.content_version := OLD.content_version + 1;
 ELSIF NEW.content_version < OLD.content_version THEN
   RAISE EXCEPTION 'content version must not decrease';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER embedding_content_version BEFORE UPDATE ON app.catalog_items
 FOR EACH ROW EXECUTE FUNCTION app.embedding_content_version();

CREATE FUNCTION app.enqueue_catalog_embedding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
   IF NEW.content_version=OLD.content_version THEN RETURN NEW; END IF;
 END IF;
 INSERT INTO app.embedding_jobs(item_id,model_id,content_version,snapshot)
 SELECT NEW.item_id,m.model_id,NEW.content_version,
   jsonb_build_object('name',NEW.name,'description',NEW.description,'kind',NEW.kind)
 FROM app.embedding_models m WHERE m.target=NEW.kind AND m.is_serving
 ON CONFLICT(item_id,model_id) DO UPDATE SET content_version=excluded.content_version,
   snapshot=excluded.snapshot,attempts=0,available_at=now(),lease_token=NULL,lease_until=NULL,last_error=NULL;
 RETURN NEW;
END $$;
CREATE TRIGGER enqueue_catalog_embedding AFTER INSERT OR UPDATE ON app.catalog_items
 FOR EACH ROW EXECUTE FUNCTION app.enqueue_catalog_embedding();

CREATE FUNCTION app.backfill_model_embeddings() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT NEW.is_serving OR NEW.target='ingredient' THEN RETURN NEW; END IF;
 -- A newly activated contract indexes every existing item, including demo rows.
 -- Repeated activation does not reset jobs or recompute current vectors.
 EXECUTE format('INSERT INTO app.embedding_jobs(item_id,model_id,content_version,snapshot)
   SELECT i.item_id,$1,i.content_version,jsonb_build_object(''name'',i.name,''description'',i.description,''kind'',i.kind)
   FROM app.catalog_items i WHERE i.kind=$2 AND NOT EXISTS
     (SELECT 1 FROM app.%I e WHERE e.%I=i.item_id AND e.model_id=$1 AND e.content_version=i.content_version)
   ON CONFLICT(item_id,model_id) DO NOTHING',NEW.target||'_embeddings',NEW.target||'_id')
 USING NEW.model_id,NEW.target;
 RETURN NEW;
END $$;
CREATE TRIGGER backfill_model_embeddings AFTER INSERT OR UPDATE OF is_serving ON app.embedding_models
 FOR EACH ROW EXECUTE FUNCTION app.backfill_model_embeddings();

-- Include contracts that were already serving before this migration.
UPDATE app.embedding_models SET is_serving=true WHERE is_serving;
