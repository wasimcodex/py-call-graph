#!/usr/bin/env python3
"""
PyCallGraph - Python Call Graph Generator

Analyzes Python source files and generates an interactive call graph
starting from a specified entry function.

Usage:
    python main.py --entry app.py --func main --dir ./my_project
    python main.py --entry app.py --func main --dir ./my_project --format html --output graph.html
"""

import argparse
import os
import sys
import time

from analyzer import CallGraphAnalyzer
from renderer import render_json, render_mermaid, render_html


def main():
    parser = argparse.ArgumentParser(
        prog='py-call-graph',
        description='Generate an interactive call graph from Python source code.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --entry app.py --func main
  python main.py --entry app.py --func main --dir ./src --format html -o call_graph.html
  python main.py --entry app.py --func Application.run --format mermaid
        """
    )

    parser.add_argument('--entry', '-e', required=True,
                        help='Path to the Python file containing the entry function.')
    parser.add_argument('--func', '-f', required=True,
                        help='Name of the entry function (e.g., "main" or "ClassName.method").')
    parser.add_argument('--dir', '-d', default=None,
                        help='Project directory to scan. Defaults to the directory of the entry file.')
    parser.add_argument('--output', '-o', default=None,
                        help='Output file path. Defaults to "call_graph.<format>".')
    parser.add_argument('--format', choices=['html', 'json', 'mermaid'], default='html',
                        help='Output format (default: html).')
    parser.add_argument('--max-depth', type=int, default=30,
                        help='Maximum call tree depth (default: 30).')
    parser.add_argument('--no-externals', action='store_true',
                        help='Exclude external/unresolved function calls from the output.')

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

    # Default output filename
    ext_map = {'html': 'html', 'json': 'json', 'mermaid': 'md'}
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

    print(f"\n✅ Done! Output saved to: {os.path.abspath(output_path)}\n")


def count_nodes(node) -> int:
    return 1 + sum(count_nodes(c) for c in node.children)


def strip_externals(node):
    """Remove external nodes from the tree in-place."""
    node.children = [c for c in node.children if not c.is_external]
    for c in node.children:
        strip_externals(c)


if __name__ == '__main__':
    main()
