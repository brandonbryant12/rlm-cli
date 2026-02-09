"""Source tree loading, .gitignore filtering, git helpers, and caching."""

import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click

ALWAYS_SKIP_DIRS = {
    ".git", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    ".egg-info", ".idea", ".vscode", "node_modules", ".next",
    ".nuxt", "vendor", ".bundle", ".terraform", ".rlm-cache",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".lock", ".sum", ".map",
}

MAX_FILE_SIZE = 256 * 1024

# Sentinel prefix for non-content entries in the source tree.
# Uses a prefix that cannot appear at the start of any real file content.
SENTINEL_PREFIX = "\x00RLM:"


class GitignoreFilter:
    """Respects .gitignore files at every directory level."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._cache: dict[Path, list[str]] = {}

    def _load_patterns(self, directory: Path) -> list[str]:
        if directory in self._cache:
            return self._cache[directory]
        patterns: list[str] = []
        gitignore = directory / ".gitignore"
        if gitignore.is_file():
            try:
                for line in gitignore.read_text(errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
            except OSError:
                pass
        self._cache[directory] = patterns
        return patterns

    def _collect_patterns(self, directory: Path) -> list[tuple[Path, str]]:
        chain: list[tuple[Path, str]] = []
        try:
            rel = directory.resolve().relative_to(self.root)
        except ValueError:
            return chain
        current = self.root
        for pattern in self._load_patterns(current):
            chain.append((current, pattern))
        for part in rel.parts:
            current = current / part
            for pattern in self._load_patterns(current):
                chain.append((current, pattern))
        return chain

    def is_ignored(self, path: Path) -> bool:
        path = path.resolve()
        parent = path.parent
        try:
            path.relative_to(self.root)
        except ValueError:
            return False
        name = path.name
        ignored = False
        for base_dir, pattern in self._collect_patterns(parent):
            negated = False
            p = pattern
            if p.startswith("!"):
                negated = True
                p = p[1:]
            if "/" in p.rstrip("/"):
                try:
                    rel_to_base = str(path.relative_to(base_dir))
                except ValueError:
                    continue
                p_clean = p.lstrip("/")
                if p_clean.endswith("/"):
                    if path.is_dir() and fnmatch.fnmatch(rel_to_base, p_clean.rstrip("/")):
                        ignored = not negated
                elif fnmatch.fnmatch(rel_to_base, p_clean):
                    ignored = not negated
            else:
                p_clean = p.rstrip("/")
                is_dir_pattern = p.endswith("/")
                if is_dir_pattern:
                    if path.is_dir() and fnmatch.fnmatch(name, p_clean):
                        ignored = not negated
                else:
                    if fnmatch.fnmatch(name, p_clean):
                        ignored = not negated
        return ignored


def load_source_tree(
    root_dir: Path,
    gitignore_filter: Optional[GitignoreFilter] = None,
    *,
    project_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Recursively load a directory into a nested dict of file contents.

    *project_root* is the top-level boundary for symlink escape detection.
    """
    tree: dict[str, Any] = {}
    root = root_dir.resolve()
    boundary = (project_root or root_dir).resolve()

    try:
        entries = sorted(os.listdir(root))
    except PermissionError:
        return tree

    for entry in entries:
        path = root / entry

        try:
            real = path.resolve()
            real.relative_to(boundary)
        except (ValueError, OSError):
            continue

        if entry.startswith(".") and entry not in (".env.example",):
            continue
        if entry in ALWAYS_SKIP_DIRS:
            continue
        if gitignore_filter and gitignore_filter.is_ignored(path):
            continue

        if path.is_dir():
            subtree = load_source_tree(path, gitignore_filter, project_root=boundary)
            if subtree:
                tree[entry] = subtree
        elif path.is_file():
            if path.suffix.lower() in SKIP_EXTENSIONS:
                continue
            if entry.endswith((".min.js", ".min.css", ".bundle.js")):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_SIZE:
                tree[entry] = f"{SENTINEL_PREFIX}FILE TOO LARGE: {size:,} bytes"
                continue
            try:
                tree[entry] = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                tree[entry] = f"{SENTINEL_PREFIX}READ ERROR: {e}"

    return tree


def get_changed_files(repo_dir: Path, since: Optional[str] = None) -> list[str]:
    cmd = ["git", "-C", str(repo_dir), "diff", "--name-only", since or "HEAD~1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        return []


def load_changed_tree(root_dir: Path, changed_files: list[str]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    root = root_dir.resolve()
    for rel_path in changed_files:
        full_path = root / rel_path
        try:
            full_path.resolve().relative_to(root)
        except ValueError:
            continue
        if not full_path.exists():
            tree[rel_path] = f"{SENTINEL_PREFIX}DELETED"
            continue
        if full_path.suffix.lower() in SKIP_EXTENSIONS:
            continue
        try:
            tree[rel_path] = full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            tree[rel_path] = f"{SENTINEL_PREFIX}READ ERROR: {e}"
    return tree


def read_files_from(source: str) -> list[str]:
    """Read a file list from a path, stdin ('-'), or comma-separated string."""
    if source == "-":
        return [line.strip() for line in sys.stdin if line.strip()]
    p = Path(source)
    if p.exists():
        return [line.strip() for line in p.read_text().splitlines() if line.strip()]
    return [f.strip() for f in source.split(",") if f.strip()]


def flatten_tree(tree: dict, prefix: str = "") -> dict[str, str]:
    """Flatten a nested source tree dict into {path: content}."""
    flat: dict[str, str] = {}
    for key, value in tree.items():
        path = f"{prefix}/{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_tree(value, path))
        else:
            flat[path] = value
    return flat


def hash_tree(tree: dict) -> str:
    content = json.dumps(tree, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def hash_tree_fast(root: Path) -> str:
    """Fast hash using git state when available."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        head = result.stdout.strip()
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--stat"],
            capture_output=True, text=True, timeout=5,
        )
        combined = head + diff.stdout
        return hashlib.sha256(combined.encode()).hexdigest()[:12]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def save_baseline(
    content: str,
    cache_dir: Path,
    task: str,
    tree_hash: str,
    cost_info: Optional[dict] = None,
):
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "task": task,
        "tree_hash": tree_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if cost_info:
        meta["cost"] = cost_info
    (cache_dir / f"{task}.baseline.md").write_text(content, encoding="utf-8")
    (cache_dir / f"{task}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    click.echo(f"✓ Baseline cached → {cache_dir}/", err=True)


def load_baseline(cache_dir: Path, task: str) -> Optional[str]:
    path = cache_dir / f"{task}.baseline.md"
    return path.read_text(encoding="utf-8") if path.exists() else None
