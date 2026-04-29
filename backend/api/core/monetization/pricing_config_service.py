"""Central pricing catalog access for Nanovia monetization."""
from __future__ import annotations

from copy import deepcopy

from api.services.billing_service import ADDONS_CONFIG, MODULES_CONFIG, PLANS_CONFIG


def get_pricing_catalog() -> dict[str, dict]:
    return {
        "plans": deepcopy(PLANS_CONFIG),
        "addons": deepcopy(ADDONS_CONFIG),
        "modules": deepcopy(MODULES_CONFIG),
    }


def get_plan_config(plan_key: str) -> dict:
    return deepcopy(PLANS_CONFIG[plan_key])


def get_addon_config(addon_key: str) -> dict:
    return deepcopy(ADDONS_CONFIG[addon_key])


def get_module_config(module_key: str) -> dict:
    return deepcopy(MODULES_CONFIG[module_key])
