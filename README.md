# rlm-cli

Deep codebase analysis powered by DSPy's Recursive Language Models.

Instead of stuffing source code into a prompt, `rlm-cli` loads your codebase into a sandboxed Python REPL and lets the model explore it iteratively — grepping for patterns, reading files, computing stats — avoiding context window degradation.

## What is an RLM?

Most LLM-based code tools work by dumping entire files into a prompt and asking for an answer. This hits hard limits fast — context windows fill up, the model loses focus on large codebases, and you pay for tokens the model never needed to see.

A **Recursive Language Model (RLM)**, introduced in DSPy, flips this: instead of reading everything up front, the model gets a sandboxed Python REPL and a set of tools, then *explores the codebase on its own terms*. It decides what to grep for, which files to read, what stats to compute — iterating in a loop until it has enough evidence to answer.

The "recursive" part means the model can call `llm_query()` *inside* the REPL to spin up sub-analyses. For example, while doing a security audit the outer model might discover an auth module, then call `llm_query("analyze this JWT implementation for vulnerabilities")` to get a focused sub-review — all within the same sandboxed session.

In practice this means `rlm-cli` can analyze codebases far larger than any context window because the model only loads what it needs, when it needs it.

## Install

Requires Python 3.11+ and `dspy>=3.1.3`.

### Global link (recommended for development)

Like `pnpm link --global` — installs the CLI globally while keeping it symlinked to your local source so edits take effect immediately:

```bash
# from the rlm-cli repo root:
pip install -e .
# or with uv:
uv pip install -e .
```

Now `rlm-cli` is available everywhere:

```bash
cd ~/any-other-project
rlm-cli tree .
rlm-cli scan . -t security
```

Changes you make to the source in this repo are picked up instantly — no reinstall needed.

### Global install (standalone)

If you just want to use the tool without keeping the source around:

```bash
# pipx (isolated environment, no dependency conflicts)
pipx install git+https://github.com/YOUR_USER/rlm-cli.git

# uv tool
uv tool install git+https://github.com/YOUR_USER/rlm-cli.git

# plain pip
pip install git+https://github.com/YOUR_USER/rlm-cli.git
```

### Global config

Set up once so your API key and model preferences follow you across projects:

```bash
rlm-cli config init --global   # interactive setup → ~/.config/rlm-cli/config.json
# or set values directly:
rlm-cli config set api_key sk-... --global
rlm-cli config set smart_model anthropic/claude-sonnet-4-5 --global
```

Per-project overrides still work — drop a `.rlm-cli.json` in any repo to customize behavior for that codebase.

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
