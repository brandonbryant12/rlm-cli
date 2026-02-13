"""Tests for rlm_cli.loader."""

import json
from pathlib import Path

import pytest

from rlm_cli.loader import (
    GitignoreFilter,
    SENTINEL_PREFIX,
    _unflatten_tree,
    flatten_tree,
    hash_tree,
    load_baseline,
    load_changed_tree,
    load_source_tree,
    load_source_tree_cache,
    load_source_tree_cached,
    read_files_from,
    save_baseline,
    save_source_tree_cache,
)


@pytest.fixture
def sample_project(tmp_path):
    """Create a small project structure for testing."""
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "utils.py").write_text("def helper(): pass\n")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.py").write_text("import utils\n")
    (sub / "config.json").write_text('{"key": "value"}\n')
    return tmp_path


class TestLoadSourceTree:
    def test_loads_files(self, sample_project):
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert "main.py" in tree
        assert "utils.py" in tree
        assert "src" in tree
        assert "app.py" in tree["src"]

    def test_reads_file_content(self, sample_project):
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert tree["main.py"] == "print('hello')\n"

    def test_skips_hidden_dirs(self, sample_project):
        (sample_project / ".hidden").mkdir()
        (sample_project / ".hidden" / "secret.py").write_text("x = 1")
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert ".hidden" not in tree

    def test_skips_pycache(self, sample_project):
        cache = sample_project / "__pycache__"
        cache.mkdir()
        (cache / "mod.cpython-312.pyc").write_bytes(b"\x00")
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert "__pycache__" not in tree

    def test_skips_binary_extensions(self, sample_project):
        (sample_project / "image.png").write_bytes(b"\x89PNG")
        (sample_project / "data.pdf").write_bytes(b"%PDF")
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert "image.png" not in tree
        assert "data.pdf" not in tree

    def test_skips_minified_files(self, sample_project):
        (sample_project / "bundle.min.js").write_text("var a=1;")
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert "bundle.min.js" not in tree

    def test_large_file_sentinel(self, sample_project):
        large = sample_project / "huge.txt"
        large.write_text("x" * (256 * 1024 + 1))
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert tree["huge.txt"].startswith(SENTINEL_PREFIX)
        assert "TOO LARGE" in tree["huge.txt"]

    def test_empty_dirs_excluded(self, tmp_path):
        (tmp_path / "empty_dir").mkdir()
        (tmp_path / "file.txt").write_text("content")
        tree = load_source_tree(tmp_path, project_root=tmp_path)
        assert "empty_dir" not in tree
        assert "file.txt" in tree

    def test_symlink_escape_blocked(self, tmp_path):
        # Create a directory outside the project
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret data")

        project = tmp_path / "project"
        project.mkdir()
        (project / "legit.py").write_text("x = 1")

        # Symlink pointing outside project
        (project / "escape").symlink_to(outside)

        tree = load_source_tree(project, project_root=project)
        assert "legit.py" in tree
        assert "escape" not in tree

    def test_allows_env_example(self, sample_project):
        (sample_project / ".env.example").write_text("API_KEY=xxx")
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert ".env.example" in tree

    def test_files_starting_with_bracket_not_dropped(self, sample_project):
        """Regression test: files starting with [ should not be treated as sentinels."""
        (sample_project / "array.json").write_text('[1, 2, 3]')
        (sample_project / "links.md").write_text('[click here](url)')
        tree = load_source_tree(sample_project, project_root=sample_project)
        assert tree["array.json"] == '[1, 2, 3]'
        assert tree["links.md"] == '[click here](url)'


class TestGitignoreFilter:
    def test_respects_gitignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\nbuild/\n")
        gi = GitignoreFilter(tmp_path)

        log_file = tmp_path / "app.log"
        log_file.touch()
        assert gi.is_ignored(log_file) is True

        py_file = tmp_path / "app.py"
        py_file.touch()
        assert gi.is_ignored(py_file) is False

    def test_respects_build_dir_pattern(self, tmp_path):
        (tmp_path / ".gitignore").write_text("build/\n")
        gi = GitignoreFilter(tmp_path)

        build_dir = tmp_path / "build"
        build_dir.mkdir()
        assert gi.is_ignored(build_dir) is True

    def test_negation_pattern(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\n!important.log\n")
        gi = GitignoreFilter(tmp_path)

        (tmp_path / "debug.log").touch()
        assert gi.is_ignored(tmp_path / "debug.log") is True

        (tmp_path / "important.log").touch()
        assert gi.is_ignored(tmp_path / "important.log") is False

    def test_nested_gitignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.tmp\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / ".gitignore").write_text("*.bak\n")
        gi = GitignoreFilter(tmp_path)

        (sub / "file.tmp").touch()
        assert gi.is_ignored(sub / "file.tmp") is True

        (sub / "file.bak").touch()
        assert gi.is_ignored(sub / "file.bak") is True

        (tmp_path / "root.bak").touch()
        assert gi.is_ignored(tmp_path / "root.bak") is False

    def test_integration_with_loader(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\nsecrets/\n")
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "debug.log").write_text("log data")
        secrets = tmp_path / "secrets"
        secrets.mkdir()
        (secrets / "key.txt").write_text("secret")

        gi = GitignoreFilter(tmp_path)
        tree = load_source_tree(tmp_path, gi, project_root=tmp_path)
        assert "app.py" in tree
        assert "debug.log" not in tree
        assert "secrets" not in tree


class TestHashTree:
    def test_deterministic(self):
        tree = {"a.py": "print(1)", "b.py": "print(2)"}
        h1 = hash_tree(tree)
        h2 = hash_tree(tree)
        assert h1 == h2
        assert len(h1) == 12

    def test_different_content_different_hash(self):
        t1 = {"a.py": "print(1)"}
        t2 = {"a.py": "print(2)"}
        assert hash_tree(t1) != hash_tree(t2)

    def test_different_filename_different_hash(self):
        t1 = {"a.py": "x"}
        t2 = {"b.py": "x"}
        assert hash_tree(t1) != hash_tree(t2)


class TestBaseline:
    def test_save_and_load(self, tmp_path):
        cache = tmp_path / "cache"
        save_baseline("analysis content", cache, "security", "abc123")
        assert (cache / "security.baseline.md").exists()
        assert (cache / "security.meta.json").exists()

        loaded = load_baseline(cache, "security")
        assert loaded == "analysis content"

        meta = json.loads((cache / "security.meta.json").read_text())
        assert meta["task"] == "security"
        assert meta["tree_hash"] == "abc123"

    def test_load_nonexistent(self, tmp_path):
        assert load_baseline(tmp_path, "security") is None

    def test_save_with_cost(self, tmp_path):
        cache = tmp_path / "cache"
        cost = {"total_cost_usd": 0.05}
        save_baseline("content", cache, "review", "def456", cost)
        meta = json.loads((cache / "review.meta.json").read_text())
        assert meta["cost"]["total_cost_usd"] == 0.05


class TestLoadChangedTree:
    def test_loads_changed_files(self, tmp_path):
        (tmp_path / "a.py").write_text("changed content")
        (tmp_path / "b.py").write_text("also changed")
        tree = load_changed_tree(tmp_path, ["a.py", "b.py"])
        assert tree["a.py"] == "changed content"
        assert tree["b.py"] == "also changed"

    def test_marks_deleted_files(self, tmp_path):
        tree = load_changed_tree(tmp_path, ["deleted.py"])
        assert tree["deleted.py"].startswith(SENTINEL_PREFIX)
        assert "DELETED" in tree["deleted.py"]

    def test_skips_binary_extensions(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        tree = load_changed_tree(tmp_path, ["image.png"])
        assert "image.png" not in tree

    def test_blocks_path_traversal(self, tmp_path):
        tree = load_changed_tree(tmp_path, ["../../etc/passwd"])
        assert "../../etc/passwd" not in tree


class TestReadFilesFrom:
    def test_comma_separated(self):
        result = read_files_from("a.py,b.py,c.py")
        assert result == ["a.py", "b.py", "c.py"]

    def test_from_file(self, tmp_path):
        listing = tmp_path / "files.txt"
        listing.write_text("a.py\nb.py\n\nc.py\n")
        result = read_files_from(str(listing))
        assert result == ["a.py", "b.py", "c.py"]

    def test_strips_whitespace(self):
        result = read_files_from("  a.py , b.py  ")
        assert result == ["a.py", "b.py"]


class TestUnflattenTree:
    def test_single_level(self):
        flat = {"a.py": "x", "b.py": "y"}
        assert _unflatten_tree(flat) == {"a.py": "x", "b.py": "y"}

    def test_nested(self):
        flat = {"src/app.py": "code", "src/lib/util.py": "util", "main.py": "main"}
        tree = _unflatten_tree(flat)
        assert tree["main.py"] == "main"
        assert tree["src"]["app.py"] == "code"
        assert tree["src"]["lib"]["util.py"] == "util"

    def test_roundtrip_with_flatten(self):
        tree = {"a.py": "1", "src": {"b.py": "2", "sub": {"c.py": "3"}}}
        assert _unflatten_tree(flatten_tree(tree)) == tree


class TestSourceTreeCache:
    def test_save_and_load_roundtrip(self, sample_project):
        cache = sample_project / ".rlm-cache"
        tree = load_source_tree(sample_project, project_root=sample_project)
        save_source_tree_cache(tree, cache, sample_project)

        loaded_tree, manifest = load_source_tree_cache(cache)
        assert loaded_tree == tree
        assert manifest["version"] == 1
        assert "files" in manifest
        assert "main.py" in manifest["files"]

    def test_cache_miss_returns_none(self, tmp_path):
        tree, manifest = load_source_tree_cache(tmp_path / "nonexistent")
        assert tree is None
        assert manifest is None

    def test_unchanged_files_use_cache(self, sample_project):
        cache = sample_project / ".rlm-cache"
        # First load populates cache
        tree1 = load_source_tree_cached(sample_project, cache)
        # Second load should use cache
        tree2 = load_source_tree_cached(sample_project, cache)
        assert tree1 == tree2

    def test_modified_file_detected(self, sample_project):
        cache = sample_project / ".rlm-cache"
        tree1 = load_source_tree_cached(sample_project, cache)
        assert tree1["main.py"] == "print('hello')\n"

        # Modify a file (also touch mtime forward to guarantee stat diff)
        import time
        time.sleep(0.05)
        (sample_project / "main.py").write_text("print('changed')\n")

        # Invalidate git hash by clearing it in manifest
        manifest_path = cache / "source_tree.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["git_hash"] = ""
        manifest_path.write_text(json.dumps(manifest))

        tree2 = load_source_tree_cached(sample_project, cache)
        assert tree2["main.py"] == "print('changed')\n"
        # Other files unchanged
        assert tree2["utils.py"] == "def helper(): pass\n"

    def test_new_file_detected(self, sample_project):
        cache = sample_project / ".rlm-cache"
        tree1 = load_source_tree_cached(sample_project, cache)
        assert "new.py" not in flatten_tree(tree1)

        # Add a new file
        (sample_project / "new.py").write_text("new_content\n")

        # Invalidate git hash
        manifest_path = cache / "source_tree.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["git_hash"] = ""
        manifest_path.write_text(json.dumps(manifest))

        tree2 = load_source_tree_cached(sample_project, cache)
        assert tree2["new.py"] == "new_content\n"

    def test_deleted_file_detected(self, sample_project):
        cache = sample_project / ".rlm-cache"
        tree1 = load_source_tree_cached(sample_project, cache)
        assert "utils.py" in tree1

        # Delete a file
        (sample_project / "utils.py").unlink()

        # Invalidate git hash
        manifest_path = cache / "source_tree.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["git_hash"] = ""
        manifest_path.write_text(json.dumps(manifest))

        tree2 = load_source_tree_cached(sample_project, cache)
        assert "utils.py" not in tree2
