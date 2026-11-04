"""Local DB commands (Python 3.10+, Docker Compose v2). No Python dependencies."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ENV = HERE / ".env"
DOMAINS = ("member", "catalog", "support")


def initialize():
    if ENV.exists():
        print("Existing infra/db/.env preserved; passwords were not changed.")
        return
    values = {"DB_PORT": "5433", "POSTGRES_PASSWORD": secrets.token_hex(24)}
    for domain in DOMAINS:
        for role in ("OWNER", "APP"):
            values[f"{domain.upper()}_{role}_PASSWORD"] = secrets.token_hex(24)
    # Exclusive creation: never overwrite credentials for an existing data volume.
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Local development only. Never commit this file.\n")
        stream.writelines(f"{key}={value}\n" for key, value in values.items())
    print("Created infra/db/.env with random local credentials (not printed).")


def compose(*args):
    if not ENV.exists():
        raise SystemExit("Run python infra/db/db.py init first.")
    if not shutil.which("docker"):
        raise SystemExit("Docker is missing. Install/start Docker with Compose v2 first.")
    subprocess.run(["docker", "compose", "--env-file", str(ENV), "-f",
                    str(HERE / "compose.yaml"), *args], cwd=HERE, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "up", "check", "status", "logs", "stop", "down", "psql"))
    parser.add_argument("database", nargs="?", choices=DOMAINS)
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "up":
        compose("up", "-d", "--wait", "--wait-timeout", "180")
        compose("exec", "-T", "postgres", "bash", "/opt/kkulpick/check.sh")
    elif args.command == "check":
        compose("exec", "-T", "postgres", "bash", "/opt/kkulpick/check.sh")
    elif args.command == "status":
        compose("ps")
    elif args.command == "logs":
        compose("logs", "--tail", "100", "postgres")
    elif args.command in ("stop", "down"):
        compose(args.command)  # no -v: preserve the data volume
    elif args.command == "psql":
        if not args.database:
            parser.error("psql requires member, catalog, or support")
        domain = args.database
        # User input is constrained to the three argparse choices.
        script = (f'export PGPASSWORD="${{{domain.upper()}_OWNER_PASSWORD}}"; '
                  f'exec psql -X -h 127.0.0.1 -U kkulpick_{domain}_owner -d kkulpick_{domain}')
        compose("exec", "postgres", "bash", "-c", script)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
