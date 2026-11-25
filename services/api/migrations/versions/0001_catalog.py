"""Catalog slice, independent of member/support migration histories."""
from pathlib import Path
from alembic import op

revision = "0001_catalog"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    for name in ("catalog.sql", "vectors.sql"):
        op.get_bind().exec_driver_sql(Path(__file__).with_name(name).read_text(encoding="utf-8"),
                                      execution_options={"no_parameters": True})


def downgrade():
    op.execute("DROP FUNCTION app.vector_guard(), app.freeze_contract(), app.check_item_subtype() CASCADE")
    op.execute("DROP TABLE app.ingredient_embeddings, app.food_embeddings, app.product_embeddings, "
               "app.embedding_models, app.ingredients, app.offer_url_history, app.price_history, "
               "app.crawl_observations, app.crawl_runs, app.offers, app.foods, app.products, app.catalog_items")
