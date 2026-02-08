"""Tests for rlm_cli.config."""

import json
import os
from pathlib import Path

import pytest

from rlm_cli.config import (
    DEFAULT_CONFIG,
    build_cfg,
    find_project_config,
    load_json,
    resolve_cache_dir,
    resolve_config,
    resolve_project_root,
    save_config,
)


class TestLoadJson:
    def test_valid_json(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text('{"smart_model": "gpt-5"}')
        assert load_json(p) == {"smart_model": "gpt-5"}

    def test_missing_file(self, tmp_path):
        assert load_json(tmp_path / "nonexistent.json") == {}

    def test_invalid_json(self, tmp_path, capsys):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json")
        assert load_json(p) == {}
        captured = capsys.readouterr()
        assert "invalid JSON" in captured.err

    def test_empty_file(self, tmp_path, capsys):
        p = tmp_path / "empty.json"
        p.write_text("")
        assert load_json(p) == {}
        captured = capsys.readouterr()
        assert "invalid JSON" in captured.err


class TestFindProjectConfig:
    def test_finds_config_in_current_dir(self, tmp_path):
        cfg = tmp_path / ".rlm-cli.json"
        cfg.write_text("{}")
        assert find_project_config(tmp_path) == cfg

    def test_finds_config_in_parent(self, tmp_path):
        cfg = tmp_path / ".rlm-cli.json"
        cfg.write_text("{}")
        child = tmp_path / "sub" / "deep"
        child.mkdir(parents=True)
        assert find_project_config(child) == cfg

    def test_stops_at_git_boundary(self, tmp_path):
        # Config above .git should not be found
        (tmp_path / ".rlm-cli.json").write_text("{}")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        child = repo / "src"
        child.mkdir()
        assert find_project_config(child) is None

    def test_finds_config_at_git_root(self, tmp_path):
        (tmp_path / ".git").mkdir()
        cfg = tmp_path / ".rlm-cli.json"
        cfg.write_text("{}")
        assert find_project_config(tmp_path) == cfg

    def test_no_config_found(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert find_project_config(tmp_path) is None


class TestResolveConfig:
    def test_defaults(self, tmp_path, monkeypatch):
        import rlm_cli.config as config_mod
        monkeypatch.setattr(config_mod, "DEFAULT_CONFIG_PATH", tmp_path / "nonexistent.json")
        monkeypatch.delenv("RLM_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("RLM_API_BASE", raising=False)
        monkeypatch.delenv("RLM_SMART_MODEL", raising=False)
        monkeypatch.delenv("RLM_SMALL_MODEL", raising=False)
        (tmp_path / ".git").mkdir()
        cfg = resolve_config(project_dir=tmp_path)
        assert cfg["smart_model"] == DEFAULT_CONFIG["smart_model"]
        assert cfg["max_iterations"] == 35

    def test_env_overrides(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.setenv("RLM_API_KEY", "test-key-123")
        monkeypatch.setenv("RLM_SMART_MODEL", "openai/gpt-5")
        cfg = resolve_config(project_dir=tmp_path)
        assert cfg["api_key"] == "test-key-123"
        assert cfg["smart_model"] == "openai/gpt-5"

    def test_cli_overrides_beat_env(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.setenv("RLM_SMART_MODEL", "env-model")
        cfg = resolve_config(
            project_dir=tmp_path,
            cli_overrides={"smart_model": "cli-model"},
        )
        assert cfg["smart_model"] == "cli-model"

    def test_project_config_loaded(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RLM_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        (tmp_path / ".git").mkdir()
        (tmp_path / ".rlm-cli.json").write_text(
            json.dumps({"max_iterations": 10, "smart_model": "proj-model"})
        )
        cfg = resolve_config(project_dir=tmp_path)
        assert cfg["max_iterations"] == 10
        assert cfg["smart_model"] == "proj-model"

    def test_fallback_api_keys(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("RLM_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthro-key")
        cfg = resolve_config(project_dir=tmp_path)
        assert cfg["api_key"] == "anthro-key"

    def test_none_values_in_overrides_ignored(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("RLM_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        cfg = resolve_config(
            project_dir=tmp_path,
            cli_overrides={"smart_model": None, "max_iterations": 5},
        )
        # None values should not override defaults
        assert cfg["smart_model"] == DEFAULT_CONFIG["smart_model"]
        assert cfg["max_iterations"] == 5


class TestSaveConfig:
    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "config.json"
        save_config(path, {"key": "value"})
        assert path.exists()
        assert json.loads(path.read_text()) == {"key": "value"}


class TestResolveProjectRoot:
    def test_valid_directory(self, tmp_path):
        assert resolve_project_root(str(tmp_path)) == tmp_path

    def test_nonexistent_directory(self, tmp_path):
        with pytest.raises(SystemExit, match="is not a directory"):
            resolve_project_root(str(tmp_path / "nope"))


class TestResolveCacheDir:
    def test_relative_path(self, tmp_path):
        result = resolve_cache_dir(tmp_path, {"cache_dir": ".rlm-cache"})
        assert result == tmp_path / ".rlm-cache"

    def test_absolute_path(self, tmp_path):
        abs_cache = tmp_path / "absolute-cache"
        result = resolve_cache_dir(tmp_path, {"cache_dir": str(abs_cache)})
        assert result == abs_cache

    def test_default_value(self, tmp_path):
        result = resolve_cache_dir(tmp_path, {})
        assert result == tmp_path / ".rlm-cache"


class TestBuildCfg:
    def test_merges_overrides(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("RLM_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        cfg = build_cfg(
            tmp_path,
            smart_model="test-model",
            small_model=None,
            api_base=None,
            api_key="test-key",
            max_iterations=10,
            max_output_chars=None,
            max_llm_calls=None,
            cache_dir=None,
        )
        assert cfg["smart_model"] == "test-model"
        assert cfg["api_key"] == "test-key"
        assert cfg["max_iterations"] == 10
        # Defaults should still be present
        assert cfg["small_model"] == DEFAULT_CONFIG["small_model"]
