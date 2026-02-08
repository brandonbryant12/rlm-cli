"""Output formatting, writing, cost reporting, and tree summary."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click


def write_output(content: str, output_path: Optional[str], task: str, project_root: Path):
    """Write to a file (resolved relative to project_root) or stdout."""
    if output_path:
        p = Path(output_path)
        if not p.is_absolute():
            p = project_root / p
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        click.echo(f"✓ {task} written → {p}", err=True)
    else:
        click.echo(content)


def format_result(
    content: str, cost_info: dict, task: str, cfg: dict, elapsed: float, fmt: str = "markdown",
) -> str:
    """Wrap analysis content with metadata."""
    if fmt == "json":
        return json.dumps({
            "task": task,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": cfg["smart_model"],
            "sub_model": cfg.get("small_model", cfg["smart_model"]),
            "max_iterations": cfg.get("max_iterations"),
            "elapsed_seconds": round(elapsed, 1),
            "cost": cost_info,
            "analysis": content,
        }, indent=2)

    header = (
        f"<!-- rlm-cli {task} | {datetime.now(timezone.utc).isoformat()} "
        f"| model={cfg['smart_model']} | iter={cfg.get('max_iterations')} "
        f"| elapsed={elapsed:.0f}s | cost=${cost_info.get('total_cost_usd', 0):.4f} -->\n\n"
    )
    return header + content


def print_cost_summary(cost_info: dict, elapsed: float):
    """Print cost/performance summary to stderr."""
    click.echo(f"\n── Cost Summary ──", err=True)
    click.echo(
        f"  Smart model:  {cost_info['smart_model_calls']} calls  "
        f"({cost_info['smart_model_tokens_in']:,} in / "
        f"{cost_info['smart_model_tokens_out']:,} out)",
        err=True,
    )
    if cost_info["sub_model_calls"] > 0:
        click.echo(
            f"  Sub model:    {cost_info['sub_model_calls']} calls  "
            f"({cost_info['sub_model_tokens_in']:,} in / "
            f"{cost_info['sub_model_tokens_out']:,} out)",
            err=True,
        )
    total_tokens = (
        cost_info["smart_model_tokens_in"] + cost_info["smart_model_tokens_out"]
        + cost_info["sub_model_tokens_in"] + cost_info["sub_model_tokens_out"]
    )
    click.echo(f"  Total tokens: {total_tokens:,}", err=True)
    click.echo(f"  Total cost:   ${cost_info['total_cost_usd']:.4f}", err=True)
    click.echo(f"  Elapsed:      {elapsed:.1f}s", err=True)


def iter_files(tree: dict, prefix: str = ""):
    """Yield all file paths from a nested source tree."""
    for key, value in tree.items():
        path = f"{prefix}/{key}" if prefix else key
        if isinstance(value, dict):
            yield from iter_files(value, path)
        else:
            yield path


def tree_summary(tree: dict) -> dict:
    """Quick stats about a loaded source tree."""
    files = list(iter_files(tree))
    ext_counts: Counter = Counter()
    for f in files:
        name = f.rsplit("/", 1)[-1] if "/" in f else f
        ext = "." + name.rsplit(".", 1)[1] if "." in name else "(none)"
        ext_counts[ext] += 1

    def _sum_sizes(t: dict) -> int:
        return sum(
            _sum_sizes(v) if isinstance(v, dict) else len(v) if isinstance(v, str) else 0
            for v in t.values()
        )

    return {
        "file_count": len(files),
        "total_chars": _sum_sizes(tree),
        "extensions": dict(ext_counts.most_common(15)),
    }


def warn_model_choice(model: str):
    """Warn if the smart model is unlikely to work well with RLM."""
    if model.startswith("ollama/"):
        return
    normalized = model.lower()
    good = ("claude", "gpt-5", "gpt-4o", "gemini", "qwen", "coder", "o3", "o4")
    if any(k in normalized for k in good):
        return
    click.echo(
        f"⚠ Warning: '{model}' may not work well as an RLM smart model.\n"
        f"  RLMs require models with strong code generation ability.\n"
        f"  Recommended: claude-sonnet-4-5, gpt-5, gemini-2.5-flash, qwen3-coder\n",
        err=True,
    )


def print_run_header(cfg: dict, project_root: Path):
    click.echo(
        f"Models:   smart={cfg['smart_model']}  "
        f"small={cfg.get('small_model', cfg['smart_model'])}",
        err=True,
    )
    if cfg.get("api_base_url"):
        click.echo(f"Endpoint: {cfg['api_base_url']}", err=True)
    click.echo(f"Scoped:   {project_root}", err=True)
    click.echo(
        f"Limits:   iterations={cfg.get('max_iterations')}  "
        f"output_chars={cfg.get('max_output_chars', 8192)}  "
        f"llm_calls={cfg.get('max_llm_calls', 50)}",
        err=True,
    )
