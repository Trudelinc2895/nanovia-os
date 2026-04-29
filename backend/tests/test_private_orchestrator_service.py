from api.config import settings
from api.services import private_orchestrator_service


def test_get_allowed_agent_keys_filters_unknowns_and_duplicates(monkeypatch):
    monkeypatch.setattr(
        settings,
        "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW",
        "ghost_agency,unknown,operator,ghost_agency",
    )

    assert private_orchestrator_service.get_allowed_agent_keys() == ["ghost_agency", "operator"]


def test_get_allowed_agent_keys_falls_back_to_default_catalog_when_config_invalid(monkeypatch):
    monkeypatch.setattr(settings, "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW", "unknown_only")

    assert private_orchestrator_service.get_allowed_agent_keys() == [
        "operator",
        "ghost_agency",
        "decision_engine",
    ]


def test_build_memory_snapshot_summarizes_recent_messages():
    snapshot = private_orchestrator_service.build_memory_snapshot(
        [
            {"role": "user", "content": "Need a plan for outreach."},
            {"role": "assistant", "content": "Let's target warm leads first."},
        ]
    )

    assert snapshot["message_count"] == 2
    assert snapshot["recent_messages"][0]["role"] == "user"
    assert "warm leads" in snapshot["summary"]


def test_score_agents_prefers_decision_engine_for_decision_prompt():
    candidates = private_orchestrator_service.score_agents(
        "Compare these options, analyze tradeoffs and recommend a decision."
    )

    assert candidates[0]["key"] == "decision_engine"
    assert candidates[0]["score"] >= candidates[1]["score"]
