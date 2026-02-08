"""LM configuration, RLM construction, cost tracking, and trace export."""

import json
from pathlib import Path
from typing import Any

import click
import dspy

from .tools import make_repl_tools


def configure_lm(cfg: dict) -> tuple:
    """Create and configure the smart and sub language models."""
    lm_kwargs: dict[str, Any] = {}
    if cfg.get("api_key"):
        lm_kwargs["api_key"] = cfg["api_key"]
    if cfg.get("api_base_url"):
        lm_kwargs["api_base"] = cfg["api_base_url"]

    smart = dspy.LM(cfg["smart_model"], **lm_kwargs)
    dspy.configure(lm=smart)

    sub_lm = None
    if cfg.get("small_model") and cfg["small_model"] != cfg["smart_model"]:
        sub_lm = dspy.LM(cfg["small_model"], **lm_kwargs)

    return smart, sub_lm


def build_rlm(sig, cfg: dict, sub_lm, source_tree: dict, verbose: bool = False):
    """Construct a dspy.RLM with custom REPL tools for codebase exploration."""
    return dspy.RLM(
        sig,
        max_iterations=cfg.get("max_iterations", 35),
        max_output_chars=cfg.get("max_output_chars", 8192),
        max_llm_calls=cfg.get("max_llm_calls", 50),
        sub_lm=sub_lm,
        tools=make_repl_tools(source_tree),
        verbose=verbose,
    )


def collect_cost(smart_lm, sub_lm=None) -> dict:
    """Extract cost/token info from DSPy LM history."""
    info: dict[str, Any] = {
        "smart_model_calls": 0,
        "smart_model_tokens_in": 0,
        "smart_model_tokens_out": 0,
        "sub_model_calls": 0,
        "sub_model_tokens_in": 0,
        "sub_model_tokens_out": 0,
        "total_cost_usd": 0.0,
    }
    try:
        for entry in smart_lm.history:
            info["smart_model_calls"] += 1
            usage = entry.get("usage", {})
            info["smart_model_tokens_in"] += usage.get("prompt_tokens", 0)
            info["smart_model_tokens_out"] += usage.get("completion_tokens", 0)
            info["total_cost_usd"] += entry.get("cost", 0.0) or 0.0
        if sub_lm:
            for entry in sub_lm.history:
                info["sub_model_calls"] += 1
                usage = entry.get("usage", {})
                info["sub_model_tokens_in"] += usage.get("prompt_tokens", 0)
                info["sub_model_tokens_out"] += usage.get("completion_tokens", 0)
                info["total_cost_usd"] += entry.get("cost", 0.0) or 0.0
    except (AttributeError, TypeError):
        pass
    return info


def save_trace(smart_lm, cache_dir: Path, task: str):
    """Dump the full RLM trajectory to a JSON file for debugging."""
    try:
        trace = [
            {
                "model": entry.get("model", ""),
                "messages": entry.get("messages", []),
                "outputs": entry.get("outputs", []),
                "usage": entry.get("usage", {}),
                "cost": entry.get("cost", 0),
            }
            for entry in smart_lm.history
        ]
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{task}.trace.json"
        path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
        click.echo(f"✓ Trace saved → {path}", err=True)
    except (AttributeError, TypeError, OSError):
        pass
