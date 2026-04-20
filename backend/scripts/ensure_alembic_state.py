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
from api.core.alembic_bootstrap import (  # noqa: E402
    missing_required_auth_columns,
    resolve_legacy_revision,
    select_revision_to_stamp,
)


def _get_alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


_USER_COLUMN_DDL = {
    "totp_secret": 'ALTER TABLE users ADD COLUMN totp_secret VARCHAR(512)',
    "totp_enabled": "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    "email_verified": "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE",
    "email_verification_token": "ALTER TABLE users ADD COLUMN email_verification_token VARCHAR(128)",
    "email_verification_expires": "ALTER TABLE users ADD COLUMN email_verification_expires TIMESTAMPTZ",
}


def _reconcile_user_auth_columns(conn, user_columns: set[str]) -> set[str]:
    missing = sorted(missing_required_auth_columns(user_columns))
    if not missing:
        return user_columns

    print("Reconciling legacy auth columns on users:", missing)
    for column in missing:
        conn.execute(text(_USER_COLUMN_DDL[column]))

    if "totp_secret" in user_columns:
        conn.execute(text("ALTER TABLE users ALTER COLUMN totp_secret TYPE VARCHAR(512)"))

    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_users_email_verification_token "
            "ON users (email_verification_token)"
        )
    )
    return user_columns | set(missing)


def main() -> int:
    engine = create_engine(settings.DATABASE_URL.replace("+psycopg", "+psycopg"))

    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())
        current_revisions: list[str] = []

        if "alembic_version" in table_names:
            version_rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            current_revisions = [row[0] for row in version_rows]

        user_columns = set()
        if "users" in table_names:
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            user_columns = _reconcile_user_auth_columns(conn, user_columns)

    detected_revision = resolve_legacy_revision(table_names, user_columns)
    revision = select_revision_to_stamp(current_revisions, detected_revision)
    if revision is None:
        print(
            "No Alembic bootstrap needed.",
            f"current={current_revisions or ['<unmanaged>']}",
            f"detected={detected_revision}",
        )
        return 0

    print(
        "Stamping database before upgrade:",
        revision,
        f"current={current_revisions or ['<unmanaged>']}",
        f"(tables={sorted(table_names)})",
    )
    command.stamp(_get_alembic_config(), revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
