"""
analyzer.py - AST-based Python call graph analyzer.

Parses Python source files, indexes all function/method definitions,
tracks imports, and builds a call tree from a specified entry point.
"""

import ast
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class FunctionInfo:
    """Represents a parsed function or method definition."""
    name: str
    qualified_name: str      # e.g. 'module.ClassName.method' or 'module.func'
    file_path: str
    line_start: int
    line_end: int
    signature: str
    docstring: Optional[str]
    calls: List[str]         # Raw call expressions found in the body
    module: str
    class_name: Optional[str] = None


@dataclass
class CallNode:
    """A node in the call tree."""
    name: str
    qualified_name: str
    file_path: Optional[str]
    line_start: Optional[int]
    line_end: Optional[int]
    signature: Optional[str]
    docstring: Optional[str]
    is_external: bool
    is_recursive: bool = False
    children: List['CallNode'] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        return {
            'name': self.name,
            'qualified_name': self.qualified_name,
            'file_path': self.file_path,
            'line_start': self.line_start,
            'line_end': self.line_end,
            'signature': self.signature,
            'docstring': self.docstring,
            'is_external': self.is_external,
            'is_recursive': self.is_recursive,
            'children': [c.to_dict() for c in self.children],
        }


class CallGraphAnalyzer:
    """
    Analyzes a Python project directory, indexes all function/method definitions,
    and builds a call tree starting from a specified entry point.
    """

    def __init__(self, project_dir: str):
        self.project_dir = os.path.abspath(project_dir)
        self.definitions: Dict[str, FunctionInfo] = {}       # qualified_name -> FunctionInfo
        self.name_index: Dict[str, List[FunctionInfo]] = {}  # simple name -> [FunctionInfo]
        self.module_imports: Dict[str, Dict[str, str]] = {}  # module -> {alias: resolved}
        self._index_project()

    # ── Indexing ──────────────────────────────────────────────────────

    def _file_to_module(self, file_path: str) -> str:
        """Convert a file path to a dotted module name relative to project root."""
        rel = os.path.relpath(file_path, self.project_dir)
        module = rel.replace(os.sep, '.').replace('/', '.')
        if module.endswith('.py'):
            module = module[:-3]
        if module.endswith('.__init__'):
            module = module[:-9]
        return module

    def _index_project(self):
        """Walk the project directory and index all Python files."""
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__'
                       and d != 'node_modules' and d != '.git' and d != 'venv'
                       and d != '.venv' and d != 'env']
            for f in files:
                if f.endswith('.py'):
                    fpath = os.path.join(root, f)
                    self._index_file(fpath)

    def _index_file(self, file_path: str):
        """Parse a single Python file and index its definitions and imports."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)
        except (SyntaxError, UnicodeDecodeError):
            return

        module = self._file_to_module(file_path)
        imports: Dict[str, str] = {}

        # Collect imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    imports[local_name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ''
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    imports[local_name] = f"{mod}.{alias.name}" if mod else alias.name

        self.module_imports[module] = imports

        # Index top-level functions and class methods
        source_lines = source.splitlines()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._index_function(node, module, file_path, source_lines, None)
            elif isinstance(node, ast.ClassDef):
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._index_function(item, module, file_path, source_lines, node.name)

    def _index_function(self, node, module: str, file_path: str,
                        source_lines: list, class_name: Optional[str]):
        """Index a single function or method definition."""
        qualified = f"{module}.{class_name}.{node.name}" if class_name else f"{module}.{node.name}"

        # Build signature string
        sig = self._extract_signature(node, source_lines)
        docstring = ast.get_docstring(node)

        # Collect all call expressions inside the function body
        calls = []
        seen_calls: set = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._call_to_string(child)
                if call_name and call_name not in seen_calls:
                    calls.append(call_name)
                    seen_calls.add(call_name)

        func_info = FunctionInfo(
            name=node.name,
            qualified_name=qualified,
            file_path=file_path,
            line_start=node.lineno,
            line_end=getattr(node, 'end_lineno', node.lineno),
            signature=sig,
            docstring=docstring,
            calls=calls,
            module=module,
            class_name=class_name,
        )

        self.definitions[qualified] = func_info
        self.name_index.setdefault(node.name, []).append(func_info)
        if class_name:
            method_key = f"{class_name}.{node.name}"
            self.name_index.setdefault(method_key, []).append(func_info)

    def _extract_signature(self, node, source_lines: list) -> str:
        """Extract the function signature from source lines."""
        start = node.lineno - 1
        lines = []
        for i in range(start, min(start + 10, len(source_lines))):
            lines.append(source_lines[i])
            if ':' in source_lines[i] and ')' in source_lines[i]:
                break
        sig = ' '.join(l.strip() for l in lines)
        # Trim to just the def ... (...) part
        idx = sig.find(':')
        if idx != -1:
            sig = sig[:idx]
        return sig.strip()

    def _call_to_string(self, node: ast.Call) -> Optional[str]:
        """Convert a Call AST node to a dotted string representation."""
        return self._expr_to_string(node.func)

    def _expr_to_string(self, node) -> Optional[str]:
        """Convert an expression node to a string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._expr_to_string(node.value)
            if value:
                return f"{value}.{node.attr}"
            return node.attr
        return None

    # ── Call Tree Building ────────────────────────────────────────────

    def build_call_tree(self, entry_file: str, entry_func: str,
                        max_depth: int = 30) -> CallNode:
        """
        Build a call tree starting from the specified entry function.

        Args:
            entry_file: Path to the file containing the entry function.
            entry_func: Name of the entry function (or Class.method).
            max_depth: Maximum recursion depth to prevent infinite trees.

        Returns:
            The root CallNode of the tree.

        Raises:
            ValueError: If the entry function cannot be found.
        """
        entry_path = os.path.abspath(entry_file)
        entry_module = self._file_to_module(entry_path)

        # Try qualified lookup
        entry_def = self.definitions.get(f"{entry_module}.{entry_func}")

        if not entry_def:
            # Try name-based lookup, preferring the entry module
            candidates = self.name_index.get(entry_func, [])
            for c in candidates:
                if c.module == entry_module:
                    entry_def = c
                    break
            if not entry_def and candidates:
                entry_def = candidates[0]

        if not entry_def:
            available = sorted(set(self.name_index.keys()))
            raise ValueError(
                f"Entry function '{entry_func}' not found in '{entry_file}'.\n"
                f"Available functions ({len(available)}): {', '.join(available[:30])}..."
            )

        visited: Set[str] = set()
        return self._build_node(entry_def, visited, max_depth)

    def _build_node(self, func_def: FunctionInfo, visited: Set[str],
                    depth: int) -> CallNode:
        """Recursively build a CallNode and its children."""
        is_recursive = func_def.qualified_name in visited

        node = CallNode(
            name=func_def.name,
            qualified_name=func_def.qualified_name,
            file_path=func_def.file_path,
            line_start=func_def.line_start,
            line_end=func_def.line_end,
            signature=func_def.signature,
            docstring=func_def.docstring,
            is_external=False,
            is_recursive=is_recursive,
        )

        if is_recursive or depth <= 0:
            return node

        visited.add(func_def.qualified_name)

        for call_name in func_def.calls:
            child_def = self._resolve_call(call_name, func_def.module)
            if child_def:
                child_node = self._build_node(child_def, visited, depth - 1)
                node.children.append(child_node)
            else:
                ext_node = CallNode(
                    name=call_name.split('.')[-1],
                    qualified_name=call_name,
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    signature=None,
                    docstring=None,
                    is_external=True,
                )
                node.children.append(ext_node)

        visited.discard(func_def.qualified_name)
        return node

    def _resolve_call(self, call_name: str, caller_module: str) -> Optional[FunctionInfo]:
        """
        Attempt to resolve a call expression to a known FunctionInfo.

        Resolution order:
        1. Import-based resolution
        2. Same-module lookup
        3. Global name-based fallback
        """
        parts = call_name.split('.')
        imports = self.module_imports.get(caller_module, {})

        if len(parts) == 1:
            return self._resolve_simple_call(parts[0], caller_module, imports)
        else:
            return self._resolve_dotted_call(parts, caller_module, imports)

    def _resolve_simple_call(self, name: str, caller_module: str,
                             imports: Dict[str, str]) -> Optional[FunctionInfo]:
        """Resolve a simple (non-dotted) function call."""
        # 1. Check imports
        if name in imports:
            resolved = imports[name]
            if resolved in self.definitions:
                return self.definitions[resolved]
            candidates = self.name_index.get(name, [])
            for c in candidates:
                if c.qualified_name == resolved:
                    return c

        # 2. Same module
        qualified = f"{caller_module}.{name}"
        if qualified in self.definitions:
            return self.definitions[qualified]

        # 3. Global unique match
        candidates = self.name_index.get(name, [])
        if len(candidates) == 1:
            return candidates[0]

        return None

    def _resolve_dotted_call(self, parts: List[str], caller_module: str,
                             imports: Dict[str, str]) -> Optional[FunctionInfo]:
        """Resolve a dotted call like self.method(), module.func(), obj.method()."""
        # self.method()
        if parts[0] == 'self':
            method_name = parts[-1]
            candidates = self.name_index.get(method_name, [])
            for c in candidates:
                if c.module == caller_module:
                    return c
            return None

        # Import-based: e.g. `utils.process()` where utils is imported
        if parts[0] in imports:
            resolved_base = imports[parts[0]]
            remaining = '.'.join(parts[1:])
            qualified = f"{resolved_base}.{remaining}"
            if qualified in self.definitions:
                return self.definitions[qualified]
            # Try resolving remaining as standalone
            candidates = self.name_index.get(remaining, [])
            for c in candidates:
                if c.qualified_name.startswith(resolved_base):
                    return c
            # Maybe it's a class method
            if len(parts) >= 2:
                candidates = self.name_index.get(parts[-1], [])
                for c in candidates:
                    if c.qualified_name.startswith(resolved_base):
                        return c

        # Full qualified name match
        full = '.'.join(parts)
        if full in self.definitions:
            return self.definitions[full]

        # Class.method style
        if len(parts) >= 2:
            class_method = f"{parts[-2]}.{parts[-1]}"
            candidates = self.name_index.get(class_method, [])
            if len(candidates) == 1:
                return candidates[0]

        # Fallback: unique match on last part
        method_name = parts[-1]
        candidates = self.name_index.get(method_name, [])
        if len(candidates) == 1:
            return candidates[0]

        return None

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return statistics about the indexed project."""
        modules = set()
        files = set()
        for d in self.definitions.values():
            modules.add(d.module)
            files.add(d.file_path)
        return {
            'total_functions': len(self.definitions),
            'total_modules': len(modules),
            'total_files': len(files),
        }
