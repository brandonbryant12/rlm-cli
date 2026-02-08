"""Smoke tests for rlm_cli.cli — non-LLM commands only."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rlm_cli.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_project(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "utils.py").write_text("def helper(): pass\n")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.py").write_text("import utils\n")
    return tmp_path


class TestVersion:
    def test_version_flag(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.5.0" in result.output


class TestHelp:
    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Recursive Language Models" in result.output

    def test_scan_help(self, runner):
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0
        assert "--task" in result.output

    def test_config_help(self, runner):
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0


class TestTree:
    def test_tree_text(self, runner, sample_project):
        result = runner.invoke(cli, ["tree", str(sample_project)])
        assert result.exit_code == 0
        assert "main.py" in result.output
        assert "src/app.py" in result.output

    def test_tree_json(self, runner, sample_project):
        result = runner.invoke(cli, ["tree", str(sample_project), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["file_count"] == 3
        assert "main.py" in data["files"]

    def test_tree_no_gitignore(self, runner, sample_project):
        (sample_project / ".gitignore").write_text("*.py\n")
        # With gitignore, .py files should be filtered
        result = runner.invoke(cli, ["tree", str(sample_project)])
        assert "main.py" not in result.output

        # Without gitignore, .py files should appear
        result = runner.invoke(cli, ["tree", str(sample_project), "--no-gitignore"])
        assert "main.py" in result.output


class TestStatus:
    def test_no_cache(self, runner, sample_project):
        result = runner.invoke(cli, ["status", str(sample_project)])
        assert result.exit_code == 0
        assert "No cache directory" in result.output

    def test_no_cache_json(self, runner, sample_project):
        result = runner.invoke(cli, ["status", str(sample_project), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["baselines"] == []


class TestConfigPath:
    def test_shows_paths(self, runner):
        result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code == 0
        assert "Global:" in result.output
        assert "Project:" in result.output


class TestConfigShow:
    def test_shows_resolved_config(self, runner, sample_project):
        result = runner.invoke(cli, ["config", "show", str(sample_project)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "smart_model" in data
        assert "max_iterations" in data


class TestConfigSet:
    def test_set_project_config(self, runner, tmp_path):
        result = runner.invoke(cli, [
            "config", "set", "max_iterations", "10", "--project",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "max_iterations" in result.output

    def test_invalid_key(self, runner):
        result = runner.invoke(cli, ["config", "set", "bad_key", "val", "--global"])
        assert result.exit_code == 1

    def test_invalid_int_value(self, runner, tmp_path, monkeypatch):
        import rlm_cli.config as config_mod
        monkeypatch.setattr(config_mod, "DEFAULT_CONFIG_PATH", tmp_path / "cfg.json")

        result = runner.invoke(cli, ["config", "set", "max_iterations", "notanumber", "--global"])
        assert result.exit_code == 1

    def test_no_scope_specified(self, runner):
        result = runner.invoke(cli, ["config", "set", "max_iterations", "10"])
        assert result.exit_code == 1


class TestScanDryRun:
    def test_dry_run(self, runner, sample_project):
        result = runner.invoke(cli, [
            "scan", str(sample_project), "-t", "security", "--dry-run",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
