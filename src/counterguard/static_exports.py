"""Recognize a narrow, source-pinned export declaration without importing Python.

This is a static binding check, not proof about arbitrary Python effects. Its
result still requires source review and the separate Docker authorization.
"""

import ast

from counterguard.admission import STDLIB
from counterguard.digests import digest_bytes


class ExportProblem(ValueError):
    """Finite reason code, never target-controlled exception text."""


def _require(condition, code):
    if not condition:
        raise ExportProblem(code)


def _tree(files, ref):
    _require(ref in files, "export_source_missing")
    try:
        tree = ast.parse(files[ref])
        _require(sum(1 for _ in ast.walk(tree)) <= 50000, "export_ast_budget_exceeded")
        return tree
    except (SyntaxError, UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, ExportProblem):
            raise
        raise ExportProblem("export_source_unparseable") from error


def _docstring(node):
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _literal(node):
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def _assignment(node):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    _require(all(isinstance(x, ast.Name) for x in targets), "export_dynamic_assignment")
    _require(node.value is not None and _literal(node.value), "export_nonliteral_assignment")
    return [x.id for x in targets]


def _terminal(tree, symbol):
    """Reject import-time execution/rebinding outside this explicit grammar."""
    future = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and not node.level
        and any(x.name == "annotations" for x in node.names)
        for node in tree.body
    )
    bound, functions, cache_names = set(), [], set()

    def bind(names):
        _require(
            not bound.intersection(names) and len(set(names)) == len(names), "export_rebinding"
        )
        _require(
            not any(n.startswith("__") and n != "__all__" for n in names), "export_hook_binding"
        )
        bound.update(names)

    for node in tree.body:
        if _docstring(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _require(not isinstance(node, ast.ImportFrom) or not node.level, "export_local_import")
            modules = (
                [x.name for x in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            _require(
                all(x.split(".")[0] in STDLIB | {"__future__"} for x in modules),
                "export_nonstdlib_import",
            )
            _require(all(x.name != "*" for x in node.names), "export_wildcard_import")
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                _require(all(x.asname is None for x in node.names), "export_future_alias")
                continue
            names = [
                x.asname or (x.name.split(".")[0] if isinstance(node, ast.Import) else x.name)
                for x in node.names
            ]
            bind(names)
            if isinstance(node, ast.ImportFrom) and node.module == "functools":
                cache_names.update(x.asname or x.name for x in node.names if x.name == "cache")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            _require(not isinstance(node, ast.AnnAssign) or future, "export_evaluated_annotation")
            bind(_assignment(node))
        elif isinstance(node, ast.FunctionDef):
            bind([node.name])
            defaults = [*node.args.defaults, *(x for x in node.args.kw_defaults if x is not None)]
            _require(all(_literal(x) for x in defaults), "export_evaluated_default")
            annotations = [node.returns] + [
                x.annotation
                for x in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            ]
            annotations += [x.annotation for x in (node.args.vararg, node.args.kwarg) if x]
            _require(future or not any(annotations), "export_evaluated_annotation")
            _require(not node.type_params, "export_type_parameters_unsupported")
            if node.name == symbol:
                _require(not node.decorator_list, "export_target_decorated")
                functions.append(node)
            else:
                # The sole recognized decorator is an un-rebound stdlib cache
                # import. No target-defined decorator is executed by this check.
                _require(
                    all(
                        isinstance(x, ast.Name) and x.id in cache_names for x in node.decorator_list
                    ),
                    "export_other_decorator_unsupported",
                )
        elif isinstance(node, ast.If):
            # Support the conventional, statically false typing-only block.
            _require(
                isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"
                and not node.orelse
                and any(
                    isinstance(x, ast.Assign)
                    and len(x.targets) == 1
                    and isinstance(x.targets[0], ast.Name)
                    and x.targets[0].id == "TYPE_CHECKING"
                    and isinstance(x.value, ast.Constant)
                    and x.value.value is False
                    for x in tree.body[: tree.body.index(node)]
                )
                and all(isinstance(x, (ast.Import, ast.ImportFrom)) for x in node.body),
                "export_conditional_binding",
            )
        else:
            raise ExportProblem("export_import_time_statement_unsupported")
    _require(len(functions) == 1, "export_definition_not_ordinary_function")


def resolve_static_reexport(files, *, module, symbol, import_root):
    """One root-package named import to one direct child ordinary .py module."""
    _require("." not in module, "export_root_package_required")
    prefix = "" if import_root == "." else "src/"
    root_ref = prefix + module + "/__init__.py"
    _require(prefix + module + ".py" not in files, "export_ambiguous_module")
    tree = _tree(files, root_ref)
    imports, all_seen = [], False
    for node in tree.body:
        if _docstring(node):
            continue
        if isinstance(node, ast.ImportFrom):
            _require(all(x.name != "*" for x in node.names), "export_wildcard_import")
            if node.module == "__future__" and not node.level:
                _require(all(x.asname is None for x in node.names), "export_future_alias")
                continue
            name = (module + "." + (node.module or "")) if node.level == 1 else node.module
            _require(
                node.level in {0, 1}
                and name is not None
                and name.startswith(module + ".")
                and len(name.split(".")) == 2,
                "export_direct_child_required",
            )
            imports.append((name, node))
        elif isinstance(node, ast.Assign):
            _require(_assignment(node) == ["__all__"] and not all_seen, "export_root_assignment")
            _require(
                isinstance(node.value, (ast.List, ast.Tuple))
                and all(
                    isinstance(x, ast.Constant) and isinstance(x.value, str)
                    for x in node.value.elts
                ),
                "export_all_not_literal_names",
            )
            all_seen = True
        else:
            raise ExportProblem("export_root_statement_unsupported")
    _require(len(imports) == 1, "export_single_import_required")
    definition_module, declaration = imports[0]
    names = [x.asname or x.name for x in declaration.names]
    _require(len(names) == len(set(names)) and names.count(symbol) == 1, "export_rebinding")
    _require("__all__" not in names, "export_hook_binding")
    _require(not any(x.startswith("__") for x in names), "export_hook_binding")
    alias = next(x for x in declaration.names if (x.asname or x.name) == symbol)
    definition_ref = prefix + definition_module.replace(".", "/") + ".py"
    _require(
        prefix + definition_module.replace(".", "/") + "/__init__.py" not in files,
        "export_ambiguous_module",
    )
    _terminal(_tree(files, definition_ref), alias.name)
    return {
        "algorithm": "static-root-reexport.v1",
        "target_module": module,
        "target_symbol": symbol,
        "definition_module": definition_module,
        "definition_symbol": alias.name,
        "definition_ref": definition_ref,
        "files": [
            {"path": ref, "content_digest": digest_bytes(files[ref])}
            for ref in sorted((root_ref, definition_ref))
        ],
        "claim": "Restricted static declaration only; "
        "not proof of arbitrary Python effects or safety.",
    }
