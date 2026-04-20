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
_REQUIRED_AUTH_COLUMNS = _TOTP_COLUMNS | _HEAD_ONLY_COLUMNS
_REVISION_ORDER = {
    INITIAL_SCHEMA_REVISION: 0,
    TOTP_REVISION: 1,
    HEAD_REVISION: 2,
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

    if "user_modules" in tables or (_HEAD_ONLY_COLUMNS & columns):
        return HEAD_REVISION

    if _TOTP_COLUMNS.issubset(columns):
        return TOTP_REVISION

    return INITIAL_SCHEMA_REVISION


def select_revision_to_stamp(
    current_revisions: Iterable[str],
    detected_revision: str | None,
) -> str | None:
    if detected_revision is None:
        return None

    current = [revision for revision in current_revisions if revision in _REVISION_ORDER]
    if not current:
        return detected_revision

    highest_current = max(current, key=_REVISION_ORDER.__getitem__)
    if _REVISION_ORDER[detected_revision] > _REVISION_ORDER[highest_current]:
        return detected_revision

    return None


def missing_required_auth_columns(user_columns: Iterable[str]) -> set[str]:
    return _REQUIRED_AUTH_COLUMNS - set(user_columns)
