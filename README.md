# rlm-cli

Deep codebase analysis powered by DSPy's Recursive Language Models.

Instead of stuffing source code into a prompt, `rlm-cli` loads your codebase into a sandboxed Python REPL and lets the model explore it iteratively — grepping for patterns, reading files, computing stats — avoiding context window degradation.

## Install

```bash
pip install -e .
# or
uv pip install -e .
```

Requires Python 3.11+ and `dspy>=3.1.3`.

## Quick start

```bash
# Preview what files would be analyzed (no LLM calls)
rlm-cli tree .

# Run a security audit
rlm-cli scan . -t security

# Architecture review
rlm-cli scan . -t architecture

# Code review
rlm-cli scan . -t review

# Generate documentation
rlm-cli scan . -t documentation

# Debug a specific issue
rlm-cli debug . -d "users can't log in after password reset"

# Ask a question about the codebase
rlm-cli ask . -q "how does authentication work?"

# Incremental refresh (only re-analyze changed files)
rlm-cli refresh . -t security
```

## Configuration

Config is resolved in layers (highest wins):

1. CLI flags
2. Environment variables (`RLM_API_KEY`, `RLM_SMART_MODEL`, etc.)
3. Project config (`.rlm-cli.json`)
4. Global config (`~/.config/rlm-cli/config.json`)
5. Defaults

```bash
# Interactive setup
rlm-cli config init --global

# Set a single value
rlm-cli config set smart_model anthropic/claude-sonnet-4-5 --global

# Show resolved config
rlm-cli config show .
```

## Commands

| Command | LLM calls | Purpose |
|---|---|---|
| `rlm-cli tree .` | 0 | Preview files that would be analyzed |
| `rlm-cli status .` | 0 | Show cached baselines and freshness |
| `rlm-cli config init/show/set/path` | 0 | Manage configuration |
| `rlm-cli scan . -t security` | $$$ | Full analysis from scratch |
| `rlm-cli refresh . -t security` | $ | Incremental update from git diff |
| `rlm-cli debug . -d "bug desc"` | $$$ | Root cause analysis |
| `rlm-cli ask . -q "question"` | $$ | Freeform codebase Q&A |

## How it works

1. **Loader** walks the filesystem into a nested dict, respecting `.gitignore` at every level
2. **Tools** (grep, list, stats, read, imports) are injected into DSPy's RLM sandbox
3. **DSPy RLM** runs the model in a loop: model writes Python code, sandbox executes it, model reasons on results
4. The model can call `llm_query()` inside the REPL for sub-analysis (the "recursive" part)
5. Results are formatted as markdown or JSON with cost metadata

## License

MIT
