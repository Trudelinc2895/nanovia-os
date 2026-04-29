"""
Unit tests for scraping service — risk scoring, governance, stealth headers, and behavior.
"""
from __future__ import annotations

import pytest


# ── risk.py ──────────────────────────────────────────────────────────────────

def test_score_url_normal_returns_low_score():
    """Normal HTTPS URL should have a low risk score."""
    from api.scraping.risk import score_url
    score = score_url("https://www.example.com/page?q=hello")
    assert score < 0.5


def test_score_url_ip_host_adds_high_score():
    """IP address as hostname should add 0.8 to the score."""
    from api.scraping.risk import score_url
    score = score_url("http://192.168.1.1/admin")
    assert score >= 0.8


def test_score_url_non_standard_port_adds_score():
    """Non-standard port should add 0.3 to the score."""
    from api.scraping.risk import score_url
    score_with_port = score_url("http://example.com:8888/path")
    score_without = score_url("http://example.com/path")
    assert score_with_port > score_without


def test_score_url_suspicious_tld():
    """Suspicious TLDs (.xyz, .tk, etc.) should add 0.2 to the score."""
    from api.scraping.risk import score_url
    score_xyz = score_url("http://example.xyz/page")
    score_com = score_url("http://example.com/page")
    assert score_xyz > score_com


def test_score_url_clamped_to_one():
    """Risk score must never exceed 1.0."""
    from api.scraping.risk import score_url
    # IP + non-standard port + suspicious TLD + short hostname — sum > 1
    score = score_url("http://1.2.3.4:9999/x")
    assert score <= 1.0
    assert score >= 0.0


def test_is_risky_returns_false_for_safe_url(monkeypatch):
    """is_risky should return False for a clearly safe URL."""
    from api.config import settings
    monkeypatch.setattr(settings, "SCRAPING_RISK_SCORE_THRESHOLD", 0.75)
    from api.scraping.risk import is_risky
    assert is_risky("https://www.google.com/search?q=test") is False


def test_is_risky_returns_true_for_ip_url(monkeypatch):
    """is_risky should return True when score meets the threshold."""
    from api.config import settings
    monkeypatch.setattr(settings, "SCRAPING_RISK_SCORE_THRESHOLD", 0.75)
    from api.scraping.risk import is_risky
    assert is_risky("http://10.0.0.1/internal") is True


# ── governance.py ─────────────────────────────────────────────────────────────

def test_detect_anomaly_false_when_within_multiplier(monkeypatch):
    """No anomaly when current_rate is within the baseline multiplier."""
    from api.config import settings
    monkeypatch.setattr(settings, "SCRAPING_ANOMALY_BASELINE_MULTIPLIER", 3.0)
    from api.scraping.governance import detect_anomaly
    assert detect_anomaly("client-1", current_rate=9, baseline_rate=5) is False


def test_detect_anomaly_true_when_spike(monkeypatch):
    """Anomaly detected when current_rate > baseline * multiplier."""
    from api.config import settings
    monkeypatch.setattr(settings, "SCRAPING_ANOMALY_BASELINE_MULTIPLIER", 3.0)
    from api.scraping.governance import detect_anomaly
    assert detect_anomaly("client-2", current_rate=100, baseline_rate=10) is True


def test_detect_anomaly_false_when_no_baseline(monkeypatch):
    """No anomaly when baseline_rate is 0 (no history yet)."""
    from api.config import settings
    monkeypatch.setattr(settings, "SCRAPING_ANOMALY_BASELINE_MULTIPLIER", 3.0)
    from api.scraping.governance import detect_anomaly
    assert detect_anomaly("client-3", current_rate=9999, baseline_rate=0) is False


# ── stealth/headers.py ────────────────────────────────────────────────────────

def test_build_stealth_headers_returns_dict():
    """build_stealth_headers should return a non-empty dict."""
    from api.scraping.stealth.headers import build_stealth_headers
    headers = build_stealth_headers()
    assert isinstance(headers, dict)
    assert len(headers) > 0


def test_build_stealth_headers_has_user_agent():
    """build_stealth_headers must include a User-Agent header."""
    from api.scraping.stealth.headers import build_stealth_headers
    headers = build_stealth_headers()
    assert "User-Agent" in headers
    assert len(headers["User-Agent"]) > 10


def test_build_stealth_headers_with_explicit_profile():
    """build_stealth_headers accepts an explicit profile dict."""
    from api.scraping.stealth.headers import build_stealth_headers
    profile = {
        "ua": "TestBrowser/1.0",
        "accept_language": "fr-FR,fr;q=0.9",
        "sec_ch_ua": "",
        "sec_ch_ua_platform": "",
        "platform": "Win32",
    }
    headers = build_stealth_headers(profile=profile)
    assert headers["User-Agent"] == "TestBrowser/1.0"
    assert headers["Accept-Language"] == "fr-FR,fr;q=0.9"


# ── stealth/behavior.py ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_jitter_completes_without_error():
    """human_jitter should complete (it's a coroutine)."""
    from api.scraping.stealth.behavior import human_jitter
    await human_jitter(0, 1)  # extremely short for test speed


@pytest.mark.asyncio
async def test_human_jitter_skips_when_max_zero():
    """human_jitter with max_ms=0 should return immediately."""
    from api.scraping.stealth.behavior import human_jitter
    await human_jitter(0, 0)  # should not raise


@pytest.mark.asyncio
async def test_human_jitter_equal_min_max():
    """human_jitter with min == max should not raise."""
    from api.scraping.stealth.behavior import human_jitter
    await human_jitter(5, 5)
