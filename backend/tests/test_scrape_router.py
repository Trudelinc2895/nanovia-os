from __future__ import annotations

from api.main import app


def test_scrape_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    assert "/scrape" in paths
    assert "/scrape/jobs/{job_id}" in paths
