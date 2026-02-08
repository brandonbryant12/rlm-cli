"""Click CLI commands — thin wrappers that compose the other modules."""

import json
import sys
import time
from pathlib import Path
from typing import Any

import click

from . import __version__
from .config import (
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_PATH,
    ENV_API_KEY,
    PROJECT_CONFIG_NAME,
    build_cfg,
    load_json,
    resolve_cache_dir,
    resolve_config,
    resolve_project_root,
    save_config,
)
from .engine import build_rlm, collect_cost, configure_lm, save_trace
from .loader import (
    GitignoreFilter,
    get_changed_files,
    hash_tree,
    load_baseline,
    load_changed_tree,
    load_source_tree,
    read_files_from,
    save_baseline,
)
from .output import (
    format_result,
    iter_files,
    print_cost_summary,
    print_run_header,
    tree_summary,
    warn_model_choice,
    write_output,
)
from .signatures import (
    TASK_OUTPUT_FIELD,
    TASK_SIGNATURES,
    DebugAnalysis,
    FreeformQuery,
    IncrementalRefresh,
)

EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_API_ERROR = 2
EXIT_CRITICAL_FINDINGS = 3


def common_options(f):
    """Decorator that adds model / limit / format flags shared by all analysis commands."""
    f = click.option("--smart-model", default=None, help="Override smart/primary model.")(f)
    f = click.option("--small-model", default=None, help="Override small/sub model.")(f)
    f = click.option("--api-base", default=None, help="OpenAI-compatible endpoint URL.")(f)
    f = click.option("--api-key", default=None, help="Auth token (or set $RLM_API_KEY).")(f)
    f = click.option("--max-iterations", default=None, type=int, help="Max RLM iterations.")(f)
    f = click.option("--max-output-chars", default=None, type=int,
                      help="Max REPL output chars per iteration (default: 8192).")(f)
    f = click.option("--max-llm-calls", default=None, type=int,
                      help="Max sub-LLM calls per run (default: 50).")(f)
    f = click.option("--cache-dir", default=None, help="Cache directory (relative to project).")(f)
    f = click.option("--format", "fmt", type=click.Choice(["markdown", "json"]),
                      default="markdown", help="Output format.")(f)
    f = click.option("-v", "--verbose", is_flag=True, help="Show RLM trace output.")(f)
    return f


def _run_rlm(cfg, sig, source_tree, rlm_inputs, output_field, task_label, root, verbose=False):
    """Shared logic: configure LM, build+run RLM, collect cost, format result.

    Returns (formatted_content, cost_info, elapsed, lm, sub_lm).
    """
    warn_model_choice(cfg["smart_model"])
    print_run_header(cfg, root)
    try:
        lm, sub_lm = configure_lm(cfg)
    except Exception as e:
        click.echo(f"Error configuring LLM: {e}", err=True)
        sys.exit(EXIT_API_ERROR)
    click.echo(f"Running {task_label} ...", err=True)
    t0 = time.time()
    try:
        rlm = build_rlm(sig, cfg, sub_lm, source_tree, verbose=verbose)
        result = rlm(**rlm_inputs)
    except Exception as e:
        click.echo(f"Error during {task_label}: {e}", err=True)
        sys.exit(EXIT_API_ERROR)
    elapsed = time.time() - t0
    content = getattr(result, output_field)
    cost_info = collect_cost(lm, sub_lm)
    print_cost_summary(cost_info, elapsed)
    return content, cost_info, elapsed, lm, sub_lm


@click.group()
@click.version_option(version=__version__)
def cli():
    """rlm-cli — Deep codebase analysis powered by Recursive Language Models.

    All operations are scoped to the directory you pass (defaults to cwd).
    Config files, cache, and .gitignore resolution never leak outside it.

    \b
    Exit codes:
      0  Success
      1  Configuration or usage error
      2  API / LLM error (retryable)
      3  Analysis found critical severity findings
    """


@cli.group()
def config():
    """Manage rlm-cli configuration."""


@config.command("init")
@click.option("--global", "is_global", is_flag=True,
              help="Create/update global config (~/.config/rlm-cli/config.json).")
@click.option("--project", is_flag=True,
              help="Create/update project config (.rlm-cli.json in cwd).")
def config_init(is_global, project):
    """Interactively initialise configuration."""
    if not is_global and not project:
        click.echo("Specify --global or --project.", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    path = DEFAULT_CONFIG_PATH if is_global else Path.cwd() / PROJECT_CONFIG_NAME
    existing = load_json(path)
    scope = "Global" if is_global else "Project"

    click.echo(f"\n{scope} config → {path}\n")

    data: dict[str, Any] = {}
    data["smart_model"] = click.prompt(
        "Smart model (main analysis)",
        default=existing.get("smart_model", DEFAULT_CONFIG["smart_model"]),
    )
    data["small_model"] = click.prompt(
        "Small model (sub-queries, cheaper)",
        default=existing.get("small_model", DEFAULT_CONFIG["small_model"]),
    )
    key = click.prompt(
        "API key (leave blank to use env var)",
        default=existing.get("api_key", ""), show_default=False,
    )
    if key:
        data["api_key"] = key
    base = click.prompt(
        "API base URL (blank = provider default)",
        default=existing.get("api_base_url", ""), show_default=False,
    )
    if base:
        data["api_base_url"] = base
    data["max_iterations"] = click.prompt(
        "Max iterations", type=int,
        default=existing.get("max_iterations", DEFAULT_CONFIG["max_iterations"]),
    )
    data["max_output_chars"] = click.prompt(
        "Max output chars per iteration", type=int,
        default=existing.get("max_output_chars", DEFAULT_CONFIG["max_output_chars"]),
    )
    data["max_llm_calls"] = click.prompt(
        "Max sub-LLM calls per run", type=int,
        default=existing.get("max_llm_calls", DEFAULT_CONFIG["max_llm_calls"]),
    )
    save_config(path, data)
    click.echo(f"\n✓ Saved → {path}")


@config.command("show")
@click.argument("directory", default=".", type=click.Path(exists=True))
def config_show(directory):
    """Show resolved config for a directory."""
    root = resolve_project_root(directory)
    cfg = resolve_config(project_dir=root)
    safe = dict(cfg)
    if safe.get("api_key"):
        safe["api_key"] = safe["api_key"][:8] + "..."
    click.echo(json.dumps(safe, indent=2))


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--global", "is_global", is_flag=True, help="Set in global config.")
@click.option("--project", is_flag=True, help="Set in project config (cwd).")
def config_set(key, value, is_global, project):
    """Set a single config value."""
    valid_keys = set(DEFAULT_CONFIG.keys())
    if key not in valid_keys:
        click.echo(f"Unknown key '{key}'. Valid: {', '.join(sorted(valid_keys))}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)
    if key in ("max_iterations", "max_output_chars", "max_llm_calls"):
        try:
            value = int(value)
        except ValueError:
            click.echo(f"Error: '{key}' must be an integer, got '{value}'.", err=True)
            sys.exit(EXIT_CONFIG_ERROR)
    if is_global:
        path = DEFAULT_CONFIG_PATH
    elif project:
        path = Path.cwd() / PROJECT_CONFIG_NAME
    else:
        click.echo("Specify --global or --project.", err=True)
        sys.exit(EXIT_CONFIG_ERROR)
    data = load_json(path)
    data[key] = value
    save_config(path, data)
    click.echo(f"✓ {key} = {value!r} → {path}")


@config.command("path")
def config_path():
    """Print config file locations."""
    click.echo(f"Global:  {DEFAULT_CONFIG_PATH}")
    click.echo(f"Project: {Path.cwd() / PROJECT_CONFIG_NAME}")


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("--no-gitignore", is_flag=True, help="Don't respect .gitignore files.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text", help="Output format.")
def tree(directory, no_gitignore, fmt):
    """Preview what files would be analyzed (no LLM calls)."""
    root = resolve_project_root(directory)
    gi = None if no_gitignore else GitignoreFilter(root)
    source_tree = load_source_tree(root, gi, project_root=root)
    stats = tree_summary(source_tree)
    if fmt == "json":
        stats["files"] = sorted(iter_files(source_tree))
        click.echo(json.dumps(stats, indent=2))
    else:
        click.echo(f"Project: {root}")
        click.echo(f"Files:   {stats['file_count']}")
        click.echo(f"Size:    {stats['total_chars']:,} chars "
                    f"(~{stats['total_chars'] // 4:,} tokens)")
        click.echo(f"\nBy extension:")
        for ext, count in stats["extensions"].items():
            click.echo(f"  {ext:12s}  {count:4d} files")
        click.echo(f"\nFiles:")
        for f in sorted(iter_files(source_tree)):
            click.echo(f"  {f}")


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-t", "--task", type=click.Choice(list(TASK_SIGNATURES)),
              required=True, help="Analysis type.")
@click.option("-o", "--output", default=None, type=click.Path(),
              help="Output file (relative to project dir).")
@click.option("--no-cache", is_flag=True, help="Skip saving a baseline.")
@click.option("--no-gitignore", is_flag=True, help="Don't respect .gitignore files.")
@click.option("--dry-run", is_flag=True,
              help="Show what would be analyzed without calling any LLM.")
@common_options
def scan(directory, task, output, no_cache, no_gitignore, dry_run, **kwargs):
    """Run a full RLM analysis on a codebase."""
    root = resolve_project_root(directory)
    cfg = build_cfg(root, **kwargs)
    cfg.setdefault("max_iterations", 35)
    cache = resolve_cache_dir(root, cfg)
    fmt = kwargs.get("fmt", "markdown")
    gi = None if no_gitignore else GitignoreFilter(root)
    click.echo(f"Loading source tree from {root} ...", err=True)
    source_tree = load_source_tree(root, gi, project_root=root)
    stats = tree_summary(source_tree)
    click.echo(
        f"  → {stats['file_count']} files loaded "
        f"({stats['total_chars']:,} chars, ~{stats['total_chars'] // 4:,} tokens)",
        err=True,
    )
    if dry_run:
        click.echo(f"\n[DRY RUN] Would run '{task}' analysis with:", err=True)
        print_run_header(cfg, root)
        click.echo(f"\nNo LLM calls made. Use 'rlm-cli tree .' for file list.", err=True)
        return
    sig = TASK_SIGNATURES[task]
    field = TASK_OUTPUT_FIELD[task]
    content, cost_info, elapsed, lm, _ = _run_rlm(
        cfg, sig, source_tree, {"source_tree": source_tree},
        field, f"{task} analysis", root, verbose=kwargs.get("verbose", False),
    )
    formatted = format_result(content, cost_info, task, cfg, elapsed, fmt)
    write_output(formatted, output, task, root)
    if kwargs.get("verbose"):
        save_trace(lm, cache, task)
    if not no_cache:
        save_baseline(formatted, cache, task, hash_tree(source_tree), cost_info)


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-t", "--task", type=click.Choice(list(TASK_SIGNATURES)),
              required=True, help="Analysis type.")
@click.option("--since", default=None, help="Git ref to diff against (default: HEAD~1).")
@click.option("--files-from", "files_from", default=None,
              help="File list: path, comma-separated, or '-' for stdin.")
@click.option("-o", "--output", default=None, type=click.Path(), help="Output file.")
@click.option("--baseline", default=None, type=click.Path(exists=True),
              help="Explicit baseline file.")
@click.option("--no-gitignore", is_flag=True, help="Don't respect .gitignore files.")
@common_options
def refresh(directory, task, since, files_from, output, baseline, no_gitignore, **kwargs):
    """Incrementally refresh a previous analysis."""
    root = resolve_project_root(directory)
    cfg = build_cfg(root, **kwargs)
    cfg.setdefault("max_iterations", 20)
    cache = resolve_cache_dir(root, cfg)
    fmt = kwargs.get("fmt", "markdown")
    if baseline:
        prev = Path(baseline).read_text(encoding="utf-8")
    else:
        prev = load_baseline(cache, task)
    if not prev:
        click.echo("No baseline found. Run 'scan' first or provide --baseline.", err=True)
        sys.exit(EXIT_CONFIG_ERROR)
    if files_from:
        changed = read_files_from(files_from)
        click.echo(f"Files from explicit list: {len(changed)}", err=True)
    else:
        click.echo(f"Computing diff (since={since or 'HEAD~1'}) ...", err=True)
        changed = get_changed_files(root, since)
    if not changed:
        click.echo("No changed files detected. Analysis is current.")
        return
    click.echo(f"  → {len(changed)} files changed", err=True)
    for f in changed[:15]:
        click.echo(f"    {f}", err=True)
    if len(changed) > 15:
        click.echo(f"    ... and {len(changed) - 15} more", err=True)
    changed_tree = load_changed_tree(root, changed)
    rlm_inputs = {"previous_analysis": prev, "changed_files": changed_tree, "task_type": task}
    content, cost_info, elapsed, _, _ = _run_rlm(
        cfg, IncrementalRefresh, changed_tree, rlm_inputs,
        "updated_analysis", f"incremental {task} refresh", root,
        verbose=kwargs.get("verbose", False),
    )
    formatted = format_result(content, cost_info, task, cfg, elapsed, fmt)
    write_output(formatted, output, task, root)
    gi = None if no_gitignore else GitignoreFilter(root)
    full_tree = load_source_tree(root, gi, project_root=root)
    save_baseline(content, cache, task, hash_tree(full_tree), cost_info)


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-d", "--description", "bug_description", required=True,
              help="Description of the bug to investigate.")
@click.option("-o", "--output", default=None, type=click.Path(), help="Output file.")
@click.option("--no-gitignore", is_flag=True, help="Don't respect .gitignore files.")
@common_options
def debug(directory, bug_description, output, no_gitignore, **kwargs):
    """Trace and debug an issue through the codebase."""
    root = resolve_project_root(directory)
    cfg = build_cfg(root, **kwargs)
    cfg.setdefault("max_iterations", 35)
    fmt = kwargs.get("fmt", "markdown")
    gi = None if no_gitignore else GitignoreFilter(root)
    click.echo(f"Loading source tree from {root} ...", err=True)
    source_tree = load_source_tree(root, gi, project_root=root)
    desc_preview = bug_description[:80] + ("..." if len(bug_description) > 80 else "")
    click.echo(f"Debugging: {desc_preview}", err=True)
    content, cost_info, elapsed, _, _ = _run_rlm(
        cfg, DebugAnalysis, source_tree,
        {"source_tree": source_tree, "bug_description": bug_description},
        "analysis", "debug analysis", root, verbose=kwargs.get("verbose", False),
    )
    formatted = format_result(content, cost_info, "debug", cfg, elapsed, fmt)
    write_output(formatted, output, "debug", root)


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-q", "--question", required=True,
              help="Question to ask about the codebase.")
@click.option("-o", "--output", default=None, type=click.Path(), help="Output file.")
@click.option("--no-gitignore", is_flag=True, help="Don't respect .gitignore files.")
@common_options
def ask(directory, question, output, no_gitignore, **kwargs):
    """Ask a freeform question about the codebase."""
    root = resolve_project_root(directory)
    cfg = build_cfg(root, **kwargs)
    cfg.setdefault("max_iterations", 25)
    fmt = kwargs.get("fmt", "markdown")
    gi = None if no_gitignore else GitignoreFilter(root)
    click.echo(f"Loading source tree from {root} ...", err=True)
    source_tree = load_source_tree(root, gi, project_root=root)
    q_preview = question[:80] + ("..." if len(question) > 80 else "")
    click.echo(f"Question: {q_preview}", err=True)
    content, cost_info, elapsed, _, _ = _run_rlm(
        cfg, FreeformQuery, source_tree,
        {"source_tree": source_tree, "question": question},
        "answer", "freeform query", root, verbose=kwargs.get("verbose", False),
    )
    formatted = format_result(content, cost_info, "ask", cfg, elapsed, fmt)
    write_output(formatted, output, "ask", root)


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("--cache-dir", default=None, help="Cache directory override.")
@click.option("--no-gitignore", is_flag=True, help="Don't respect .gitignore files.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text", help="Output format.")
def status(directory, cache_dir, no_gitignore, fmt):
    """Show cached baselines and their freshness."""
    root = resolve_project_root(directory)
    cfg = resolve_config(project_dir=root)
    if cache_dir:
        cfg["cache_dir"] = cache_dir
    cache = resolve_cache_dir(root, cfg)
    if not cache.exists():
        if fmt == "json":
            click.echo(json.dumps({"baselines": []}))
        else:
            click.echo("No cache directory found. Run 'scan' first.")
        return
    gi = None if no_gitignore else GitignoreFilter(root)
    source_tree = load_source_tree(root, gi, project_root=root)
    current_hash = hash_tree(source_tree)
    baselines = []
    for meta_file in sorted(cache.glob("*.meta.json")):
        meta = json.loads(meta_file.read_text())
        is_current = meta["tree_hash"] == current_hash
        entry: dict[str, Any] = {
            "task": meta["task"],
            "timestamp": meta["timestamp"],
            "current": is_current,
            "tree_hash": meta["tree_hash"],
        }
        if "cost" in meta:
            entry["cost"] = meta["cost"]
        baselines.append(entry)
    if fmt == "json":
        click.echo(json.dumps({"current_hash": current_hash, "baselines": baselines}, indent=2))
    else:
        if not baselines:
            click.echo("No baselines cached yet.")
            return
        for b in baselines:
            stale = "✓ current" if b["current"] else "✗ STALE"
            cost_str = ""
            if "cost" in b:
                cost_str = f"  ${b['cost'].get('total_cost_usd', 0):.4f}"
            click.echo(f"  {b['task']:15s}  {b['timestamp']}  [{stale}]{cost_str}")
