#!/usr/bin/env python3
"""
PyCallGraph - Python Call Graph & Flow Tree Generator

Analyzes Python source files and generates either:
  - A call graph (existing mode): shows which functions call which.
  - A flow / decision tree (new mode): shows the full execution flow
    including control flow branches, variable assignments, mutations,
    and data flow through each function.

Usage:
    # Classic call graph
    python main.py --entry app.py --func main --dir ./my_project

    # Flow / decision tree
    python main.py --entry app.py --func main --dir ./my_project --mode flow

    # Flow tree with function inlining (expand called functions inline)
    python main.py --entry app.py --func main --dir ./my_project --mode flow --inline
"""

import argparse
import os
import sys
import time

from analyzer import CallGraphAnalyzer
from renderer import render_json, render_mermaid, render_html
from flow_analyzer import ProjectFlowAnalyzer


def main():
    parser = argparse.ArgumentParser(
        prog='py-call-graph',
        description='Generate an interactive call graph or flow/decision tree from Python source code.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Call graph (default)
  python main.py --entry app.py --func main
  python main.py --entry app.py --func main --dir ./src --format html -o call_graph.html

  # Flow / decision tree
  python main.py --entry app.py --func main --mode flow
  python main.py --entry app.py --func main --mode flow --inline --inline-depth 5
  python main.py --entry app.py --func main --mode flow --format json
        """
    )

    parser.add_argument('--entry', '-e', required=True,
                        help='Path to the Python file containing the entry function.')
    parser.add_argument('--func', '-f', required=True,
                        help='Name of the entry function (e.g., "main" or "ClassName.method").')
    parser.add_argument('--dir', '-d', default=None,
                        help='Project directory to scan. Defaults to the directory of the entry file.')
    parser.add_argument('--output', '-o', default=None,
                        help='Output file path. Defaults to "call_graph.<format>" or "flow_tree.<format>".')
    parser.add_argument('--format', choices=['html', 'html-light', 'json', 'mermaid'], default='html',
                        help='Output format (default: html). Use html-light for very large projects.')
    parser.add_argument('--max-depth', type=int, default=30,
                        help='Maximum call tree depth (default: 30).')
    parser.add_argument('--no-externals', action='store_true',
                        help='Exclude external/unresolved function calls from the output.')

    # New flow mode arguments
    parser.add_argument('--mode', choices=['call', 'flow'], default='call',
                        help='Analysis mode: "call" for call graph (default), "flow" for decision/flow tree.')
    parser.add_argument('--inline', action='store_true',
                        help='(Flow mode) Inline called functions into the flow tree for deep analysis.')
    parser.add_argument('--inline-depth', type=int, default=6,
                        help='(Flow mode) Maximum depth for inlining called functions (default: 6).')

    args = parser.parse_args()

    # Resolve paths
    entry_file = os.path.abspath(args.entry)
    if not os.path.isfile(entry_file):
        print(f"Error: Entry file '{args.entry}' not found.", file=sys.stderr)
        sys.exit(1)

    project_dir = os.path.abspath(args.dir) if args.dir else os.path.dirname(entry_file)
    if not os.path.isdir(project_dir):
        print(f"Error: Project directory '{args.dir}' not found.", file=sys.stderr)
        sys.exit(1)

    if args.mode == 'flow':
        _run_flow_mode(args, entry_file, project_dir)
    else:
        _run_call_mode(args, entry_file, project_dir)


def _run_call_mode(args, entry_file: str, project_dir: str):
    """Run the classic call graph analysis."""
    ext_map = {'html': 'html', 'html-light': 'html', 'json': 'json', 'mermaid': 'md'}
    output_path = args.output or f"call_graph.{ext_map[args.format]}"

    # ── Analyze ────────────────────────────────────────────────
    print(f"\n🔍 Scanning project: {project_dir}")
    t0 = time.time()
    analyzer = CallGraphAnalyzer(project_dir)
    stats = analyzer.get_stats()
    t_scan = time.time() - t0
    print(f"   Found {stats['total_functions']} functions in {stats['total_files']} files "
          f"({stats['total_modules']} modules) [{t_scan:.2f}s]")

    # ── Build Tree ─────────────────────────────────────────────
    print(f"\n🌳 Building call tree from: {args.func} ({os.path.basename(entry_file)})")
    try:
        tree = analyzer.build_call_tree(entry_file, args.func, max_depth=args.max_depth)
    except ValueError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    # Optionally strip externals
    if args.no_externals:
        strip_externals(tree)

    node_count = count_nodes(tree)
    print(f"   Tree has {node_count} nodes")

    # ── Render ─────────────────────────────────────────────────
    print(f"\n📄 Rendering {args.format.upper()} → {output_path}")
    if args.format == 'json':
        render_json(tree, output_path)
    elif args.format == 'mermaid':
        render_mermaid(tree, output_path)
    elif args.format == 'html':
        render_html(tree, output_path, project_dir=project_dir)
    elif args.format == 'html-light':
        from renderer import render_html_light
        render_html_light(tree, output_path, project_dir=project_dir)

    print(f"\n✅ Done! Output saved to: {os.path.abspath(output_path)}\n")


def _run_flow_mode(args, entry_file: str, project_dir: str):
    """Run the flow / decision tree analysis."""
    from flow_renderer import render_flow_html, render_flow_html_light, render_flow_json, render_flow_mermaid

    ext_map = {'html': 'html', 'html-light': 'html', 'json': 'json', 'mermaid': 'md'}
    output_path = args.output or f"flow_tree.{ext_map[args.format]}"

    # ── Analyze ────────────────────────────────────────────────
    print(f"\n🔍 Scanning project: {project_dir}")
    t0 = time.time()

    # We need both the call graph analyzer (for resolution) and the flow analyzer
    call_analyzer = CallGraphAnalyzer(project_dir)
    flow_analyzer = ProjectFlowAnalyzer(project_dir)
    flow_analyzer.analyze_project()

    stats = call_analyzer.get_stats()
    t_scan = time.time() - t0
    print(f"   Found {stats['total_functions']} functions in {stats['total_files']} files "
          f"({stats['total_modules']} modules) [{t_scan:.2f}s]")
    print(f"   Built flow trees for {len(flow_analyzer.flow_trees)} functions")

    # ── Resolve entry function ─────────────────────────────────
    entry_module = call_analyzer._file_to_module(entry_file)
    entry_qualified = f"{entry_module}.{args.func}"

    # Try to find the function
    if entry_qualified not in flow_analyzer.flow_trees:
        # Fallback: search by simple name
        matches = [qn for qn in flow_analyzer.flow_trees if qn.endswith(f".{args.func}")]
        if matches:
            # Prefer same module
            same_mod = [m for m in matches if m.startswith(entry_module)]
            entry_qualified = same_mod[0] if same_mod else matches[0]
        else:
            available = sorted(flow_analyzer.flow_trees.keys())
            print(f"\nError: Function '{args.func}' not found.", file=sys.stderr)
            if available:
                print(f"Available functions ({len(available)}):", file=sys.stderr)
                for name in available[:30]:
                    print(f"  - {name}", file=sys.stderr)
            sys.exit(1)

    # ── Build Flow Tree ────────────────────────────────────────
    print(f"\n🌳 Building flow tree from: {entry_qualified}")

    if args.inline:
        # Build a call resolver using the call graph analyzer
        def resolve_call(call_name: str, caller_module: str):
            resolved = call_analyzer._resolve_call(call_name, caller_module)
            return resolved.qualified_name if resolved else None

        flow_tree = flow_analyzer.build_deep_flow_tree(
            entry_qualified,
            call_resolver=resolve_call,
            max_depth=args.inline_depth,
        )
        print(f"   Inlined functions up to depth {args.inline_depth}")
    else:
        flow_tree = flow_analyzer.flow_trees.get(entry_qualified)

    if flow_tree is None:
        print(f"\nError: Could not build flow tree for '{entry_qualified}'.", file=sys.stderr)
        sys.exit(1)

    flow_dict = flow_tree.to_dict()
    node_count = _count_flow_nodes(flow_dict)
    print(f"   Flow tree has {node_count} nodes")

    # ── Render ─────────────────────────────────────────────────
    print(f"\n📄 Rendering {args.format.upper()} → {output_path}")
    if args.format == 'json':
        render_flow_json(flow_dict, output_path)
    elif args.format == 'mermaid':
        render_flow_mermaid(flow_dict, output_path)
    elif args.format == 'html':
        render_flow_html(flow_dict, output_path, project_dir=project_dir)
    elif args.format == 'html-light':
        render_flow_html_light(flow_dict, output_path, project_dir=project_dir)

    print(f"\n✅ Done! Output saved to: {os.path.abspath(output_path)}\n")


def _count_flow_nodes(d: dict) -> int:
    return 1 + sum(_count_flow_nodes(c) for c in d.get('children', []))


def count_nodes(node) -> int:
    return 1 + sum(count_nodes(c) for c in node.children)


def strip_externals(node):
    """Remove external nodes from the tree in-place."""
    node.children = [c for c in node.children if not c.is_external]
    for c in node.children:
        strip_externals(c)


if __name__ == '__main__':
    main()
