# Architecture

## The core idea

LLMs degrade when you fill their context window ("context rot"). Instead of stuffing source code into the prompt, an RLM stores the codebase as a Python variable in a sandboxed REPL and lets the model write code to explore it iteratively:

1. Model sees metadata + tool descriptions (not the full codebase)
2. Model writes Python: `grep_tree("password", max_results=20)`
3. Sandbox executes it, returns results
4. Model reasons, writes more code
5. Repeat until `FINAL(answer)`

The model can also call `llm_query("summarize this chunk")` inside the REPL, spawning sub-LLM calls — that's the "recursive" part.

**We build the wrapper. DSPy builds the REPL loop.**

## How a scan works end-to-end

```
$ rlm-cli scan ./my-project -t security
```

1. **loader.py** walks filesystem → nested dict of `{filename: content}`. Respects .gitignore at every level, skips binaries/node_modules, blocks symlink escapes outside project root.
2. **config.py** merges 5 config layers: defaults → global → project → env vars → CLI flags.
3. **tools.py** builds 5 closure-based tool functions over the source tree dict. These are plain Python with type annotations and docstrings (required by dspy.RLM).
4. **engine.py** calls `dspy.RLM(signature, tools=tools_list, max_iterations=35, ...)`. DSPy handles the REPL loop.
5. **output.py** formats results as markdown or JSON with metadata header. **loader.py** caches the baseline for incremental refresh.

## Module dependency graph

```
cli.py
  ├── config.py
  ├── loader.py
  ├── engine.py
  │   └── tools.py
  ├── output.py
  └── signatures.py
```

## Design decisions

- **No runtime version checks.** The `dspy>=3.1.2` pin in pyproject.toml is the contract.
- **All commands go through `build_rlm()`.** Single construction point in engine.py.
- **Tools are closures.** `make_repl_tools(source_tree)` returns 5 functions that close over a flattened `{path: content}` dict.
- **Config is immutable per run.** Built once by `build_cfg()`, threaded through as a plain dict.
- **stderr for humans, stdout for machines.** Every `click.echo(..., err=True)` is progress. Only the final analysis goes to stdout.
