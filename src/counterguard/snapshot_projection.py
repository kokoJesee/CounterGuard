"""Versioned literal pytest.param projection; source is parsed, never executed."""

import ast
import itertools

from counterguard.contract_draft import MAX_CASES, Unsupported, _literal, _project_test, _resolve
from counterguard.digests import digest_bytes

EXTRACTOR = "snapshot-test-projection.v1"


def project_snapshot_test(raw: bytes, *, test_function, target_module, target_symbol):
    identities = []

    def parameters(function, bindings):
        dimensions, seen, count = [], set(), 1
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
                not isinstance(labels, (tuple, list))
                or not labels
                or any(not isinstance(x, str) or not x.isidentifier() or x in seen for x in labels)
                or len(set(labels)) != len(labels)
                or not isinstance(rows, (ast.Tuple, ast.List))
                or not rows.elts
            ):
                raise Unsupported("unsupported_parametrization")
            seen.update(labels)
            dimension = []
            for row in rows.elts:
                identity = None
                if isinstance(row, ast.Call):
                    if (
                        _resolve(row.func, bindings) != "pytest.param"
                        or len(row.keywords) != 1
                        or row.keywords[0].arg != "id"
                        or not isinstance(row.keywords[0].value, ast.Constant)
                        or type(row.keywords[0].value.value) is not str
                        or len(row.keywords[0].value.value) > 256
                    ):
                        raise Unsupported("pytest_param_requires_literal_id_without_marks")
                    values, identity = row.args, row.keywords[0].value.value
                else:
                    values = (
                        [row]
                        if len(labels) == 1
                        else (row.elts if isinstance(row, (ast.Tuple, ast.List)) else [])
                    )
                if len(values) != len(labels):
                    raise Unsupported("parameter_arity_mismatch")
                for value in values:
                    _literal(value, {})
                dimension.append((dict(zip(labels, values, strict=True)), identity))
            count *= len(dimension)
            if count > MAX_CASES:
                raise Unsupported("case_budget_exceeded")
            dimensions.append(dimension)
        args = function.args
        if (
            {x.arg for x in args.posonlyargs + args.args + args.kwonlyargs} != seen
            or args.vararg
            or args.kwarg
            or args.defaults
            or args.kw_defaults
        ):
            raise Unsupported("fixture_or_default_argument_requires_review")
        combinations = list(itertools.product(*dimensions)) if dimensions else [()]
        identities.extend(tuple(item[1] for item in row) for row in combinations)
        return [
            dict(itertools.chain.from_iterable(item[0].items() for item in row))
            for row in combinations
        ]

    result = _project_test(
        raw,
        test_function=test_function,
        target_module=target_module,
        target_symbol=target_symbol,
        parameter_reader=parameters,
        identity_namespace=EXTRACTOR,
    )
    return result | {
        "extractor_version": EXTRACTOR,
        "source_digest": digest_bytes(raw),
        "parameter_ids": tuple(identities),
    }
