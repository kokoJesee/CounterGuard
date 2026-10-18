"""Project a deliberately small test grammar into review-only data, never execute it."""

import ast
import itertools
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.contract_draft_models import (
    ContractProposal,
    ContractProposalV2,
    DraftCase,
    DraftKeyword,
    DraftLiteral,
    DraftMatchCase,
    DraftUnsupported,
)
from counterguard.contracts import EXCEPTION_TYPES
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.literal_match import validate_literal_match
from counterguard.project_config import Module, RepositoryPath, Symbol, reject_links
from counterguard.repository import read_committed_files

MAX_CASES = 256


class Unsupported(ValueError):
    pass


def _resolve(node, bindings):
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = _resolve(node.value, bindings)
        return parent + "." + node.attr if parent else None
    return None


def _literal(node, parameters, *, depth=0):
    if depth > 8:
        raise Unsupported("literal_depth_exceeded")
    if isinstance(node, ast.Name) and node.id in parameters:
        return _literal(parameters[node.id], {}, depth=depth + 1)
    if isinstance(node, ast.Constant):
        value = node.value
        kind = {
            type(None): "none",
            bool: "boolean",
            int: "integer",
            float: "float",
            str: "string",
            bytes: "bytes",
        }.get(type(value))
        if kind:
            return DraftLiteral(kind=kind, value=value.hex() if kind == "bytes" else value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _literal(node.operand, parameters, depth=depth + 1)
        if inner.kind in {"integer", "float"}:
            return DraftLiteral(
                kind=inner.kind,
                value=-inner.value if isinstance(node.op, ast.USub) else inner.value,
            )
    if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) <= 128:
        return DraftLiteral(
            kind="list" if isinstance(node, ast.List) else "tuple",
            items=tuple(_literal(item, parameters, depth=depth + 1) for item in node.elts),
        )
    if isinstance(node, ast.Dict) and len(node.keys) <= 128 and None not in node.keys:
        return DraftLiteral(
            kind="dict",
            entries=tuple(
                (
                    _literal(key, parameters, depth=depth + 1),
                    _literal(value, parameters, depth=depth + 1),
                )
                for key, value in zip(node.keys, node.values, strict=True)
            ),
        )
    raise Unsupported("nonliteral_expression")


def _parameters(function, bindings):
    dimensions = []
    seen = set()
    count = 1
    for decorator in function.decorator_list:
        if (
            not isinstance(decorator, ast.Call)
            or _resolve(decorator.func, bindings) != "pytest.mark.parametrize"
            or len(decorator.args) != 2
            or decorator.keywords
        ):
            raise Unsupported("unsupported_test_decorator")
        labels = ast.literal_eval(decorator.args[0])
        labels = [x.strip() for x in labels.split(",")] if isinstance(labels, str) else labels
        rows = decorator.args[1]
        if (
            not isinstance(labels, (list, tuple))
            or not labels
            or any(not isinstance(x, str) or not x.isidentifier() or x in seen for x in labels)
            or len(set(labels)) != len(labels)
            or not isinstance(rows, (ast.List, ast.Tuple))
            or not rows.elts
        ):
            raise Unsupported("unsupported_parametrization")
        seen.update(labels)
        dimension = []
        for row in rows.elts:
            values = (
                [row]
                if len(labels) == 1
                else (row.elts if isinstance(row, (ast.List, ast.Tuple)) else [])
            )
            if len(values) != len(labels):
                raise Unsupported("parameter_arity_mismatch")
            for value in values:
                _literal(value, {})
            dimension.append(dict(zip(labels, values, strict=True)))
        count *= len(dimension)
        if count > MAX_CASES:
            raise Unsupported("case_budget_exceeded")
        dimensions.append(dimension)
    args = function.args
    declared = {x.arg for x in args.posonlyargs + args.args + args.kwonlyargs}
    if declared != seen or args.vararg or args.kwarg or args.defaults or args.kw_defaults:
        raise Unsupported("fixture_or_default_argument_requires_review")
    # Source declaration order is preserved. Identical inputs do not acquire clocks or UUIDs.
    return (
        [
            dict(itertools.chain.from_iterable(item.items() for item in combination))
            for combination in itertools.product(*dimensions)
        ]
        if dimensions
        else [{}]
    )


def _call(node, bindings, parameters, target):
    if not isinstance(node, ast.Call) or _resolve(node.func, bindings) != target:
        raise Unsupported("assertion_is_not_a_direct_target_call")
    if any(isinstance(arg, ast.Starred) for arg in node.args) or any(
        item.arg is None for item in node.keywords
    ):
        raise Unsupported("argument_expansion_requires_review")
    return {
        "positional_args": tuple(_literal(arg, parameters) for arg in node.args),
        "keyword_args": tuple(
            DraftKeyword(name=item.arg, literal=_literal(item.value, parameters))
            for item in node.keywords
        ),
    }


def _assertion(statement, bindings, parameters, target):
    if isinstance(statement, ast.Assert):
        if statement.msg is not None:
            _literal(statement.msg, parameters)
        expression = statement.test
        if isinstance(expression, ast.Compare):
            if len(expression.ops) != 1:
                raise Unsupported("chained_comparison_requires_review")
            oracle = {ast.Eq: "eq", ast.NotEq: "ne", ast.Is: "is", ast.IsNot: "is_not"}.get(
                type(expression.ops[0])
            )
            if oracle is None:
                raise Unsupported("unsupported_comparison")
            return _call(expression.left, bindings, parameters, target) | {
                "oracle": oracle,
                "expected": _literal(expression.comparators[0], parameters),
            }
        negative = isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not)
        return _call(
            expression.operand if negative else expression, bindings, parameters, target
        ) | {"oracle": "falsey" if negative else "truthy"}
    if isinstance(statement, ast.With) and len(statement.items) == 1:
        item = statement.items[0]
        call = item.context_expr
        if (
            item.optional_vars is not None
            or not isinstance(call, ast.Call)
            or _resolve(call.func, bindings) != "pytest.raises"
            or len(call.args) != 1
            or any(keyword.arg != "match" for keyword in call.keywords)
            or len(call.keywords) > 1
            or not isinstance(call.args[0], ast.Name)
            or call.args[0].id not in EXCEPTION_TYPES
            or call.args[0].id in bindings
            or len(statement.body) != 1
            or not isinstance(statement.body[0], ast.Expr)
        ):
            raise Unsupported("unsupported_exception_assertion")
        result = _call(statement.body[0].value, bindings, parameters, target) | {
            "oracle": "raises",
            "exception": call.args[0].id,
        }
        if call.keywords:
            pattern = call.keywords[0].value
            if not isinstance(pattern, ast.Constant) or not isinstance(pattern.value, str):
                raise Unsupported("exception_match_literal_required")
            try:
                result["exception_match"] = validate_literal_match(pattern.value)
            except ValueError as error:
                raise Unsupported(str(error)) from error
        return result
    raise Unsupported("unsupported_assertion")


def _assertion_count(node, bindings):
    return sum(
        isinstance(child, ast.Assert)
        or (
            isinstance(child, ast.With)
            and any(
                isinstance(item.context_expr, ast.Call)
                and _resolve(item.context_expr.func, bindings) == "pytest.raises"
                for item in child.items
            )
        )
        for child in ast.walk(node)
    )


def project_test(
    test_bytes: bytes, *, test_function: str, target_module: str, target_symbol: str
) -> dict:
    """Return proposal fragments; import bindings are syntax, not runtime identity proof."""
    if len(test_bytes) > 1024 * 1024:
        raise ValueError("Test file exceeds byte budget")
    try:
        tree = ast.parse(test_bytes)
    except (SyntaxError, UnicodeError) as error:
        raise ValueError("Committed test cannot be parsed by this scanner") from error
    if sum(1 for _ in ast.walk(tree)) > 50000:
        raise ValueError("Test file exceeds AST budget")
    bindings = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if alias.name == "*":
                    raise ValueError("Wildcard imports require manual binding review")
                bindings[alias.asname or alias.name] = node.module + "." + alias.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings[node.name] = "<local_definition_requires_review>"
        else:
            # Known lexical rebindings must not masquerade as an imported target.
            for name in ast.walk(node):
                if isinstance(name, ast.Name) and isinstance(name.ctx, (ast.Store, ast.Del)):
                    bindings[name.id] = "<rebinding_requires_review>"
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_function
    ]
    if len(selected) != 1:
        raise ValueError("Select one top-level test function present exactly once")
    function = selected[0]
    statements = [
        node
        for node in function.body
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    source_count = _assertion_count(function, bindings)
    target = target_module + "." + target_symbol
    cases, unsupported = [], []

    def refuse(reason):
        return {
            "cases": (),
            "unsupported": (
                DraftUnsupported(
                    source_line=function.lineno, reason_code=reason, assertion_count=source_count
                ),
            ),
            "source_assertions": source_count,
            "represented_assertions": 0,
        }

    if isinstance(function, ast.AsyncFunctionDef):
        return refuse("async_test_requires_review")
    if not source_count:
        return refuse("no_assertion_syntax")
    try:
        parameters = _parameters(function, bindings)
        local_names = {
            node.id
            for node in ast.walk(function)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        }
        initial_bindings = bindings | {
            name: "<local_binding_requires_review>" for name in local_names | set(parameters[0])
        }
        local = dict(initial_bindings)
        assertion_seen = False
        for statement in statements:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and _resolve(statement.value, local) == target
            ):
                if assertion_seen:
                    return refuse("alias_assignment_after_assertion")
                if statement.targets[0].id in parameters[0]:
                    return refuse("parameter_rebinding_requires_review")
                local[statement.targets[0].id] = target
            elif not isinstance(statement, (ast.Assert, ast.With)):
                return refuse("test_setup_or_control_flow_requires_review")
            else:
                assertion_seen = True
        selected_assertions = [
            node for node in statements if isinstance(node, (ast.Assert, ast.With))
        ]
        if len(selected_assertions) * len(parameters) > MAX_CASES:
            return refuse("case_budget_exceeded")
        local = dict(initial_bindings)
        ordinal = 0
        for statement in statements:
            if isinstance(statement, ast.Assign):
                local[statement.targets[0].id] = target
                continue
            ordinal += 1
            candidates = []
            ast_digest = digest_bytes(ast.dump(statement, include_attributes=False).encode())
            try:
                for parameter_index, values in enumerate(parameters, 1):
                    fragment = _assertion(statement, local, values, target)
                    identity = digest_json_artifact(
                        {
                            "test_function": test_function,
                            "target": target,
                            "assertion_index": ordinal,
                            "parameter_index": parameter_index,
                            "assertion_digest": ast_digest,
                            "fragment": fragment,
                        }
                    )
                    candidates.append(
                        (DraftMatchCase if "exception_match" in fragment else DraftCase)(
                            case_id="case_" + identity[7:31],
                            source_line=statement.lineno,
                            assertion_index=ordinal,
                            parameter_index=parameter_index,
                            assertion_digest=ast_digest,
                            **fragment,
                        )
                    )
            except (ValueError, TypeError, RecursionError) as error:
                unsupported.append(
                    DraftUnsupported(
                        source_line=statement.lineno,
                        reason_code=str(error)
                        if isinstance(error, Unsupported)
                        else "literal_or_oracle_requires_review",
                        assertion_count=_assertion_count(statement, bindings),
                    )
                )
            else:
                cases.extend(candidates)
    except (ValueError, TypeError, RecursionError) as error:
        return refuse(
            str(error) if isinstance(error, Unsupported) else "test_parameters_require_review"
        )
    return {
        "cases": tuple(cases),
        "unsupported": tuple(unsupported),
        "source_assertions": source_count,
        "represented_assertions": len({case.assertion_index for case in cases}),
    }


def draft_contract(
    repo: Path,
    revision: str,
    *,
    test_ref: str,
    test_function: str,
    target: str,
    output: Path,
    cwd: Path | None = None,
) -> ContractProposal:
    cwd = (cwd or Path.cwd()).resolve(strict=True)
    test_ref = TypeAdapter(RepositoryPath).validate_python(test_ref)
    TypeAdapter(Symbol).validate_python(test_function)
    if not test_function.startswith("test_") or target.count(":") != 1:
        raise ValueError("Select a test_* function and module:symbol target")
    module, symbol = target.split(":")
    TypeAdapter(Module).validate_python(module)
    TypeAdapter(Symbol).validate_python(symbol)
    output = output if output.is_absolute() else cwd / output
    reject_links(output)
    output = output.resolve()
    if not output.is_relative_to(cwd) or output == cwd or output.is_relative_to(repo.resolve()):
        raise ValueError("Draft output must be below cwd and outside the target repository")
    if output.exists():
        raise ArtifactIntegrityError("Draft output exists; choose a new proposal ID")
    commit, files, pins = read_committed_files(repo, revision)
    if test_ref not in files:
        raise ValueError("Test must exist in the selected committed tree")
    fragments = project_test(
        files[test_ref], test_function=test_function, target_module=module, target_symbol=symbol
    )
    status = (
        "unsupported"
        if not fragments["cases"]
        else ("partial" if fragments["unsupported"] else "draft_ready")
    )
    value = {
        "status": status,
        "requested_revision": revision,
        "commit": commit,
        "test_ref": test_ref,
        "test_object_id": next(pin.object_id for pin in pins if pin.path == test_ref),
        "test_digest": digest_bytes(files[test_ref]),
        "test_function": test_function,
        "target_module": module,
        "target_symbol": symbol,
        **fragments,
        "next_action": "Review every literal, oracle, import binding, case independence and "
        "unsupported assertion. This proposal cannot run or enter the Registry. An owner-head "
        "contract and supported Docker bootstrap are still required.",
        "implementation_digests": inspection_implementation_digests(),
    }
    matched = any(isinstance(case, DraftMatchCase) for case in fragments["cases"])
    version = "v2" if matched else "v1"
    value["artifact_digest"] = digest_json_artifact(
        value
        | {
            "schema_version": f"contract-proposal.{version}",
            "extractor_version": f"literal-test-projection.{version}",
            "human_review_required": True,
            "execution_allowed": False,
            "binding_trust": "syntactic_only_requires_owner_review",
        }
    )
    proposal = (ContractProposalV2 if matched else ContractProposal).model_validate(value)
    write_immutable(output / "proposal.json", canonical_json_bytes(proposal))
    return proposal
