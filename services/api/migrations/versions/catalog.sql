CREATE TABLE app.catalog_items (
 item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind text NOT NULL CHECK(kind IN ('product','food')),
 name text NOT NULL, description text, content_version bigint NOT NULL DEFAULT 1 CHECK(content_version>0),
 identity_status text NOT NULL DEFAULT 'source_only', UNIQUE(item_id,kind)
);
CREATE TABLE app.products (item_id uuid PRIMARY KEY REFERENCES app.catalog_items ON DELETE CASCADE);
CREATE TABLE app.foods (item_id uuid PRIMARY KEY REFERENCES app.catalog_items ON DELETE CASCADE);
-- At commit, the item has exactly one subtype, matching its parent's kind.
CREATE FUNCTION app.check_item_subtype() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ident uuid; k text; product_exists boolean; food_exists boolean;
BEGIN
 IF TG_OP='UPDATE' AND OLD.item_id<>NEW.item_id THEN RAISE EXCEPTION 'immutable item id'; END IF;
 ident:=CASE WHEN TG_OP='DELETE' THEN OLD.item_id ELSE NEW.item_id END;
 SELECT kind INTO k FROM app.catalog_items WHERE item_id=ident FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT EXISTS(SELECT 1 FROM app.products WHERE item_id=ident), EXISTS(SELECT 1 FROM app.foods WHERE item_id=ident)
   INTO product_exists,food_exists;
 IF product_exists<>(k='product') OR food_exists<>(k='food') THEN RAISE EXCEPTION 'item subtype mismatch'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER verify_item AFTER INSERT OR UPDATE ON app.catalog_items
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_item_subtype();
CREATE CONSTRAINT TRIGGER verify_product AFTER INSERT OR UPDATE OR DELETE ON app.products
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_item_subtype();
CREATE CONSTRAINT TRIGGER verify_food AFTER INSERT OR UPDATE OR DELETE ON app.foods
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_item_subtype();
CREATE TABLE app.ingredients (ingredient_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE,
 canonical_name text NOT NULL, content_version bigint NOT NULL DEFAULT 1 CHECK(content_version>0));
CREATE TABLE app.offers (
 offer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), item_id uuid NOT NULL, kind text NOT NULL,
 FOREIGN KEY(item_id,kind) REFERENCES app.catalog_items(item_id,kind),
 source text NOT NULL, source_listing_id text NOT NULL, variant_key text NOT NULL,
 condition text NOT NULL CHECK(condition IN ('new','used')), CHECK(condition <> 'used' OR kind='product'),
 price numeric(20,4) NOT NULL CHECK(price>=0), currency varchar(3) NOT NULL,
 shipping_fee numeric(20,4) CHECK(shipping_fee>=0), current_url text NOT NULL, url_version bigint NOT NULL DEFAULT 1,
 availability text NOT NULL CHECK(availability IN ('available','out_of_stock','ended','suspect')),
 price_observed_at timestamptz NOT NULL, status_observed_at timestamptz NOT NULL,
 url_observed_at timestamptz NOT NULL, content_observed_at timestamptz NOT NULL,
 last_seen_at timestamptz NOT NULL, last_checked_at timestamptz NOT NULL, fresh_until timestamptz NOT NULL,
 UNIQUE(source,source_listing_id,variant_key)
);
CREATE INDEX offers_page ON app.offers(kind,offer_id);
CREATE TABLE app.crawl_runs(run_id uuid PRIMARY KEY, source text NOT NULL, started_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE app.crawl_observations(
 observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES app.crawl_runs,
 source text NOT NULL, observation_key text NOT NULL, payload_hash text NOT NULL, observed_at timestamptz NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now(), normalized_payload jsonb NOT NULL,
 state text NOT NULL, error_code text, offer_id uuid REFERENCES app.offers, UNIQUE(source,observation_key)
);
CREATE TABLE app.price_history(price_history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), offer_id uuid NOT NULL REFERENCES app.offers,
 observation_id uuid NOT NULL UNIQUE REFERENCES app.crawl_observations, price numeric(20,4) NOT NULL,
 currency varchar(3) NOT NULL, shipping_fee numeric(20,4), observed_at timestamptz NOT NULL);
CREATE INDEX price_by_offer ON app.price_history(offer_id,observed_at);
CREATE TABLE app.offer_url_history(url_history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), offer_id uuid NOT NULL REFERENCES app.offers,
 url text NOT NULL, valid_from timestamptz NOT NULL, valid_to timestamptz, CHECK(valid_to IS NULL OR valid_to>valid_from));
CREATE UNIQUE INDEX one_active_url ON app.offer_url_history(offer_id) WHERE valid_to IS NULL;
