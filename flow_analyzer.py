"""
flow_analyzer.py - Statement-level flow analysis for Python functions.

Builds a "decision tree" for each function that captures:
  - Sequential execution order of statements
  - Control flow branches  (if / elif / else, for, while, try / except / finally)
  - Variable assignments, mutations, and augmented assignments
  - Function / method calls with their arguments
  - Data flow: which variables feed into which calls

The tree is rooted at the function entry and every branch point fans
out into child nodes so the user can follow each possible execution path.
"""

import ast
import os
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# ────────────────────────────────────────────────────────────────
# Flow-node types
# ────────────────────────────────────────────────────────────────

@dataclass
class FlowNode:
    """Base node in the decision / flow tree."""
    kind: str                     # e.g. "call", "assign", "branch", "loop", ...
    label: str                    # human-readable short label
    detail: Optional[str] = None  # longer description / source snippet
    line: Optional[int] = None    # source line number
    source: Optional[str] = None  # raw source text of the statement
    children: List['FlowNode'] = field(default_factory=list)

    # Extended metadata (filled depending on kind)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            'kind': self.kind,
            'label': self.label,
            'detail': self.detail,
            'line': self.line,
            'source': self.source,
            'children': [c.to_dict() for c in self.children],
        }
        if self.meta:
            d['meta'] = self.meta
        return d


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _unparse(node: ast.AST) -> str:
    """Best-effort unparse of an AST node back to source."""
    try:
        return ast.unparse(node)
    except Exception:
        return "<expr>"


def _expr_name(node: ast.AST) -> str:
    """Short readable name for an expression node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        val = _expr_name(node.value)
        return f"{val}.{node.attr}"
    if isinstance(node, ast.Subscript):
        return f"{_expr_name(node.value)}[…]"
    if isinstance(node, ast.Call):
        return f"{_expr_name(node.func)}(…)"
    if isinstance(node, ast.Starred):
        return f"*{_expr_name(node.value)}"
    if isinstance(node, (ast.Tuple, ast.List)):
        inner = ", ".join(_expr_name(e) for e in node.elts)
        return f"({inner})" if isinstance(node, ast.Tuple) else f"[{inner}]"
    return _unparse(node)


def _collect_targets(node: ast.AST) -> List[str]:
    """Collect assignment target names from a target node."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: List[str] = []
        for elt in node.elts:
            names.extend(_collect_targets(elt))
        return names
    if isinstance(node, ast.Starred):
        return _collect_targets(node.value)
    if isinstance(node, ast.Attribute):
        return [_expr_name(node)]
    if isinstance(node, ast.Subscript):
        return [_expr_name(node)]
    return [_unparse(node)]


def _extract_call_args(call_node: ast.Call) -> List[str]:
    """Return a list of human-readable argument representations."""
    args = []
    for a in call_node.args:
        args.append(_unparse(a))
    for kw in call_node.keywords:
        if kw.arg:
            args.append(f"{kw.arg}={_unparse(kw.value)}")
        else:
            args.append(f"**{_unparse(kw.value)}")
    return args


def _find_calls_in_expr(node: ast.AST) -> List[ast.Call]:
    """Find all Call nodes inside an expression (including nested ones)."""
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            calls.append(child)
    return calls


def _extract_used_names(node: ast.AST) -> Set[str]:
    """Extract all Name references used (read) in an expression."""
    names: Set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


# ────────────────────────────────────────────────────────────────
# The Flow Analyzer
# ────────────────────────────────────────────────────────────────

class FlowAnalyzer:
    """
    Walks a function body and builds a flow / decision tree.

    The analyser processes statements sequentially. Branch statements
    (if/for/while/try/with) create child subtrees.  Assignments record
    variable mutations.  Calls record both the call and the data flowing
    into it (which local variables are used as arguments).
    """

    def __init__(self, source_lines: List[str]):
        self.source_lines = source_lines

    # ── public API ────────────────────────────────────────────

    def analyze_function(self, func_node: ast.FunctionDef) -> FlowNode:
        """Analyze a single function and return its flow tree."""
        sig = _unparse(func_node) if hasattr(ast, 'unparse') else func_node.name
        # Try to build a nice signature
        try:
            args_str = _unparse(func_node.args)
        except Exception:
            args_str = "…"

        root = FlowNode(
            kind="function",
            label=func_node.name,
            detail=f"def {func_node.name}({args_str})",
            line=func_node.lineno,
            source=self._get_source(func_node.lineno),
            meta={
                'params': [arg.arg for arg in func_node.args.args],
                'is_async': isinstance(func_node, ast.AsyncFunctionDef),
            },
        )
        root.children = self._process_body(func_node.body)
        return root

    # ── statement dispatcher ──────────────────────────────────

    def _process_body(self, stmts: List[ast.stmt]) -> List[FlowNode]:
        """Process a list of statements into flow nodes."""
        nodes: List[FlowNode] = []
        for stmt in stmts:
            result = self._process_stmt(stmt)
            if result is not None:
                if isinstance(result, list):
                    nodes.extend(result)
                else:
                    nodes.append(result)
        return nodes

    def _process_stmt(self, stmt: ast.stmt) -> Optional[Union[FlowNode, List[FlowNode]]]:
        """Dispatch a single statement to the appropriate handler."""
        handler = getattr(self, f'_handle_{type(stmt).__name__}', None)
        if handler:
            return handler(stmt)
        # Fallback: expression statements (including bare calls)
        if isinstance(stmt, ast.Expr):
            return self._handle_Expr(stmt)
        # Generic fallback
        return self._handle_generic(stmt)

    # ── assignments ───────────────────────────────────────────

    def _handle_Assign(self, stmt: ast.Assign) -> Union[FlowNode, List[FlowNode]]:
        targets = []
        for t in stmt.targets:
            targets.extend(_collect_targets(t))

        value_str = _unparse(stmt.value)
        label = f"{', '.join(targets)} = {value_str}"

        # Check if the value contains calls
        calls_in_value = _find_calls_in_expr(stmt.value)
        used_names = _extract_used_names(stmt.value)

        node = FlowNode(
            kind="assign",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={
                'targets': targets,
                'value': value_str,
                'reads': sorted(used_names),
            },
        )

        # If assignment includes calls, add them as children
        for call in calls_in_value:
            call_node = self._make_call_node(call)
            node.children.append(call_node)

        return node

    def _handle_AnnAssign(self, stmt: ast.AnnAssign) -> Optional[FlowNode]:
        if stmt.target is None:
            return None
        target = _expr_name(stmt.target)
        ann = _unparse(stmt.annotation)
        if stmt.value:
            value_str = _unparse(stmt.value)
            label = f"{target}: {ann} = {value_str}"
        else:
            label = f"{target}: {ann}"

        node = FlowNode(
            kind="assign",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={
                'targets': [target],
                'annotation': ann,
                'value': _unparse(stmt.value) if stmt.value else None,
            },
        )

        if stmt.value:
            for call in _find_calls_in_expr(stmt.value):
                node.children.append(self._make_call_node(call))

        return node

    def _handle_AugAssign(self, stmt: ast.AugAssign) -> FlowNode:
        target = _expr_name(stmt.target)
        op = _unparse(ast.BinOp(left=ast.Constant(value=0), op=stmt.op, right=ast.Constant(value=0)))
        # Extract just the operator symbol
        op_map = {
            ast.Add: '+=', ast.Sub: '-=', ast.Mult: '*=', ast.Div: '/=',
            ast.FloorDiv: '//=', ast.Mod: '%=', ast.Pow: '**=',
            ast.BitAnd: '&=', ast.BitOr: '|=', ast.BitXor: '^=',
            ast.LShift: '<<=', ast.RShift: '>>=',
        }
        op_str = op_map.get(type(stmt.op), '?=')
        value_str = _unparse(stmt.value)
        label = f"{target} {op_str} {value_str}"

        node = FlowNode(
            kind="mutation",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={
                'target': target,
                'operator': op_str,
                'value': value_str,
                'reads': sorted(_extract_used_names(stmt.value)),
            },
        )

        for call in _find_calls_in_expr(stmt.value):
            node.children.append(self._make_call_node(call))

        return node

    # ── expressions (including bare calls) ────────────────────

    def _handle_Expr(self, stmt: ast.Expr) -> Optional[Union[FlowNode, List[FlowNode]]]:
        if isinstance(stmt.value, ast.Call):
            return self._make_call_node(stmt.value, line=stmt.lineno)
        if isinstance(stmt.value, (ast.Constant, ast.JoinedStr)):
            # String literal expression (possibly docstring) — skip
            return None
        # Other expression
        src = _unparse(stmt.value)
        return FlowNode(
            kind="expression",
            label=_truncate(src, 80),
            detail=src,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )

    # ── return / yield ────────────────────────────────────────

    def _handle_Return(self, stmt: ast.Return) -> FlowNode:
        if stmt.value:
            val = _unparse(stmt.value)
            label = f"return {val}"
            reads = sorted(_extract_used_names(stmt.value))
        else:
            label = "return"
            val = None
            reads = []

        node = FlowNode(
            kind="return",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={'value': val, 'reads': reads},
        )

        if stmt.value:
            for call in _find_calls_in_expr(stmt.value):
                node.children.append(self._make_call_node(call))

        return node

    def _handle_Yield(self, stmt) -> FlowNode:
        val = _unparse(stmt.value) if stmt.value else None
        label = f"yield {val}" if val else "yield"
        return FlowNode(
            kind="yield",
            label=label,
            line=getattr(stmt, 'lineno', None),
            source=self._get_source(getattr(stmt, 'lineno', None)),
        )

    # ── if / elif / else ──────────────────────────────────────

    def _handle_If(self, stmt: ast.If) -> FlowNode:
        condition = _unparse(stmt.test)
        label = f"if {condition}"

        branch = FlowNode(
            kind="branch",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={
                'condition': condition,
                'reads': sorted(_extract_used_names(stmt.test)),
            },
        )

        # True branch
        true_node = FlowNode(
            kind="branch_true",
            label=f"✓ True: {_truncate(condition, 50)}",
            detail=f"When {condition} is truthy",
            line=stmt.lineno,
            meta={'branch': 'true'},
        )
        true_node.children = self._process_body(stmt.body)

        # Calls inside the condition itself
        for call in _find_calls_in_expr(stmt.test):
            cn = self._make_call_node(call)
            cn.meta['context'] = 'condition'
            branch.children.append(cn)

        branch.children.append(true_node)

        # Handle elif chain / else
        if stmt.orelse:
            if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                # elif — recurse
                elif_node = self._handle_If(stmt.orelse[0])
                elif_node.label = elif_node.label.replace("if ", "elif ", 1)
                elif_node.kind = "branch_elif"
                branch.children.append(elif_node)
            else:
                # else block
                false_node = FlowNode(
                    kind="branch_false",
                    label="✗ Else",
                    detail="Otherwise (else branch)",
                    line=stmt.orelse[0].lineno if stmt.orelse else None,
                    meta={'branch': 'false'},
                )
                false_node.children = self._process_body(stmt.orelse)
                branch.children.append(false_node)

        return branch

    # ── for loop ──────────────────────────────────────────────

    def _handle_For(self, stmt: ast.For) -> FlowNode:
        target = _expr_name(stmt.target)
        iter_str = _unparse(stmt.iter)
        label = f"for {target} in {iter_str}"

        loop = FlowNode(
            kind="loop_for",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={
                'variable': target,
                'iterable': iter_str,
                'reads': sorted(_extract_used_names(stmt.iter)),
            },
        )

        body_node = FlowNode(
            kind="loop_body",
            label="Loop body (each iteration)",
            line=stmt.body[0].lineno if stmt.body else stmt.lineno,
        )
        body_node.children = self._process_body(stmt.body)
        loop.children.append(body_node)

        if stmt.orelse:
            else_node = FlowNode(
                kind="loop_else",
                label="Loop else (no break)",
                line=stmt.orelse[0].lineno if stmt.orelse else None,
            )
            else_node.children = self._process_body(stmt.orelse)
            loop.children.append(else_node)

        return loop

    def _handle_AsyncFor(self, stmt: ast.AsyncFor) -> FlowNode:
        node = self._handle_For(stmt)
        node.kind = "loop_async_for"
        node.label = "async " + node.label
        return node

    # ── while loop ────────────────────────────────────────────

    def _handle_While(self, stmt: ast.While) -> FlowNode:
        condition = _unparse(stmt.test)
        label = f"while {condition}"

        loop = FlowNode(
            kind="loop_while",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={
                'condition': condition,
                'reads': sorted(_extract_used_names(stmt.test)),
            },
        )

        body_node = FlowNode(
            kind="loop_body",
            label="Loop body (each iteration)",
            line=stmt.body[0].lineno if stmt.body else stmt.lineno,
        )
        body_node.children = self._process_body(stmt.body)
        loop.children.append(body_node)

        if stmt.orelse:
            else_node = FlowNode(
                kind="loop_else",
                label="Loop else (no break)",
                line=stmt.orelse[0].lineno if stmt.orelse else None,
            )
            else_node.children = self._process_body(stmt.orelse)
            loop.children.append(else_node)

        return loop

    # ── try / except / finally ────────────────────────────────

    def _handle_Try(self, stmt: ast.Try) -> FlowNode:
        node = FlowNode(
            kind="try",
            label="try",
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )

        try_body = FlowNode(kind="try_body", label="Try body", line=stmt.lineno)
        try_body.children = self._process_body(stmt.body)
        node.children.append(try_body)

        for handler in stmt.handlers:
            exc_type = _unparse(handler.type) if handler.type else "Exception"
            handler_label = f"except {exc_type}"
            if handler.name:
                handler_label += f" as {handler.name}"

            exc_node = FlowNode(
                kind="except",
                label=handler_label,
                line=handler.lineno,
                source=self._get_source(handler.lineno),
                meta={
                    'exception_type': exc_type,
                    'alias': handler.name,
                },
            )
            exc_node.children = self._process_body(handler.body)
            node.children.append(exc_node)

        if stmt.orelse:
            else_node = FlowNode(
                kind="try_else",
                label="else (no exception)",
                line=stmt.orelse[0].lineno if stmt.orelse else None,
            )
            else_node.children = self._process_body(stmt.orelse)
            node.children.append(else_node)

        if stmt.finalbody:
            finally_node = FlowNode(
                kind="finally",
                label="finally (always runs)",
                line=stmt.finalbody[0].lineno if stmt.finalbody else None,
            )
            finally_node.children = self._process_body(stmt.finalbody)
            node.children.append(finally_node)

        return node

    # Python 3.11+ TryStar
    def _handle_TryStar(self, stmt) -> FlowNode:
        return self._handle_Try(stmt)

    # ── with ──────────────────────────────────────────────────

    def _handle_With(self, stmt: ast.With) -> FlowNode:
        items = []
        for item in stmt.items:
            ctx = _unparse(item.context_expr)
            if item.optional_vars:
                var = _expr_name(item.optional_vars)
                items.append(f"{ctx} as {var}")
            else:
                items.append(ctx)

        label = f"with {', '.join(items)}"

        node = FlowNode(
            kind="context",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={'items': items},
        )
        node.children = self._process_body(stmt.body)
        return node

    def _handle_AsyncWith(self, stmt: ast.AsyncWith) -> FlowNode:
        node = self._handle_With(stmt)
        node.kind = "context_async"
        node.label = "async " + node.label
        return node

    # ── raise / assert / delete ───────────────────────────────

    def _handle_Raise(self, stmt: ast.Raise) -> FlowNode:
        if stmt.exc:
            exc = _unparse(stmt.exc)
            label = f"raise {exc}"
        else:
            label = "raise"
        return FlowNode(
            kind="raise",
            label=_truncate(label, 80),
            detail=label if stmt.exc else None,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )

    def _handle_Assert(self, stmt: ast.Assert) -> FlowNode:
        test = _unparse(stmt.test)
        label = f"assert {test}"
        if stmt.msg:
            label += f", {_unparse(stmt.msg)}"
        return FlowNode(
            kind="assert",
            label=_truncate(label, 80),
            detail=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
            meta={'condition': test, 'reads': sorted(_extract_used_names(stmt.test))},
        )

    def _handle_Delete(self, stmt: ast.Delete) -> FlowNode:
        targets = [_expr_name(t) for t in stmt.targets]
        label = f"del {', '.join(targets)}"
        return FlowNode(
            kind="delete",
            label=label,
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )

    # ── break / continue / pass ───────────────────────────────

    def _handle_Break(self, stmt: ast.Break) -> FlowNode:
        return FlowNode(kind="break", label="break", line=stmt.lineno)

    def _handle_Continue(self, stmt: ast.Continue) -> FlowNode:
        return FlowNode(kind="continue", label="continue", line=stmt.lineno)

    def _handle_Pass(self, stmt: ast.Pass) -> FlowNode:
        return FlowNode(kind="pass", label="pass", line=stmt.lineno)

    # ── global / nonlocal ─────────────────────────────────────

    def _handle_Global(self, stmt: ast.Global) -> FlowNode:
        return FlowNode(
            kind="global",
            label=f"global {', '.join(stmt.names)}",
            line=stmt.lineno,
        )

    def _handle_Nonlocal(self, stmt: ast.Nonlocal) -> FlowNode:
        return FlowNode(
            kind="nonlocal",
            label=f"nonlocal {', '.join(stmt.names)}",
            line=stmt.lineno,
        )

    # ── import ────────────────────────────────────────────────

    def _handle_Import(self, stmt: ast.Import) -> FlowNode:
        names = [a.asname or a.name for a in stmt.names]
        return FlowNode(
            kind="import",
            label=f"import {', '.join(names)}",
            line=stmt.lineno,
        )

    def _handle_ImportFrom(self, stmt: ast.ImportFrom) -> FlowNode:
        mod = stmt.module or ''
        names = [a.asname or a.name for a in stmt.names]
        return FlowNode(
            kind="import",
            label=f"from {mod} import {', '.join(names)}",
            line=stmt.lineno,
        )

    # ── class / function defs inside functions ────────────────

    def _handle_FunctionDef(self, stmt: ast.FunctionDef) -> FlowNode:
        return FlowNode(
            kind="def",
            label=f"def {stmt.name}(…)",
            detail=f"Nested function definition: {stmt.name}",
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )

    def _handle_AsyncFunctionDef(self, stmt: ast.AsyncFunctionDef) -> FlowNode:
        return FlowNode(
            kind="def",
            label=f"async def {stmt.name}(…)",
            detail=f"Nested async function definition: {stmt.name}",
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )

    def _handle_ClassDef(self, stmt: ast.ClassDef) -> FlowNode:
        return FlowNode(
            kind="class",
            label=f"class {stmt.name}",
            detail=f"Nested class definition: {stmt.name}",
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )

    # ── match (Python 3.10+) ─────────────────────────────────

    def _handle_Match(self, stmt) -> FlowNode:
        subject = _unparse(stmt.subject)
        node = FlowNode(
            kind="match",
            label=f"match {_truncate(subject, 60)}",
            detail=f"match {subject}",
            line=stmt.lineno,
            source=self._get_source(stmt.lineno),
        )
        for case in stmt.cases:
            pattern = _unparse(case.pattern)
            guard = f" if {_unparse(case.guard)}" if case.guard else ""
            case_node = FlowNode(
                kind="case",
                label=f"case {pattern}{guard}",
                line=case.pattern.lineno if hasattr(case.pattern, 'lineno') else stmt.lineno,
            )
            case_node.children = self._process_body(case.body)
            node.children.append(case_node)
        return node

    # ── generic fallback ──────────────────────────────────────

    def _handle_generic(self, stmt: ast.stmt) -> Optional[FlowNode]:
        src = _unparse(stmt) if hasattr(ast, 'unparse') else type(stmt).__name__
        return FlowNode(
            kind="other",
            label=_truncate(src, 80),
            detail=src,
            line=getattr(stmt, 'lineno', None),
            source=self._get_source(getattr(stmt, 'lineno', None)),
        )

    # ── call node builder ─────────────────────────────────────

    def _make_call_node(self, call: ast.Call, line: Optional[int] = None) -> FlowNode:
        """Build a FlowNode for a function/method call."""
        func_name = _expr_name(call.func)
        args = _extract_call_args(call)
        args_str = ", ".join(args)
        label = f"{func_name}({args_str})"

        # Figure out which variables flow into this call
        used_names: Set[str] = set()
        for a in call.args:
            used_names |= _extract_used_names(a)
        for kw in call.keywords:
            used_names |= _extract_used_names(kw.value)

        node = FlowNode(
            kind="call",
            label=_truncate(label, 100),
            detail=label,
            line=line or getattr(call, 'lineno', None),
            source=self._get_source(line or getattr(call, 'lineno', None)),
            meta={
                'function': func_name,
                'arguments': args,
                'data_flow_in': sorted(used_names),
            },
        )

        # Nested calls inside arguments (e.g. foo(bar(x)))
        for arg in call.args:
            for nested_call in _find_calls_in_expr(arg):
                if nested_call is not call:
                    child = self._make_call_node(nested_call)
                    child.meta['context'] = 'argument'
                    node.children.append(child)
        for kw in call.keywords:
            for nested_call in _find_calls_in_expr(kw.value):
                if nested_call is not call:
                    child = self._make_call_node(nested_call)
                    child.meta['context'] = 'keyword_argument'
                    node.children.append(child)

        return node

    # ── source helpers ────────────────────────────────────────

    def _get_source(self, lineno: Optional[int]) -> Optional[str]:
        if lineno is None:
            return None
        idx = lineno - 1
        if 0 <= idx < len(self.source_lines):
            return self.source_lines[idx].strip()
        return None


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "…"


# ────────────────────────────────────────────────────────────────
# Project-level flow analysis
# ────────────────────────────────────────────────────────────────

class ProjectFlowAnalyzer:
    """
    Analyzes an entire project and builds flow trees for functions,
    integrating with CallGraphAnalyzer for call resolution.
    """

    def __init__(self, project_dir: str):
        self.project_dir = os.path.abspath(project_dir)
        self.flow_trees: Dict[str, FlowNode] = {}  # qualified_name -> FlowNode
        self._file_asts: Dict[str, ast.Module] = {}
        self._file_sources: Dict[str, List[str]] = {}

    def _file_to_module(self, file_path: str) -> str:
        rel = os.path.relpath(file_path, self.project_dir)
        module = rel.replace(os.sep, '.').replace('/', '.')
        if module.endswith('.py'):
            module = module[:-3]
        if module.endswith('.__init__'):
            module = module[:-9]
        return module

    def analyze_file(self, file_path: str):
        """Parse a file and analyze all functions in it."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)
        except (SyntaxError, UnicodeDecodeError):
            return

        source_lines = source.splitlines()
        self._file_asts[file_path] = tree
        self._file_sources[file_path] = source_lines

        module = self._file_to_module(file_path)
        analyzer = FlowAnalyzer(source_lines)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{module}.{node.name}"
                self.flow_trees[qualified] = analyzer.analyze_function(node)
            elif isinstance(node, ast.ClassDef):
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qualified = f"{module}.{node.name}.{item.name}"
                        self.flow_trees[qualified] = analyzer.analyze_function(item)

    def analyze_project(self):
        """Walk the project directory and analyze all Python files."""
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__'
                       and d != 'node_modules' and d != '.git' and d != 'venv'
                       and d != '.venv' and d != 'env']
            for f in files:
                if f.endswith('.py'):
                    self.analyze_file(os.path.join(root, f))

    def build_deep_flow_tree(self, entry_qualified: str,
                             call_resolver=None,
                             max_depth: int = 10,
                             visited: Optional[Set[str]] = None) -> Optional[FlowNode]:
        """
        Build a deep flow tree that inlines called functions' flow trees.

        This creates the full decision tree: when a call is encountered,
        if we have the flow tree for the called function, we attach it as
        children of the call node so the user can drill down into what
        happens inside each called function.

        Args:
            entry_qualified: Qualified name of the entry function.
            call_resolver: A function (call_name, caller_module) -> qualified_name
                          for resolving call expressions to qualified names.
            max_depth: Maximum inlining depth.
            visited: Set of already-visited functions (for recursion detection).
        """
        if visited is None:
            visited = set()

        flow = self.flow_trees.get(entry_qualified)
        if flow is None:
            return None

        if entry_qualified in visited:
            # Mark as recursive
            return FlowNode(
                kind="recursive",
                label=f"↻ {flow.label} (recursive)",
                detail=f"Recursive call to {entry_qualified}",
                line=flow.line,
                meta={'qualified_name': entry_qualified},
            )

        if max_depth <= 0:
            return FlowNode(
                kind="depth_limit",
                label=f"⋯ {flow.label} (depth limit)",
                detail=f"Max depth reached for {entry_qualified}",
                line=flow.line,
            )

        import copy
        result = copy.deepcopy(flow)
        visited = visited | {entry_qualified}

        # Recursively inline called functions
        self._inline_calls(result, call_resolver, max_depth - 1, visited,
                           entry_qualified.rsplit('.', 1)[0] if '.' in entry_qualified else '')

        return result

    def _inline_calls(self, node: FlowNode, call_resolver, depth: int,
                      visited: Set[str], caller_module: str):
        """Walk the flow tree and inline call targets."""
        new_children = []
        for child in node.children:
            if child.kind == "call" and call_resolver:
                func_name = child.meta.get('function', '')
                resolved = call_resolver(func_name, caller_module)
                if resolved and resolved in self.flow_trees:
                    # Inline the called function's flow tree
                    inlined = self.build_deep_flow_tree(
                        resolved, call_resolver, depth, visited
                    )
                    if inlined:
                        # Replace existing children with inlined content
                        # (the original children of a call node are nested
                        # calls in arguments — those are already in inlined)
                        child.children = inlined.children
                        child.meta['resolved_to'] = resolved
                        child.meta['inlined'] = True
            else:
                # Only recurse into non-call children (call children
                # get their subtrees from inlining above)
                self._inline_calls(child, call_resolver, depth, visited, caller_module)

            new_children.append(child)

        node.children = new_children

