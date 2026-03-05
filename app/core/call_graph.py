"""
call_graph.py — Build a Service Interaction Map using AST parsing.
Detects imports between project files and function calls to build
a call graph showing how files/functions interact.
"""
import ast
import os
from typing import Any


def detect_imports(code: str) -> list[str]:
    """Extract all import targets from a Python source string."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def detect_function_calls(code: str) -> list[dict]:
    """Extract function/method calls with line numbers."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    calls = []

    class CallVisitor(ast.NodeVisitor):
        def __init__(self):
            self.current_func = None

        def visit_FunctionDef(self, node):
            old = self.current_func
            self.current_func = node.name
            self.generic_visit(node)
            self.current_func = old

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

        def visit_Call(self, node):
            call_name = None
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                # e.g. db.connect(), services.create_order()
                parts = []
                current = node.func
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                parts.reverse()
                call_name = ".".join(parts)

            if call_name:
                calls.append({
                    "caller": self.current_func or "<module>",
                    "callee": call_name,
                    "line": node.lineno,
                })
            self.generic_visit(node)

    CallVisitor().visit(tree)
    return calls


def build_interaction_map(files: list[dict], failure_points: dict | list = None) -> dict:
    """
    Build a service interaction map from project files.

    Returns:
        {
            "edges": [{"from": "routes.py", "to": "services.py:create_order", "failure": "race condition"}],
            "graph": "routes.py\n   ↓\nservices.py:create_order\n   ↓\n..."
        }
    """
    # Map basenames to files
    project_modules = {}
    for f in files:
        basename = os.path.splitext(f["file"])[0]
        project_modules[basename] = f

    # Build failure lookup from AI failure_points
    failure_lookup = {}
    if isinstance(failure_points, dict):
        for category, items in failure_points.items():
            if isinstance(items, list):
                for item in items:
                    loc = item.get("location", "") if isinstance(item, dict) else ""
                    desc = item.get("description", "") if isinstance(item, dict) else ""
                    if ":" in loc:
                        fname = loc.split(":")[0]
                        if fname not in failure_lookup:
                            failure_lookup[fname] = []
                        failure_lookup[fname].append(desc)
    elif isinstance(failure_points, list):
        for item in failure_points:
            loc = item.get("location", "") if isinstance(item, dict) else ""
            desc = item.get("description", "") if isinstance(item, dict) else ""
            if ":" in loc:
                fname = loc.split(":")[0]
                if fname not in failure_lookup:
                    failure_lookup[fname] = []
                failure_lookup[fname].append(desc)

    # Detect edges: file → imported module (if in project)
    edges = []
    seen = set()

    for f in files:
        source_file = f["file"]
        code = f["content"]

        # Get imports
        imports = detect_imports(code)
        for imp in imports:
            # Check if import matches a project module
            imp_base = imp.split(".")[-1]
            if imp_base in project_modules and imp_base != os.path.splitext(source_file)[0]:
                target_file = project_modules[imp_base]["file"]
                edge_key = f"{source_file}->{target_file}"
                if edge_key not in seen:
                    seen.add(edge_key)

                    # Check for failures in target
                    failure = None
                    if target_file in failure_lookup:
                        failure = failure_lookup[target_file][0]

                    edges.append({
                        "from": source_file,
                        "to": target_file,
                        "failure": failure,
                    })

        # Get function calls that reference other modules
        calls = detect_function_calls(code)
        for call in calls:
            callee = call["callee"]
            parts = callee.split(".")
            if parts[0] in project_modules and parts[0] != os.path.splitext(source_file)[0]:
                target = project_modules[parts[0]]["file"]
                func_ref = callee if len(parts) > 1 else callee
                edge_key = f"{source_file}:{call['caller']}->{func_ref}"
                if edge_key not in seen:
                    seen.add(edge_key)

                    failure = None
                    if target in failure_lookup:
                        failure = failure_lookup[target][0]

                    edges.append({
                        "from": f"{source_file}:{call['caller']}",
                        "to": func_ref,
                        "failure": failure,
                    })

    # Build visual graph
    graph_lines = _build_visual_graph(edges, files)

    return {
        "edges": edges,
        "graph": "\n".join(graph_lines),
    }


def _build_visual_graph(edges: list[dict], files: list[dict]) -> list[str]:
    """Build a vertical text graph showing service interactions."""
    if not edges:
        # Fallback: just show file hierarchy
        lines = []
        for i, f in enumerate(files):
            lines.append(f["file"])
            if i < len(files) - 1:
                lines.append("   ↓")
        return lines

    # Build adjacency from edges
    visited = set()
    lines = []

    # Find root nodes (files that are not targets)
    sources = {e["from"].split(":")[0] for e in edges}
    targets = {e["to"].split(":")[0].split(".")[0] + ".py" for e in edges}
    roots = sources - targets
    if not roots:
        roots = {edges[0]["from"].split(":")[0]}

    def walk(node, depth=0):
        indent = "   " * depth
        if node in visited:
            return
        visited.add(node)

        lines.append(f"{indent}{node}")

        # Find edges from this node
        for e in edges:
            src_file = e["from"].split(":")[0]
            if src_file == node or e["from"] == node:
                target = e["to"]
                failure = e.get("failure")
                marker = f"   ❌ {failure}" if failure else ""

                lines.append(f"{indent}   ↓")
                target_file = target.split(":")[0].split(".")[0] + ".py"
                display = target + marker
                lines.append(f"{indent}   {display}")

                # Recurse into target file
                if target_file != node:
                    walk(target_file, depth + 1)

    for root in sorted(roots):
        walk(root)

    return lines if lines else [f["file"] for f in files]
