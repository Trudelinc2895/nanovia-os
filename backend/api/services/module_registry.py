from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_MONETIZATION_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "shared" / "catalog" / "monetization.json"
)


def _load_public_catalog() -> dict[str, Any]:
    with _MONETIZATION_CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


PUBLIC_MONETIZATION_CATALOG = _load_public_catalog()


def _build_module_registry() -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for slug, cfg in PUBLIC_MONETIZATION_CATALOG["modules"].items():
        entry = deepcopy(cfg)
        entry["slug"] = slug
        entry["key"] = entry.get("key", slug)
        registry[slug] = entry
    return registry


MODULE_REGISTRY = _build_module_registry()
MODULE_REGISTRY_SLUGS = tuple(MODULE_REGISTRY.keys())

MODULE_IDENTIFIER_TO_SLUG = {
    identifier: slug
    for slug, entry in MODULE_REGISTRY.items()
    for identifier in {slug, entry["key"]}
}


def canonicalize_module_slug(module_identifier: str | None) -> str | None:
    if not module_identifier:
        return None
    return MODULE_IDENTIFIER_TO_SLUG.get(module_identifier)


def get_module_registry_entry(module_identifier: str) -> dict[str, Any] | None:
    canonical_slug = canonicalize_module_slug(module_identifier)
    if not canonical_slug:
        return None
    return MODULE_REGISTRY.get(canonical_slug)


def get_module_lookup_slugs(module_identifier: str) -> tuple[str, ...]:
    entry = get_module_registry_entry(module_identifier)
    if not entry:
        return ()
    if entry["key"] == entry["slug"]:
        return (entry["slug"],)
    return (entry["slug"], entry["key"])
