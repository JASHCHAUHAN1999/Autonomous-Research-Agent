"""Shared pytest fixtures for the Autonomous Research Agent test suite."""
import pytest

from app import config


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    """Point settings.db_path at a throwaway file and reset caches per test."""
    db_file = tmp_path / "test_research.db"
    monkeypatch.setattr(config.settings, "db_path", str(db_file))

    # Clear the model-discovery TTL cache if that module exists yet.
    try:
        from app import models  # noqa: WPS433 (local import is intentional)
        models._cache.clear()
    except Exception:
        pass

    yield


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point settings.db_path at an isolated temp database and create the schema."""
    from app.config import settings
    from app.storage import db

    db_file = tmp_path / "test_research.db"
    monkeypatch.setattr(settings, "db_path", str(db_file))
    db.init_db()
    yield str(db_file)
