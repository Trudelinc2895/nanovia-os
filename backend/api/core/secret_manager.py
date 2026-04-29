"""Managed secret resolution helpers for Nanovia runtime settings."""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class VaultSecretReference:
    mount: str
    path: str
    field: str


def is_vault_reference(value: str | None) -> bool:
    return bool(value and value.strip().startswith("vault://"))


def parse_vault_reference(reference: str) -> VaultSecretReference:
    raw = reference.strip()
    if not raw.startswith("vault://"):
        raise ValueError("Vault secret references must start with vault://")

    location = raw[len("vault://") :]
    path_part, separator, field = location.partition("#")
    if not separator or not field.strip():
        raise ValueError("Vault secret references must include a #field suffix")

    mount, slash, secret_path = path_part.partition("/")
    if not slash or not mount.strip() or not secret_path.strip():
        raise ValueError("Vault secret references must use vault://<mount>/<path>#<field>")

    return VaultSecretReference(
        mount=mount.strip(),
        path=secret_path.strip("/"),
        field=field.strip(),
    )


def fetch_vault_secret(
    reference: str,
    *,
    vault_addr: str,
    vault_token: str,
    timeout: float = 5.0,
) -> str:
    if not vault_addr.strip():
        raise ValueError("VAULT_ADDR is required to resolve Vault secret references")
    if not vault_token.strip():
        raise ValueError("VAULT_TOKEN is required to resolve Vault secret references")

    secret_ref = parse_vault_reference(reference)
    api_url = f"{vault_addr.rstrip('/')}/v1/{secret_ref.mount}/data/{secret_ref.path}"
    request = Request(
        api_url,
        headers={
            "X-Vault-Token": vault_token,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ValueError(f"Vault secret fetch failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"Vault secret fetch failed: {exc.reason}") from exc

    data = payload.get("data", {})
    secret_values = data.get("data", data)
    if secret_ref.field not in secret_values:
        raise ValueError(
            f"Vault secret field {secret_ref.field!r} not found at {secret_ref.mount}/{secret_ref.path}"
        )

    resolved = secret_values[secret_ref.field]
    if not isinstance(resolved, str) or not resolved.strip():
        raise ValueError(
            f"Vault secret field {secret_ref.field!r} at {secret_ref.mount}/{secret_ref.path} is empty"
        )
    return resolved.strip()


def resolve_secret_value(
    *,
    provider: str,
    value: str | None,
    reference: str | None,
    vault_addr: str,
    vault_token: str,
    timeout: float = 5.0,
) -> str:
    candidate = (value or "").strip()
    secret_ref = (reference or "").strip()

    if candidate and not is_vault_reference(candidate):
        return candidate
    if not secret_ref and is_vault_reference(candidate):
        secret_ref = candidate

    if not secret_ref:
        return candidate
    if not is_vault_reference(secret_ref):
        raise ValueError("Managed secret references must use the vault://<mount>/<path>#<field> format")
    if provider == "env":
        return candidate

    return fetch_vault_secret(
        secret_ref,
        vault_addr=vault_addr,
        vault_token=vault_token,
        timeout=timeout,
    )
