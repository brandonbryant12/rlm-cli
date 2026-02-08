"""Configuration loading, resolution, and persistence.

Config precedence (highest wins):
  CLI flags → env vars → project .rlm-cli.json → global config → defaults
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "rlm-cli" / "config.json"
PROJECT_CONFIG_NAME = ".rlm-cli.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "smart_model": "anthropic/claude-sonnet-4-5",
    "small_model": "anthropic/claude-haiku-4-5",
    "api_base_url": None,
    "api_key": None,
    "max_iterations": 35,
    "max_output_chars": 8192,
    "max_llm_calls": 50,
    "cache_dir": ".rlm-cache",
}

ENV_API_KEY = "RLM_API_KEY"
ENV_API_BASE = "RLM_API_BASE"
ENV_SMART_MODEL = "RLM_SMART_MODEL"
ENV_SMALL_MODEL = "RLM_SMALL_MODEL"


def load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def find_project_config(start: Path) -> Optional[Path]:
    """Walk up from *start* looking for .rlm-cli.json, stopping at .git."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        candidate = parent / PROJECT_CONFIG_NAME
        if candidate.exists():
            return candidate
        if (parent / ".git").exists():
            break
    return None


def resolve_config(
    project_dir: Path | None = None,
    cli_overrides: dict | None = None,
) -> dict:
    """Merge config: defaults < global < project < env < CLI."""
    cfg = dict(DEFAULT_CONFIG)

    cfg.update({k: v for k, v in load_json(DEFAULT_CONFIG_PATH).items() if v is not None})

    anchor = (project_dir or Path.cwd()).resolve()
    proj_path = find_project_config(anchor)
    if proj_path:
        cfg.update({k: v for k, v in load_json(proj_path).items() if v is not None})

    if os.environ.get(ENV_API_KEY):
        cfg["api_key"] = os.environ[ENV_API_KEY]
    if os.environ.get(ENV_API_BASE):
        cfg["api_base_url"] = os.environ[ENV_API_BASE]
    if os.environ.get(ENV_SMART_MODEL):
        cfg["smart_model"] = os.environ[ENV_SMART_MODEL]
    if os.environ.get(ENV_SMALL_MODEL):
        cfg["small_model"] = os.environ[ENV_SMALL_MODEL]

    if not cfg.get("api_key"):
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
            if os.environ.get(var):
                cfg["api_key"] = os.environ[var]
                break

    if cli_overrides:
        cfg.update({k: v for k, v in cli_overrides.items() if v is not None})

    return cfg


def save_config(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def resolve_project_root(directory: str) -> Path:
    root = Path(directory).resolve()
    if not root.is_dir():
        raise SystemExit(f"Error: {root} is not a directory.")
    return root


def resolve_cache_dir(project_root: Path, cfg: dict) -> Path:
    raw = cfg.get("cache_dir", ".rlm-cache")
    p = Path(raw)
    return p if p.is_absolute() else project_root / p


def build_cfg(project_root: Path, smart_model, small_model, api_base, api_key,
              max_iterations, max_output_chars, max_llm_calls, cache_dir, **_) -> dict:
    """Build resolved config from CLI kwargs, merging with file/env config."""
    overrides: dict[str, Any] = {}
    if smart_model:
        overrides["smart_model"] = smart_model
    if small_model:
        overrides["small_model"] = small_model
    if api_base:
        overrides["api_base_url"] = api_base
    if api_key:
        overrides["api_key"] = api_key
    if max_iterations is not None:
        overrides["max_iterations"] = max_iterations
    if max_output_chars is not None:
        overrides["max_output_chars"] = max_output_chars
    if max_llm_calls is not None:
        overrides["max_llm_calls"] = max_llm_calls
    if cache_dir:
        overrides["cache_dir"] = cache_dir
    return resolve_config(project_dir=project_root, cli_overrides=overrides)
