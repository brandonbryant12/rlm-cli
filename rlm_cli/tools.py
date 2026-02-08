"""Custom REPL tools injected into the RLM's Python interpreter.

These give the model efficient ways to explore the codebase instead of
writing boilerplate dict-traversal code every iteration.
"""

import fnmatch
import re
from collections import Counter
from typing import Any, Callable


def _flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    """Flatten a nested source tree dict into {path: content}."""
    flat: dict[str, str] = {}
    for key, value in tree.items():
        path = f"{prefix}/{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def make_repl_tools(source_tree: dict[str, Any]) -> list[Callable]:
    """Build the tool functions available inside the RLM's REPL."""

    flat_tree = _flatten(source_tree)

    def grep_tree(pattern: str, max_results: int = 50) -> str:
        """Search all files for a regex pattern. Returns matching lines with
        file paths and line numbers. Use for finding: imports, function defs,
        secrets, patterns like 'eval(', 'password', 'TODO', etc.

        Args:
            pattern: A Python regex pattern (case-insensitive).
            max_results: Maximum number of matches to return (default 50).

        Returns:
            Formatted string of matches: "path/file.py:42: matched line"
        """
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex: {e}"
        results = []
        for path, content in flat_tree.items():
            if not isinstance(content, str) or content.startswith("["):
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if compiled.search(line):
                    results.append(f"{path}:{i}: {line.strip()}")
                    if len(results) >= max_results:
                        return "\n".join(results) + f"\n... truncated at {max_results} results"
        return "\n".join(results) if results else "No matches found."

    def list_files(glob_pattern: str = "*") -> str:
        """List all files in the source tree, optionally filtered by glob.

        Args:
            glob_pattern: Glob like "*.py", "test_*", "*.ts" (default: all).

        Returns:
            Sorted file paths with char counts, one per line.
        """
        results = []
        for path, content in flat_tree.items():
            name = path.rsplit("/", 1)[-1] if "/" in path else path
            if glob_pattern != "*" and not fnmatch.fnmatch(name, glob_pattern):
                continue
            size = len(content) if isinstance(content, str) else 0
            results.append(f"{path}  ({size:,} chars)")
        results.sort()
        return "\n".join(results) if results else "No files match that pattern."

    def file_stats() -> str:
        """Get a high-level overview: file count by extension, total lines,
        largest files, and directory structure summary."""
        ext_counts: Counter = Counter()
        ext_lines: Counter = Counter()
        largest: list[tuple[int, str]] = []
        total_files = 0
        total_lines = 0

        for path, content in flat_tree.items():
            total_files += 1
            name = path.rsplit("/", 1)[-1] if "/" in path else path
            ext = "." + name.rsplit(".", 1)[1] if "." in name else "(no ext)"
            ext_counts[ext] += 1
            if isinstance(content, str) and not content.startswith("["):
                lines = content.count("\n") + 1
                ext_lines[ext] += lines
                total_lines += lines
                largest.append((lines, path))

        largest.sort(reverse=True)
        out = [
            f"Total files: {total_files}",
            f"Total lines: {total_lines:,}",
            "",
            "By extension:",
        ]
        for ext, count in ext_counts.most_common(20):
            out.append(f"  {ext:12s}  {count:4d} files  {ext_lines.get(ext, 0):>8,} lines")
        out.append("")
        out.append("Largest files:")
        for lc, path in largest[:15]:
            out.append(f"  {lc:>6,} lines  {path}")

        dirs: Counter = Counter()
        for path in flat_tree:
            parts = path.split("/")
            if len(parts) >= 2:
                dirs[parts[0]] += 1
        out.append("")
        out.append("Top-level directories:")
        for d, count in dirs.most_common(20):
            out.append(f"  {d}/  ({count} files)")
        return "\n".join(out)

    def read_file(path: str) -> str:
        """Read the full contents of a specific file by its path.

        Args:
            path: File path as shown by list_files(), e.g. "src/auth.py".

        Returns:
            The file contents, or an error message if not found.
        """
        if path in flat_tree:
            return flat_tree[path]
        matches = [p for p in flat_tree if p.endswith(path) or path in p]
        if len(matches) == 1:
            return flat_tree[matches[0]]
        if matches:
            return f"Ambiguous path. Matches: {', '.join(matches[:10])}"
        return f"File not found: {path}"

    def find_imports(file_path: str) -> str:
        """Find all import/require statements in a file.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of import statements found.
        """
        content = read_file(file_path)
        if content.startswith(("File not found", "Ambiguous")):
            return content
        imports = []
        for line in content.splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")) and "import" in s:
                imports.append(s)
            elif s.startswith(("require(", "const ")) and ("require(" in s or "from " in s):
                imports.append(s)
            elif s.startswith("use ") and s.endswith(";"):
                imports.append(s)
        return "\n".join(imports) if imports else "No import statements found."

    return [grep_tree, list_files, file_stats, read_file, find_imports]
