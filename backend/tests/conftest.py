import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets its own throwaway SQLite file instead of the real db/requests.db."""
    monkeypatch.setattr(settings, "db_path", tmp_path / "test_requests.db")
    db.init_db()
    yield
