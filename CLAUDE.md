# CLAUDE.md — rlm-cli

## What this project is

A CLI tool that uses DSPy's Recursive Language Model (`dspy.RLM`) to perform deep codebase analysis. The model explores code through a sandboxed REPL instead of having code stuffed into its context window.

## Key dependency

`dspy>=3.1.3` — the version where `dspy.RLM` accepts `tools` as `list[Callable]` (PR #9247).

## Architecture

- `config.py` — 5-layer config resolution
- `loader.py` — filesystem walking, .gitignore, git helpers, caching
- `signatures.py` — DSPy Signature classes for each analysis type
- `tools.py` — 5 closure-based REPL tools injected into the RLM sandbox
- `engine.py` — LM setup, `build_rlm()`, cost tracking
- `output.py` — formatting, cost summary, tree stats
- `cli.py` — Click commands (thin wrappers)

## Conventions

- All progress/status → stderr (`click.echo(..., err=True)`)
- Only analysis content → stdout (enables piping)
- Exit codes: 0=success, 1=config error, 2=API error, 3=critical findings
- No runtime version checks — pyproject.toml pin is the contract

## Running

```bash
pip install -e .
rlm-cli tree .        # no LLM calls, test the loader
rlm-cli scan . -t review --dry-run   # test config resolution
rlm-cli scan . -t review             # real analysis (needs API key)
```
