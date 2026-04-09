"""Pytest fallback async runner for environments missing pytest-asyncio.

If pytest-asyncio is installed, its own plugin handles async tests and this
hook remains effectively unused. If not installed, this hook executes coroutine
tests with asyncio.run so the suite still works in constrained CI/dev setups.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
from pathlib import Path


ROOT_BACKEND = Path(__file__).resolve().parents[1]
if str(ROOT_BACKEND) not in sys.path:
    sys.path.insert(0, str(ROOT_BACKEND))

# Minimal defaults so importing settings-dependent modules in unit tests does
# not require local secrets/infra.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-chars")


def pytest_pyfunc_call(pyfuncitem):
    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_func(**kwargs))
    return True
