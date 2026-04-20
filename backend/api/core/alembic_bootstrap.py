from __future__ import annotations

from typing import Iterable

INITIAL_SCHEMA_REVISION = "1e4c69cd0c11"
TOTP_REVISION = "370e89b14c7c"
HEAD_REVISION = "b9f3a2c1d8e7"

_TOTP_COLUMNS = {"totp_secret", "totp_enabled"}
_HEAD_ONLY_COLUMNS = {
    "email_verified",
    "email_verification_token",
    "email_verification_expires",
}


def resolve_legacy_revision(
    table_names: Iterable[str],
    user_columns: Iterable[str],
) -> str | None:
    """Return the safest Alembic revision to stamp for a legacy unmanaged DB."""
    tables = set(table_names)
    columns = set(user_columns)

    if "users" not in tables:
        return None

    if "user_modules" in tables and _HEAD_ONLY_COLUMNS.issubset(columns) and _TOTP_COLUMNS.issubset(columns):
        return HEAD_REVISION

    if _TOTP_COLUMNS.issubset(columns):
        return TOTP_REVISION

    return INITIAL_SCHEMA_REVISION
