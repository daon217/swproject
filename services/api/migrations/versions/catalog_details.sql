ALTER TABLE app.catalog_items
  ADD COLUMN brand text,
  ADD COLUMN manufacturer text,
  ADD COLUMN category text,
  ADD COLUMN image_url text,
  ADD COLUMN image_urls jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE app.products
  ADD COLUMN model_name text,
  ADD COLUMN model_number text,
  ADD COLUMN mpn text,
  ADD COLUMN gtin text,
  ADD COLUMN identifiers jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN color text,
  ADD COLUMN size text,
  ADD COLUMN options jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN variant_signature text;

ALTER TABLE app.foods
  ADD COLUMN ingredients_raw text,
  ADD COLUMN ingredients jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN allergen_notice_raw text,
  ADD COLUMN cross_contact_raw text,
  ADD COLUMN allergens_declared jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN evidence_status text NOT NULL DEFAULT 'not_reported'
    CHECK (evidence_status IN ('not_reported','reported','negative_claim_unverified','conflicting','image_only','ocr_unverified')),
  ADD COLUMN food_observed_at timestamptz;

ALTER TABLE app.offers
  ADD COLUMN seller_id text,
  ADD COLUMN seller_name text,
  ADD COLUMN detail_observed_at timestamptz;

CREATE INDEX catalog_items_brand_idx ON app.catalog_items(lower(brand)) WHERE brand IS NOT NULL;
CREATE INDEX products_gtin_idx ON app.products(gtin) WHERE gtin IS NOT NULL;
CREATE INDEX products_model_number_idx ON app.products(lower(model_number)) WHERE model_number IS NOT NULL;
CREATE INDEX products_mpn_idx ON app.products(lower(mpn)) WHERE mpn IS NOT NULL;

CREATE TABLE app.listing_extensions (
  extension_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid REFERENCES app.crawl_runs,
  source text NOT NULL,
  observation_key text NOT NULL,
  offer_id uuid REFERENCES app.offers ON DELETE CASCADE,
  schema_version text NOT NULL,
  payload_hash text NOT NULL,
  observed_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  normalized_payload jsonb NOT NULL,
  state text NOT NULL,
  error_code text,
  change_kind text NOT NULL,
  changed_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  before_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(source, observation_key)
);
CREATE INDEX listing_extensions_offer_idx ON app.listing_extensions(offer_id, observed_at);
