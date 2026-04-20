from __future__ import annotations

from pathlib import Path
import sys

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.config import settings  # noqa: E402
from api.core.alembic_bootstrap import resolve_legacy_revision  # noqa: E402


def _get_alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


def main() -> int:
    engine = create_engine(settings.DATABASE_URL.replace("+psycopg", "+psycopg"))

    with engine.connect() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())

        if "alembic_version" in table_names:
            version_rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            if version_rows:
                print(f"Alembic already tracked at {[row[0] for row in version_rows]}")
                return 0

        user_columns = set()
        if "users" in table_names:
            user_columns = {column["name"] for column in inspector.get_columns("users")}

    revision = resolve_legacy_revision(table_names, user_columns)
    if revision is None:
        print("No legacy schema detected; no Alembic bootstrap needed.")
        return 0

    print(
        "Stamping legacy database before upgrade:",
        revision,
        f"(tables={sorted(table_names)})",
    )
    command.stamp(_get_alembic_config(), revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
