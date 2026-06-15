# 🌳 PyCallGraph — Python Call Graph Generator

A command-line tool that analyzes Python source code and generates interactive call graph visualizations. Starting from a specified entry function, it traces all function calls across multiple files and produces a tree diagram.

## Features

- **AST-Based Analysis** — Uses Python's `ast` module for accurate parsing (no execution needed)
- **Cross-File Tracing** — Follows imports across modules and packages
- **Multiple Output Formats**:
  - 📊 **Interactive HTML** — D3.js-powered collapsible tree with zoom, search, and details panel
  - 📝 **Mermaid Markdown** — Renders in GitHub, VS Code, and other Markdown viewers  
  - 📦 **JSON** — Raw tree data for programmatic use
- **Smart Resolution** — Resolves function calls through imports, class methods, and `self` references
- **Cycle Detection** — Identifies and marks recursive calls

## Requirements

- Python 3.8+
- No external dependencies (uses only the standard library)

## Quick Start

```bash
# Generate an interactive HTML call graph
python main.py --entry your_app.py --func main --dir ./your_project

# Generate a Mermaid diagram
python main.py --entry your_app.py --func main --format mermaid

# Generate JSON output
python main.py --entry your_app.py --func main --format json

# Exclude external/built-in function calls
python main.py --entry your_app.py --func main --no-externals

# ── Flow / Decision Tree Mode ─────────────────────────

# Generate a flow tree showing control flow, assignments, and data flow
python main.py --entry your_app.py --func main --mode flow

# Flow tree with called functions inlined (deep analysis)
python main.py --entry your_app.py --func main --mode flow --inline

# Control inline depth (default: 6)
python main.py --entry your_app.py --func main --mode flow --inline --inline-depth 4

# Flow tree as JSON
python main.py --entry your_app.py --func main --mode flow --format json
```

## Flow / Decision Tree Mode

The `--mode flow` option generates a **detailed decision tree** instead of a flat call graph. This captures:

- **Control Flow Branches**: `if/elif/else`, `for`, `while`, `try/except/finally`, `with`, `match/case`
- **Variable Assignments & Mutations**: tracks what variables are set and what values/expressions they receive
- **Data Flow**: shows which variables flow into each function call as arguments
- **Sequential Ordering**: statements appear in their actual execution order
- **Nested Calls**: calls within expressions (e.g., `foo(bar(x))`) are shown as nested nodes

With `--inline`, the tool **expands called functions inline** — when a call is encountered, the called function's own flow tree is inlined as children of the call node, letting you trace execution across function boundaries.

### Node Types in the Flow Tree

| Icon | Kind | Meaning |
|------|------|---------|
| `ƒ` | Function | Function entry point |
| `→` | Call | Function/method call |
| `←` | Assign | Variable assignment |
| `↺` | Mutation | Augmented assignment (`+=`, etc.) |
| `◆` | Branch | `if`/`elif` condition |
| `✓` | True Branch | Code when condition is true |
| `✗` | False Branch | Code in `else` block |
| `⟳` | Loop | `for`/`while` loop |
| `⚡` | Try | `try` block |
| `✋` | Except | Exception handler |
| `⏎` | Return | Return statement |
| `💥` | Raise | Raise exception |

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--entry`, `-e` | Path to the file containing the entry function | *(required)* |
| `--func`, `-f` | Name of the entry function (e.g., `main` or `Class.method`) | *(required)* |
| `--dir`, `-d` | Project directory to scan | Entry file's directory |
| `--output`, `-o` | Output file path | `call_graph.<ext>` or `flow_tree.<ext>` |
| `--format` | Output format: `html`, `json`, `mermaid` | `html` |
| `--mode` | Analysis mode: `call` (call graph) or `flow` (decision tree) | `call` |
| `--max-depth` | Maximum call tree depth | `30` |
| `--no-externals` | Exclude unresolved/external calls (call mode) | `false` |
| `--inline` | Inline called functions into the flow tree (flow mode) | `false` |
| `--inline-depth` | Maximum inlining depth (flow mode) | `6` |

## Example with Test Project

```bash
# Run against the included test project
python main.py --entry test_project/app.py --func main --dir . --format html -o demo.html
```

Open `demo.html` in a browser to see the interactive call graph.

### Interacting with the HTML Output

- **Click** a node to expand/collapse its children
- **Right-click** a node to open the detail panel with signature, docstring, and file info
- **Scroll** to zoom in/out
- **Drag** to pan the view
- **Search** for functions using the search bar
- Use **Expand All** / **Collapse All** buttons

## How It Works

1. **Indexing**: Walks the project directory, parses every `.py` file with `ast`, and indexes all function/method definitions and their imports.
2. **Resolution**: For each function call found in the AST, resolves it to a known definition using import tracking, same-module lookup, and name-based fallbacks.
3. **Tree Building**: Starting from the entry function, recursively builds a call tree. Cycles are detected and marked.
4. **Rendering**: Converts the tree to the selected output format.

## Limitations

- **Static Analysis Only**: Cannot resolve dynamic calls (e.g., `getattr`, `eval`, callback patterns)
- **No Type Inference**: Method calls on arbitrary objects use name-based heuristic matching
- **Decorators**: Does not unwrap decorator-wrapped functions
