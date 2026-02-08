# OpenCode Configuration

## Project context

rlm-cli is a CLI tool using DSPy's Recursive Language Model for deep codebase analysis. Key dependency: `dspy>=3.1.2`.

## Conventions

- Python 3.11+, Click for CLI, DSPy for LLM orchestration
- stderr for progress, stdout for analysis output only
- Exit codes: 0=success, 1=config, 2=API, 3=critical findings
- All tool functions need docstrings + type annotations (DSPy requirement)

## Testing

```bash
pip install -e ".[dev]"
pytest
ruff check .
```
