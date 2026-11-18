import os
from sqlalchemy import URL


def url(role, domain="catalog"):
    if domain not in {"catalog", "member", "support"}:
        raise ValueError("unknown database")
    password = os.getenv(domain.upper() + "_PASSWORD") or os.environ[domain.upper() + "_" + role.upper() + "_PASSWORD"]
    return URL.create("postgresql+psycopg", username=f"kkulpick_{domain}_{role}",
                      password=password, host=os.getenv("DB_HOST", "127.0.0.1"),
                      port=int(os.getenv("DB_PORT", "5433")), database=f"kkulpick_{domain}")
