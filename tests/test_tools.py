"""Tests for rlm_cli.tools."""

import pytest

from rlm_cli.loader import SENTINEL_PREFIX
from rlm_cli.loader import flatten_tree
from rlm_cli.tools import make_repl_tools


@pytest.fixture
def sample_tree():
    return {
        "main.py": "import os\nimport sys\n\ndef main():\n    print('hello')\n",
        "utils.py": "def helper(x):\n    return x + 1\n\nPASSWORD = 'secret123'\n",
        "src": {
            "app.py": "from utils import helper\n\nclass App:\n    pass\n",
            "config.json": '{"key": "value"}\n',
        },
        "data": {
            "readme.txt": "This is a readme file.\n",
        },
    }


@pytest.fixture
def tools(sample_tree):
    return make_repl_tools(sample_tree)


@pytest.fixture
def grep_tree(tools):
    return tools[0]


@pytest.fixture
def list_files(tools):
    return tools[1]


@pytest.fixture
def file_stats(tools):
    return tools[2]


@pytest.fixture
def read_file(tools):
    return tools[3]


@pytest.fixture
def find_imports(tools):
    return tools[4]


class TestFlatten:
    def test_flat_dict(self):
        result = flatten_tree({"a.py": "content"})
        assert result == {"a.py": "content"}

    def test_nested_dict(self):
        result = flatten_tree({"src": {"app.py": "code"}})
        assert result == {"src/app.py": "code"}

    def test_deeply_nested(self):
        result = flatten_tree({"a": {"b": {"c.py": "x"}}})
        assert result == {"a/b/c.py": "x"}


class TestGrepTree:
    def test_finds_pattern(self, grep_tree):
        result = grep_tree("PASSWORD")
        assert "utils.py:4:" in result
        assert "secret123" in result

    def test_case_insensitive(self, grep_tree):
        result = grep_tree("password")
        assert "utils.py" in result

    def test_regex_pattern(self, grep_tree):
        result = grep_tree(r"def \w+\(")
        assert "main.py" in result
        assert "utils.py" in result

    def test_no_matches(self, grep_tree):
        result = grep_tree("NONEXISTENT_PATTERN_XYZ")
        assert result == "No matches found."

    def test_invalid_regex(self, grep_tree):
        result = grep_tree("[invalid")
        assert "Invalid regex" in result

    def test_max_results(self, grep_tree):
        result = grep_tree(".", max_results=3)
        assert "truncated at 3" in result

    def test_skips_sentinel_entries(self):
        tree = {
            "ok.py": "findme\n",
            "bad.py": f"{SENTINEL_PREFIX}FILE TOO LARGE: 999 bytes",
        }
        tools = make_repl_tools(tree)
        result = tools[0]("findme")
        assert "ok.py" in result
        assert "bad.py" not in result

    def test_does_not_skip_bracket_content(self):
        """Files starting with [ should be searchable."""
        tree = {"array.json": '[1, 2, "findme"]'}
        tools = make_repl_tools(tree)
        result = tools[0]("findme")
        assert "array.json" in result


class TestListFiles:
    def test_lists_all(self, list_files):
        result = list_files()
        assert "main.py" in result
        assert "src/app.py" in result
        assert "data/readme.txt" in result

    def test_glob_filter(self, list_files):
        result = list_files("*.py")
        assert "main.py" in result
        assert "src/app.py" in result
        assert "config.json" not in result
        assert "readme.txt" not in result

    def test_no_matches(self, list_files):
        result = list_files("*.xyz")
        assert result == "No files match that pattern."

    def test_includes_char_count(self, list_files):
        result = list_files("*.py")
        assert "chars)" in result


class TestFileStats:
    def test_returns_overview(self, file_stats):
        result = file_stats()
        assert "Total files:" in result
        assert "Total lines:" in result
        assert "By extension:" in result
        assert ".py" in result
        assert "Largest files:" in result

    def test_counts_files(self, file_stats):
        result = file_stats()
        assert "Total files: 5" in result


class TestReadFile:
    def test_exact_path(self, read_file):
        result = read_file("main.py")
        assert "import os" in result

    def test_nested_path(self, read_file):
        result = read_file("src/app.py")
        assert "from utils import helper" in result

    def test_fuzzy_match_suffix(self, read_file):
        result = read_file("app.py")
        assert "from utils import helper" in result

    def test_not_found(self, read_file):
        result = read_file("nonexistent.py")
        assert "File not found" in result

    def test_ambiguous_match(self):
        tree = {
            "a": {"test.py": "a_test"},
            "b": {"test.py": "b_test"},
        }
        tools = make_repl_tools(tree)
        result = tools[3]("test.py")
        assert "Ambiguous" in result


class TestFindImports:
    def test_finds_python_imports(self, find_imports):
        result = find_imports("main.py")
        assert "import os" in result
        assert "import sys" in result

    def test_finds_from_imports(self, find_imports):
        result = find_imports("src/app.py")
        assert "from utils import helper" in result

    def test_no_imports(self, find_imports):
        result = find_imports("data/readme.txt")
        assert result == "No import statements found."

    def test_file_not_found(self, find_imports):
        result = find_imports("nonexistent.py")
        assert "File not found" in result
