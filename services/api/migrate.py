"""Migrate independent catalog and member databases with their owner accounts."""
import subprocess
import sys

for config in ("alembic.ini", "member_alembic.ini", "support_alembic.ini"):
    subprocess.run([sys.executable, "-m", "alembic", "-c", config, "upgrade", "head"], check=True)
