from api.core.alembic_bootstrap import (
    BRANDING_REVISION,
    HEAD_REVISION,
    INITIAL_SCHEMA_REVISION,
    MERGED_HEAD_REVISION,
    TOTP_REVISION,
    WORKSPACE_BILLING_REVISION,
    missing_required_auth_columns,
    resolve_legacy_revision,
    select_revision_to_stamp,
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


def test_resolve_legacy_revision_detects_head_from_user_modules_table():
    assert resolve_legacy_revision({"users", "user_modules"}, {"id", "email"}) == HEAD_REVISION


def test_resolve_legacy_revision_detects_head_from_email_verification_columns():
    assert (
        resolve_legacy_revision(
            {"users", "subscriptions"},
            {"id", "email", "email_verified"},
        )
        == HEAD_REVISION
    )


def test_resolve_legacy_revision_detects_workspace_billing_branch():
    assert (
        resolve_legacy_revision(
            {"users", "workspaces", "plans"},
            {"id", "email"},
        )
        == WORKSPACE_BILLING_REVISION
    )


def test_resolve_legacy_revision_detects_branding_branch():
    assert (
        resolve_legacy_revision(
            {"users", "branding_settings"},
            {"id", "email"},
        )
        == BRANDING_REVISION
    )


def test_resolve_legacy_revision_detects_merged_heads():
    assert (
        resolve_legacy_revision(
            {"users", "workspaces", "branding_settings"},
            {"id", "email"},
        )
        == MERGED_HEAD_REVISION
    )


def test_select_revision_to_stamp_for_unmanaged_database():
    assert select_revision_to_stamp([], INITIAL_SCHEMA_REVISION) == INITIAL_SCHEMA_REVISION


def test_select_revision_to_stamp_advances_stale_alembic_version():
    assert select_revision_to_stamp([TOTP_REVISION], HEAD_REVISION) == HEAD_REVISION


def test_select_revision_to_stamp_advances_branch_heads_to_merge():
    assert select_revision_to_stamp([WORKSPACE_BILLING_REVISION], MERGED_HEAD_REVISION) == MERGED_HEAD_REVISION
    assert select_revision_to_stamp([BRANDING_REVISION], MERGED_HEAD_REVISION) == MERGED_HEAD_REVISION


def test_select_revision_to_stamp_ignores_current_or_newer_revision():
    assert select_revision_to_stamp([HEAD_REVISION], HEAD_REVISION) is None


def test_missing_required_auth_columns_reports_partial_legacy_user_schema():
    assert missing_required_auth_columns({"id", "email", "email_verified"}) == {
        "totp_secret",
        "totp_enabled",
        "email_verification_token",
        "email_verification_expires",
    }
