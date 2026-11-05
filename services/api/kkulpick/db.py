import os
from sqlalchemy import URL


def url(role):
    return URL.create("postgresql+psycopg", username=f"kkulpick_catalog_{role}",
                      password=os.environ["CATALOG_PASSWORD"], host=os.getenv("DB_HOST", "127.0.0.1"),
                      port=int(os.getenv("DB_PORT", "5433")), database="kkulpick_catalog")
