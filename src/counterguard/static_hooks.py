"""Lexical hook observations and one finite raise-only grammar, never Python execution.

Recognition narrows a review finding, not the trust model. Arbitrary module/class
effects and later mutation are still the local source reviewer's responsibility.
"""

import ast

from counterguard.digests import digest_bytes

HOOKS = frozenset({"__getattr__", "__getattribute__", "__dir__"})


def _doc(node):
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _body(node):
    return [x for x in node.body if not _doc(x)]


def _bindings(node):
    """Conservative names bound in this lexical scope, including branch bindings."""
    found = []

    def visit(item):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append(item.name)
            return
        if isinstance(item, ast.Lambda):
            return
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            found.extend(
                x.asname or (x.name.split(".")[0] if isinstance(item, ast.Import) else x.name)
                for x in item.names
            )
        if isinstance(item, ast.Name) and isinstance(item.ctx, (ast.Store, ast.Del)):
            found.append(item.id)
        if isinstance(item, ast.ExceptHandler) and item.name:
            found.append(item.name)
        if isinstance(item, (ast.MatchAs, ast.MatchStar)) and item.name:
            found.append(item.name)
        if isinstance(item, ast.MatchMapping) and item.rest:
            found.append(item.rest)
        for child in ast.iter_child_nodes(item):
            visit(child)

    for item in node.body:
        visit(item)
    return found


def _simple_args(node, *, annotations=False):
    args = node.args
    return (
        isinstance(node, ast.FunctionDef)
        and not node.decorator_list
        and not node.type_params
        and not args.posonlyargs
        and len(args.args) == 2
        and not args.defaults
        and not args.kwonlyargs
        and not args.vararg
        and not args.kwarg
        and len({x.arg for x in args.args}) == 2
        and (annotations or (not node.returns and not any(x.annotation for x in args.args)))
    )


def _exception_definition(files, ref, symbol):
    """Pin an entire inert exception declaration module, not just a class name."""
    if ref not in files:
        return False
    try:
        tree = ast.parse(files[ref])
    except (SyntaxError, UnicodeError, ValueError, RecursionError):
        return False
    if sum(1 for _ in ast.walk(tree)) > 50000:
        return False
    names = _bindings(tree)
    if len(set(names)) != len(names) or set(names) & {"Exception", "super", "str"}:
        return False
    classes = []
    for node in tree.body:
        if _doc(node):
            continue
        if (
            isinstance(node, ast.ImportFrom)
            and not node.level
            and node.module == "__future__"
            and all(x.name == "annotations" and x.asname is None for x in node.names)
        ):
            continue
        if not (
            isinstance(node, ast.ClassDef)
            and not node.decorator_list
            and not node.keywords
            and not node.type_params
            and len(node.bases) == 1
            and isinstance(node.bases[0], ast.Name)
            and node.bases[0].id == "Exception"
        ):
            return False
        classes.append(node.name)
        statements = [x for x in _body(node) if not isinstance(x, ast.Pass)]
        if not statements:
            continue
        if len(statements) != 1:
            return False
        init = statements[0]
        if not isinstance(init, ast.FunctionDef) or not _simple_args(init, annotations=True):
            return False
        first, message = init.args.args
        if (
            init.name != "__init__"
            or first.arg != "self"
            or message.arg != "message"
            or first.annotation is not None
            or not (
                message.annotation is None
                or isinstance(message.annotation, ast.Name)
                and message.annotation.id == "str"
            )
            or not (
                init.returns is None
                or isinstance(init.returns, ast.Constant)
                and init.returns.value is None
            )
        ):
            return False
        body = _body(init)
        if len(body) != 1 or not isinstance(body[0], ast.Expr):
            return False
        # Compare syntax, never call super() or a user-supplied constructor.
        expected = ast.parse("super().__init__(message)").body[0].value
        if ast.dump(body[0].value) != ast.dump(expected):
            return False
    return classes.count(symbol) == 1


def _finite_exception(files, tree, owner, hook, *, module, ref, import_root):
    if (
        not isinstance(owner, ast.ClassDef)
        or owner not in tree.body
        or owner.decorator_list
        or owner.keywords
        or owner.type_params
        or len(owner.bases) > 1
        or any(not isinstance(x, ast.Name) or x.id not in {"type", "object"} for x in owner.bases)
        or _body(owner) != [hook]
        or hook.name != "__getattr__"
        or not _simple_args(hook, annotations=True)
    ):
        return None
    future = any(
        isinstance(x, ast.ImportFrom)
        and not x.level
        and x.module == "__future__"
        and any(a.name == "annotations" for a in x.names)
        for x in tree.body
    )
    if not future and (hook.returns or any(x.annotation for x in hook.args.args)):
        return None
    statements = _body(hook)
    if len(statements) != 1 or not isinstance(statements[0], ast.Raise):
        return None
    raised = statements[0]
    call = raised.exc
    if (
        raised.cause is not None
        or not isinstance(call, ast.Call)
        or not isinstance(call.func, ast.Name)
        or len(call.args) != 1
        or call.keywords
    ):
        return None
    message = call.args[0]
    parameter = hook.args.args[1].arg
    literal = isinstance(message, ast.Constant) and isinstance(message.value, str)
    formatted = isinstance(message, ast.JoinedStr) and all(
        isinstance(x, ast.Constant)
        and isinstance(x.value, str)
        or isinstance(x, ast.FormattedValue)
        and isinstance(x.value, ast.Name)
        and x.value.id == parameter
        and x.conversion == -1
        and x.format_spec is None
        for x in message.values
    )
    if not (literal or formatted) or call.func.id in {x.arg for x in hook.args.args}:
        return None
    bindings = _bindings(tree)
    if any(bindings.count(name) != 1 for name in (owner.name, call.func.id)):
        return None
    if set(bindings) & {"type", "object"}:
        return None
    protected = {owner.name, call.func.id, "type", "object"}
    if any(
        isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id in protected
        or isinstance(node, ast.Global)
        and protected.intersection(node.names)
        for node in ast.walk(tree)
    ):
        # Also reject writes hidden in defaults, comprehensions or function
        # bodies. This deliberately over-approximates local shadowing.
        return None
    # Only a unique top-level from-import can establish exception identity.
    imported = [
        (node, alias)
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if (alias.asname or alias.name) == call.func.id
    ]
    if len(imported) != 1:
        return None
    node, alias = imported[0]
    package = module.split(".") if ref.endswith("/__init__.py") else module.split(".")[:-1]
    if node.level:
        if node.level > len(package) or not node.module:
            return None
        target = ".".join(package[: len(package) - node.level + 1] + [node.module])
    else:
        target = node.module or ""
    if not target.startswith(module.split(".")[0] + "."):
        return None
    prefix = "" if import_root == "." else "src/"
    stem = prefix + target.replace(".", "/")
    refs = [p for p in (stem + ".py", stem + "/__init__.py") if p in files]
    if len(refs) != 1 or not _exception_definition(files, refs[0], alias.name):
        return None
    return {
        "module": target,
        "symbol": alias.name,
        "path": refs[0],
        "content_digest": digest_bytes(files[refs[0]]),
    }


def inspect_hooks(files, tree, *, module, ref, import_root):
    """Return typed, source-bound observations and unresolved hook findings."""
    findings, observations = set(), []

    def issue(scope):
        findings.add(
            "module_lookup_hook_requires_review"
            if scope == "module"
            else "class_lookup_hook_requires_review"
        )

    def visit(node, scopes):
        scope, owner = scopes[-1] if scopes else ("module", tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in HOOKS:
                actual = "nested_function" if scope == "function" else scope
                if scope == "class" and any(
                    isinstance(x, ast.Name) and x.id == "type" for x in owner.bases
                ):
                    actual = "metaclass"
                exception = (
                    _finite_exception(
                        files, tree, owner, node, module=module, ref=ref, import_root=import_root
                    )
                    if scope == "class"
                    else None
                )
                observations.append(
                    {
                        "scope": actual,
                        "qualified_name": ".".join([x.name for _, x in scopes] + [node.name]),
                        "path": ref,
                        "line": node.lineno,
                        "content_digest": digest_bytes(files[ref]),
                        "recognition": "finite_raise" if exception else "unrecognized",
                        "grammar": "finite-raise-hook.v1" if exception else None,
                        "exception": exception,
                    }
                )
                if scope != "function" and exception is None:
                    issue(scope)
            scopes = [*scopes, ("function", node)]
        elif isinstance(node, ast.ClassDef):
            if scope != "function" and node.name in HOOKS:
                issue(scope)
            scopes = [*scopes, ("class", node)]
        elif isinstance(node, ast.Global) and HOOKS.intersection(node.names):
            issue("module")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {
                x.asname or (x.name.split(".")[0] if isinstance(node, ast.Import) else x.name)
                for x in node.names
            }
            if scope != "function" and HOOKS.intersection(names):
                issue(scope)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if scope != "function" and node.id in HOOKS:
                issue(scope)
        elif (
            isinstance(node, ast.ExceptHandler)
            and node.name in HOOKS
            or isinstance(node, (ast.MatchAs, ast.MatchStar))
            and node.name in HOOKS
            or isinstance(node, ast.MatchMapping)
            and node.rest in HOOKS
        ):
            if scope != "function":
                issue(scope)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if node.attr in HOOKS:
                issue("module")  # Object identity is not statically established.
        for child in ast.iter_child_nodes(node):
            visit(child, scopes)

    visit(tree, [])
    return sorted(findings), observations
