from api.core.alembic_bootstrap import (
    HEAD_REVISION,
    INITIAL_SCHEMA_REVISION,
    TOTP_REVISION,
    resolve_legacy_revision,
)


def test_resolve_legacy_revision_returns_none_without_users_table():
    assert resolve_legacy_revision({"subscriptions"}, set()) is None


def test_resolve_legacy_revision_detects_initial_schema():
    assert resolve_legacy_revision({"users", "subscriptions"}, {"id", "email"}) == INITIAL_SCHEMA_REVISION


def test_resolve_legacy_revision_detects_totp_schema():
    assert (
        resolve_legacy_revision(
            {"users", "subscriptions"},
            {"id", "email", "totp_secret", "totp_enabled"},
        )
        == TOTP_REVISION
    )


def test_resolve_legacy_revision_detects_head_schema():
    assert (
        resolve_legacy_revision(
            {"users", "subscriptions", "user_modules"},
            {
                "id",
                "email",
                "totp_secret",
                "totp_enabled",
                "email_verified",
                "email_verification_token",
                "email_verification_expires",
            },
        )
        == HEAD_REVISION
    )
