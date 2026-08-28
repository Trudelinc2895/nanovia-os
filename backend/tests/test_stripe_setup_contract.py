from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_PATH = REPO_ROOT / "stripe" / "setup_stripe.py"
PILOT_CONTRACT_PATH = (
    REPO_ROOT / "backend" / "api" / "services" / "pilot_stripe_contract_service.py"
)


def _load_setup_module(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_nanovia_contract")
    spec = importlib.util.spec_from_file_location("nanovia_stripe_setup_contract", SETUP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_string_frozenset(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = node.value
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "frozenset"
            and len(value.args) == 1
            and isinstance(value.args[0], (ast.Set, ast.List, ast.Tuple))
        ):
            raise AssertionError(f"{name} is not a literal frozenset")
        return {
            element.value
            for element in value.args[0].elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    raise AssertionError(f"Could not find {name} in {path}")


def test_stripe_bootstrap_subscribes_every_pilot_runtime_event(monkeypatch):
    setup = _load_setup_module(monkeypatch)
    configured = set(setup.WEBHOOK_EVENTS)
    checkout_events = _extract_string_frozenset(
        PILOT_CONTRACT_PATH,
        "PILOT_CHECKOUT_EVENT_TYPES",
    )
    reversal_events = _extract_string_frozenset(
        PILOT_CONTRACT_PATH,
        "PILOT_REVERSAL_EVENT_TYPES",
    )

    assert checkout_events <= configured
    assert reversal_events <= configured


def test_setup_webhook_reconciles_existing_endpoint_without_dropping_extra_events(
    monkeypatch,
):
    setup = _load_setup_module(monkeypatch)
    url = f"https://{setup.DOMAIN}/api/v1/billing/webhook"
    existing = SimpleNamespace(
        id="we_existing",
        url=url,
        enabled_events=["checkout.session.completed", "customer.source.updated"],
    )
    monkeypatch.setattr(
        setup.stripe.WebhookEndpoint,
        "list",
        lambda: SimpleNamespace(data=[existing]),
    )

    modified: dict[str, object] = {}

    def _modify(endpoint_id: str, **kwargs):
        modified["endpoint_id"] = endpoint_id
        modified.update(kwargs)
        return SimpleNamespace(
            id=endpoint_id,
            url=url,
            enabled_events=kwargs["enabled_events"],
        )

    monkeypatch.setattr(setup.stripe.WebhookEndpoint, "modify", _modify)

    result = setup.setup_webhook()

    assert modified["endpoint_id"] == "we_existing"
    enabled_events = set(modified["enabled_events"])
    assert set(setup.WEBHOOK_EVENTS) <= enabled_events
    assert "customer.source.updated" in enabled_events
    assert set(result.enabled_events) == enabled_events


def test_setup_webhook_leaves_wildcard_endpoint_unchanged(monkeypatch):
    setup = _load_setup_module(monkeypatch)
    url = f"https://{setup.DOMAIN}/api/v1/billing/webhook"
    existing = SimpleNamespace(
        id="we_wildcard",
        url=url,
        enabled_events=["*"],
    )
    monkeypatch.setattr(
        setup.stripe.WebhookEndpoint,
        "list",
        lambda: SimpleNamespace(data=[existing]),
    )

    def _unexpected_modify(*args, **kwargs):
        raise AssertionError("Wildcard endpoint must not be modified")

    monkeypatch.setattr(setup.stripe.WebhookEndpoint, "modify", _unexpected_modify)

    result = setup.setup_webhook()

    assert result is existing
