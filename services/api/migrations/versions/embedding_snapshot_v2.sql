-- Brand and category feed the embedding text (catalog-v2 contract). A change to either now
-- bumps content_version, which re-queues the item; price/stock-only changes still do not.
CREATE OR REPLACE FUNCTION app.embedding_content_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.name,NEW.description,NEW.kind,NEW.brand,NEW.category)
    IS DISTINCT FROM (OLD.name,OLD.description,OLD.kind,OLD.brand,OLD.category) THEN
   NEW.content_version := OLD.content_version + 1;
 ELSIF NEW.content_version < OLD.content_version THEN
   RAISE EXCEPTION 'content version must not decrease';
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION app.embedding_snapshot(i app.catalog_items) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
 SELECT jsonb_strip_nulls(jsonb_build_object('name',i.name,'description',i.description,'kind',i.kind,
                                             'brand',i.brand,'category',i.category))
$$;

CREATE OR REPLACE FUNCTION app.enqueue_catalog_embedding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
   IF NEW.kind IS DISTINCT FROM OLD.kind THEN
     DELETE FROM app.embedding_jobs j
       USING app.embedding_models m
       WHERE j.item_id = NEW.item_id AND j.model_id = m.model_id AND m.target <> NEW.kind;
   END IF;
   IF NEW.content_version=OLD.content_version THEN RETURN NEW; END IF;
 END IF;
 INSERT INTO app.embedding_jobs(item_id,model_id,content_version,snapshot)
 SELECT NEW.item_id,m.model_id,NEW.content_version,app.embedding_snapshot(NEW)
 FROM app.embedding_models m WHERE m.target=NEW.kind AND m.is_serving
 ON CONFLICT(item_id,model_id) DO UPDATE SET content_version=excluded.content_version,
   snapshot=excluded.snapshot,attempts=0,available_at=now(),lease_token=NULL,lease_until=NULL,last_error=NULL;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION app.backfill_model_embeddings() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT NEW.is_serving OR NEW.target='ingredient' THEN RETURN NEW; END IF;
 EXECUTE format('INSERT INTO app.embedding_jobs(item_id,model_id,content_version,snapshot)
   SELECT i.item_id,$1,i.content_version,app.embedding_snapshot(i)
   FROM app.catalog_items i WHERE i.kind=$2 AND NOT EXISTS
     (SELECT 1 FROM app.%I e WHERE e.%I=i.item_id AND e.model_id=$1 AND e.content_version=i.content_version)
   ON CONFLICT(item_id,model_id) DO NOTHING',NEW.target||'_embeddings',NEW.target||'_id')
 USING NEW.model_id,NEW.target;
 RETURN NEW;
END $$;
