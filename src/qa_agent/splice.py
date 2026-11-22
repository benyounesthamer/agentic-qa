"""Merge model-written code into the test file by function name, instead of rewriting the whole file.

Why: a model that must re-send the entire file on every change eventually gets cut off mid-file as
the suite grows, and an incomplete file silently loses tests. Here the model sends only what it
changed or added; each top-level function or class replaces the one with the same name, new ones
are appended, and new imports go to the top. The rest of the file is never touched.
"""
from __future__ import annotations

import ast


def _blocks(tree: ast.Module, lines: list[str]) -> dict[str, tuple[int, int]]:
    """name -> (first line, last line), 0-based and inclusive, decorators included."""
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            out[node.name] = (start, node.end_lineno - 1)
    return out


def splice(original: str, patch: str) -> str:
    """Apply `patch` (imports, helpers, functions) to `original`. Both must be valid Python."""
    if not original.strip():
        return patch.strip() + "\n"
    orig_tree, patch_tree = ast.parse(original), ast.parse(patch)
    lines, patch_lines = original.splitlines(), patch.splitlines()
    orig_blocks = _blocks(orig_tree, lines)

    new_imports, replacements, appended = [], {}, []
    existing_imports = {ast.unparse(n) for n in orig_tree.body if isinstance(n, (ast.Import, ast.ImportFrom))}
    for node in patch_tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if ast.unparse(node) not in existing_imports:
                new_imports.append(ast.unparse(node))
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            text = "\n".join(patch_lines[start:node.end_lineno])
            if node.name in orig_blocks:
                replacements[node.name] = text
            else:
                appended.append(text)
        else:  # module-level statements such as constants
            appended.append("\n".join(patch_lines[node.lineno - 1:node.end_lineno]))

    # replace from the bottom up so earlier line numbers stay valid
    for name, (start, end) in sorted(orig_blocks.items(), key=lambda kv: -kv[1][0]):
        if name in replacements:
            lines[start:end + 1] = replacements[name].splitlines()

    if new_imports:
        last_import = max((n.end_lineno for n in orig_tree.body if isinstance(n, (ast.Import, ast.ImportFrom))),
                          default=0)
        lines[last_import:last_import] = new_imports
    result = "\n".join(lines).rstrip() + "\n"
    for block in appended:
        result += "\n\n" + block.strip() + "\n"
    return result


def focus(code: str, keep_tests: set[str]) -> str:
    """The parts of the file a repair needs: imports, helpers and constants, and only the named tests.

    Sending the whole suite on every repair wastes tokens and, on large suites, exceeds the
    provider's request size; passing tests are left out because they are not being changed.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    lines = code.splitlines()
    parts = []
    for node in tree.body:
        is_test = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        if is_test and node.name not in keep_tests:
            continue
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]) - 1
        parts.append("\n".join(lines[start:node.end_lineno]))
    return "\n\n".join(parts) + "\n"
