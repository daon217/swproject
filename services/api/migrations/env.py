from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from kkulpick.db import url

engine = create_engine(url("owner"), poolclass=NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, version_table_schema="app")
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
