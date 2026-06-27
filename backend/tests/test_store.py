"""Tests for backend.db.store.DataStore file-fallback mode (no DB required)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

from backend.db.store import DataStore


@pytest.fixture
def store(tmp_path) -> DataStore:
    """Create a DataStore instance with no DB (file fallback only)."""
    logger = logging.getLogger("test")
    return DataStore(
        database_url="",  # no DB
        user_config_dir=tmp_path / "configs",
        logger=logger,
    )


@pytest.fixture
def sample_user() -> dict:
    return {
        "iss": "https://auth.example.com",
        "sub": "user-123",
        "name": "Test User",
        "email": "test@example.com",
    }


class TestSafeUserId:
    def test_safe_user_id_deterministic(self, store, sample_user):
        id1 = store.safe_user_id(sample_user)
        id2 = store.safe_user_id(sample_user)
        assert id1 == id2

    def test_safe_user_id_same_issuer_subject(self, store):
        u1 = {"iss": "  https://auth.example.com  ", "sub": "  user-123  "}
        u2 = {"iss": "https://auth.example.com", "sub": "user-123"}
        assert store.safe_user_id(u1) == store.safe_user_id(u2)

    def test_safe_user_id_different_users(self, store):
        u1 = {"iss": "https://auth.example.com", "sub": "user-1"}
        u2 = {"iss": "https://auth.example.com", "sub": "user-2"}
        assert store.safe_user_id(u1) != store.safe_user_id(u2)


class TestUserConfigFileFallback:
    def test_get_user_config_returns_empty_when_no_file(self, store, sample_user):
        result = store.get_user_config(sample_user)
        assert result == {}

    def test_put_and_get_user_config(self, store, sample_user):
        config_data = {"theme": "dark", "language": "en"}
        ts = store.put_user_config(sample_user, config_data)

        result = store.get_user_config(sample_user)
        assert result["config"] == config_data
        assert "updated_at" in result

    def test_get_user_config_merges_updated_at(self, store, sample_user):
        config_data = {"setting": "value"}
        store.put_user_config(sample_user, config_data)

        result = store.get_user_config(sample_user)
        assert isinstance(result["updated_at"], int)

    def test_put_user_config_overwrites_existing(self, store, sample_user):
        store.put_user_config(sample_user, {"v": 1})
        time.sleep(0.01)  # ensure different timestamp
        ts = store.put_user_config(sample_user, {"v": 2})

        result = store.get_user_config(sample_user)
        assert result["config"] == {"v": 2}

    def test_corrupted_config_file_returns_empty(self, store, sample_user, tmp_path):
        user_id = store.safe_user_id(sample_user)
        config_dir = tmp_path / "configs" / user_id
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text("not valid json{", encoding="utf-8")

        result = store.get_user_config(sample_user)
        assert result == {}

    def test_non_dict_config_file_returns_empty(self, store, sample_user, tmp_path):
        user_id = store.safe_user_id(sample_user)
        config_dir = tmp_path / "configs" / user_id
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text('["not", "a", "dict"]', encoding="utf-8")

        result = store.get_user_config(sample_user)
        assert result == {}


class TestPresetsFileFallback:
    def test_list_presets_empty_initially(self, store, sample_user):
        result = store.list_presets(sample_user)
        assert result == []

    def test_create_and_list_preset(self, store, sample_user):
        preset_data = {
            "name": "My Preset",
            "job_type": "general",
            "description": "Test preset",
            "settings": {"quality": "high"},
            "is_default": False,
        }
        created = store.create_preset(sample_user, preset_data)

        assert created["name"] == "My Preset"
        assert created["job_type"] == "general"
        assert created["settings"] == {"quality": "high"}
        assert "id" in created

        presets = store.list_presets(sample_user)
        assert len(presets) == 1
        assert presets[0]["name"] == "My Preset"

    def test_create_preset_requires_name(self, store, sample_user):
        with pytest.raises(ValueError, match="name is required"):
            store.create_preset(sample_user, {"name": ""})

        with pytest.raises(ValueError, match="name is required"):
            store.create_preset(sample_user, {})

    def test_create_preset_defaults_job_type(self, store, sample_user):
        created = store.create_preset(sample_user, {"name": "Test"})
        assert created["job_type"] == "general"

    def test_create_preset_resets_other_default_for_same_job_type(self, store, sample_user):
        store.create_preset(sample_user, {"name": "A", "job_type": "general", "is_default": True})
        store.create_preset(sample_user, {"name": "B", "job_type": "general", "is_default": True})

        presets = store.list_presets(sample_user)
        defaults = [p for p in presets if p["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "B"

    def test_update_preset(self, store, sample_user):
        created = store.create_preset(sample_user, {"name": "Original"})
        preset_id = created["id"]

        updated = store.update_preset(sample_user, preset_id, {"name": "Updated"})
        assert updated["name"] == "Updated"

    def test_update_nonexistent_preset_returns_none(self, store, sample_user):
        result = store.update_preset(sample_user, "nonexistent-id", {"name": "X"})
        assert result is None

    def test_update_preset_clears_default_on_others(self, store, sample_user):
        store.create_preset(sample_user, {"name": "A", "job_type": "general", "is_default": True})
        created = store.create_preset(sample_user, {"name": "B", "job_type": "general"})
        store.update_preset(sample_user, created["id"], {"is_default": True})

        presets = store.list_presets(sample_user)
        defaults = [p for p in presets if p["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "B"

    def test_delete_preset(self, store, sample_user):
        created = store.create_preset(sample_user, {"name": "ToDelete"})
        preset_id = created["id"]

        result = store.delete_preset(sample_user, preset_id)
        assert result is True

        presets = store.list_presets(sample_user)
        assert len(presets) == 0

    def test_delete_nonexistent_preset_returns_false(self, store, sample_user):
        result = store.delete_preset(sample_user, "nonexistent-id")
        assert result is False

    def test_delete_with_empty_preset_id_returns_false(self, store, sample_user):
        result = store.delete_preset(sample_user, "")
        assert result is False


class TestEnabled:
    def test_enabled_false_when_no_database_url(self, store):
        assert store.enabled is False

    def test_enabled_true_with_url_and_psycopg(self, tmp_path, monkeypatch):
        logger = logging.getLogger("test")
        # Simulate psycopg being available
        import sys
        mock_psycopg = type(sys)("psycopg")
        sys.modules["psycopg"] = mock_psycopg

        store = DataStore(
            database_url="postgresql://localhost/test",
            user_config_dir=tmp_path / "configs",
            logger=logger,
        )
        # enabled depends on both url and _psycopg being set
        assert store.enabled is True

        del sys.modules["psycopg"]


class TestDatastoreEnabledProperty:
    def test_enabled_true_when_db_url_and_psycopg(self, tmp_path, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "psycopg", type(__import__("sys"))("psycopg"))
        logger = logging.getLogger("test2")
        store = DataStore(
            database_url="postgresql://localhost/testdb",
            user_config_dir=tmp_path / "configs",
            logger=logger,
        )
        # The store constructor tries to import psycopg; if it succeeds and url is set, enabled is True
        assert store.enabled is True