"""Food ingredients/allergen evidence and product matching metadata extensions."""
from pathlib import Path
from alembic import op

revision = '0009_catalog_details'
down_revision = '0008_embedding_jobs'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_name('catalog_details.sql').read_text(encoding='utf-8'),
                                  execution_options={'no_parameters': True})


def downgrade():
    op.execute('DROP TABLE app.listing_extensions')
    op.execute('DROP INDEX app.catalog_items_brand_idx, app.products_gtin_idx, app.products_model_number_idx, app.products_mpn_idx')
    op.execute('ALTER TABLE app.offers DROP COLUMN seller_id, DROP COLUMN seller_name, DROP COLUMN detail_observed_at')
    op.execute('''ALTER TABLE app.foods DROP COLUMN ingredients_raw, DROP COLUMN ingredients,
                  DROP COLUMN allergen_notice_raw, DROP COLUMN cross_contact_raw,
                  DROP COLUMN allergens_declared, DROP COLUMN evidence_status, DROP COLUMN food_observed_at''')
    op.execute('''ALTER TABLE app.products DROP COLUMN model_name, DROP COLUMN model_number,
                  DROP COLUMN mpn, DROP COLUMN gtin, DROP COLUMN identifiers,
                  DROP COLUMN color, DROP COLUMN size, DROP COLUMN options, DROP COLUMN variant_signature''')
    op.execute('''ALTER TABLE app.catalog_items DROP COLUMN brand, DROP COLUMN manufacturer,
                  DROP COLUMN category, DROP COLUMN image_url, DROP COLUMN image_urls''')
