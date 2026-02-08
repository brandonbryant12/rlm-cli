"""Tests for rlm_cli.output."""

import json

import pytest

from rlm_cli.output import (
    format_result,
    iter_files,
    tree_summary,
    warn_model_choice,
    write_output,
)


@pytest.fixture
def sample_cost():
    return {
        "smart_model_calls": 5,
        "smart_model_tokens_in": 1000,
        "smart_model_tokens_out": 500,
        "sub_model_calls": 2,
        "sub_model_tokens_in": 200,
        "sub_model_tokens_out": 100,
        "total_cost_usd": 0.0123,
    }


@pytest.fixture
def sample_cfg():
    return {
        "smart_model": "anthropic/claude-sonnet-4-5",
        "small_model": "anthropic/claude-haiku-4-5",
        "max_iterations": 35,
    }


class TestFormatResult:
    def test_markdown_format(self, sample_cost, sample_cfg):
        result = format_result("# Analysis", sample_cost, "security", sample_cfg, 12.5)
        assert result.startswith("<!-- rlm-cli security")
        assert "# Analysis" in result
        assert "cost=$0.0123" in result

    def test_json_format(self, sample_cost, sample_cfg):
        result = format_result("findings here", sample_cost, "review", sample_cfg, 5.0, fmt="json")
        data = json.loads(result)
        assert data["task"] == "review"
        assert data["model"] == "anthropic/claude-sonnet-4-5"
        assert data["analysis"] == "findings here"
        assert data["elapsed_seconds"] == 5.0
        assert data["cost"]["total_cost_usd"] == 0.0123


class TestWriteOutput:
    def test_writes_to_file(self, tmp_path):
        output = tmp_path / "result.md"
        write_output("content", str(output), "security", tmp_path)
        assert output.read_text() == "content"

    def test_creates_parent_dirs(self, tmp_path):
        output = tmp_path / "sub" / "deep" / "result.md"
        write_output("content", str(output), "security", tmp_path)
        assert output.read_text() == "content"

    def test_relative_path_resolved(self, tmp_path):
        write_output("content", "output/result.md", "security", tmp_path)
        assert (tmp_path / "output" / "result.md").read_text() == "content"

    def test_stdout_when_no_path(self, capsys):
        write_output("stdout content", None, "security", None)
        captured = capsys.readouterr()
        assert "stdout content" in captured.out


class TestIterFiles:
    def test_flat_tree(self):
        tree = {"a.py": "x", "b.py": "y"}
        assert sorted(iter_files(tree)) == ["a.py", "b.py"]

    def test_nested_tree(self):
        tree = {"src": {"app.py": "x"}, "main.py": "y"}
        assert sorted(iter_files(tree)) == ["main.py", "src/app.py"]

    def test_deeply_nested(self):
        tree = {"a": {"b": {"c.py": "x"}}}
        assert list(iter_files(tree)) == ["a/b/c.py"]


class TestTreeSummary:
    def test_counts_files(self):
        tree = {"a.py": "hello", "b.js": "world", "src": {"c.py": "nested"}}
        stats = tree_summary(tree)
        assert stats["file_count"] == 3

    def test_counts_chars(self):
        tree = {"a.py": "12345"}
        stats = tree_summary(tree)
        assert stats["total_chars"] == 5

    def test_extension_breakdown(self):
        tree = {"a.py": "x", "b.py": "y", "c.js": "z"}
        stats = tree_summary(tree)
        assert stats["extensions"][".py"] == 2
        assert stats["extensions"][".js"] == 1


class TestWarnModelChoice:
    def test_no_warning_for_claude(self, capsys):
        warn_model_choice("anthropic/claude-sonnet-4-5")
        assert capsys.readouterr().err == ""

    def test_no_warning_for_gpt5(self, capsys):
        warn_model_choice("openai/gpt-5")
        assert capsys.readouterr().err == ""

    def test_no_warning_for_ollama(self, capsys):
        warn_model_choice("ollama/anything")
        assert capsys.readouterr().err == ""

    def test_warns_for_unknown_model(self, capsys):
        warn_model_choice("some-random-model")
        assert "Warning" in capsys.readouterr().err
