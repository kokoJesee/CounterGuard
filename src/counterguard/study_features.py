"""Research-only static features; reviewed metadata and syntax never imply a label."""

import ast
from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import FeatureExtractionError
from counterguard.features import _module_bindings, _resolved_name
from counterguard.models import ArtifactRef, Digest, FrozenModel, NonEmptyText, UtcDateTime
from counterguard.predicates import VOCABULARY, AstFeature, FeatureVector
from counterguard.project_config import Identifier, Symbol
from counterguard.scope import TrainingExample
from counterguard.standalone_capture import ZERO, _require, _seal
from counterguard.standalone_models import ReviewReason
from counterguard.static_exports import resolve_static_reexport
from counterguard.study_models import FixtureInterface

EXTRACTOR = "ast-features.study.v1"
SIGNATURE = "parameter-shape.study.v1"
STUDY_VOCABULARY = {
    **VOCABULARY,
    "branch:is_member": "If/IfExp test or generator filter references formal is_member",
    "branch:none": "If/IfExp test or generator filter uses formal parameter is/is not None",
    "range:check": (
        "Numeric lower and upper bounds on one syntactic expression in one If/IfExp test, "
        "generator filter, or Compare/BoolOp generator element; no cross-generator merging"
    ),
}
VOCABULARY_PIN = digest_bytes(canonical_json_bytes(STUDY_VOCABULARY))
MAX_SOURCE_BYTES = 256 * 1024
MAX_NODES = 16000
MAX_DEPTH = 80
MAX_GENERATORS = 8


class StudyFeatureContext(FrozenModel):
    schema_version: Literal["study-feature-context.v1"] = "study-feature-context.v1"
    purpose: Literal["tool_owned_research_fixture_only"] = "tool_owned_research_fixture_only"
    authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    context_id: Identifier
    created_at: UtcDateTime
    operator: ReviewReason
    reason: ReviewReason
    metadata_basis: ReviewReason
    source_ref: ArtifactRef
    source_digest: Digest
    symbol: Symbol
    contract_family: Identifier
    contract_version: Identifier
    interface_kind: FixtureInterface
    module_group: Identifier
    artifact_digest: Digest

    @model_validator(mode="after")
    def nonblank(self):
        if any(not text.strip() for text in (self.operator, self.reason, self.metadata_basis)):
            raise ValueError("Research feature metadata requires a nonblank independent basis")
        return self


class SyntaxWitness(FrozenModel):
    token: AstFeature
    line: Annotated[int, Field(ge=1)]
    end_line: Annotated[int, Field(ge=1)]
    node_kind: NonEmptyText

    @model_validator(mode="after")
    def ordered(self):
        if self.end_line < self.line:
            raise ValueError("Syntax witness ends before it starts")
        return self


class StudyFeatureRecord(FrozenModel):
    schema_version: Literal["study-feature-record.v1"] = "study-feature-record.v1"
    purpose: Literal["tool_owned_research_fixture_only"] = "tool_owned_research_fixture_only"
    extractor: Literal["ast-features.study.v1"] = EXTRACTOR
    signature_algorithm: Literal["parameter-shape.study.v1"] = SIGNATURE
    vocabulary_digest: Digest
    context_digest: Digest
    source_digest: Digest
    implementation_digests: dict[str, Digest]
    features: FeatureVector
    witnesses: tuple[SyntaxWitness, ...]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        keys = [_witness_key(w) for w in self.witnesses]
        if keys != sorted(set(keys)) or {w.token for w in self.witnesses} != set(
            self.features.ast_features
        ):
            raise ValueError("Every token requires canonical, unique syntax witnesses")
        return self


class StudyFeatureAudit(FrozenModel):
    schema_version: Literal["study-feature-audit.v1"] = "study-feature-audit.v1"
    assurance: Literal["annotation_agreement_not_semantic_adjudication"] = (
        "annotation_agreement_not_semantic_adjudication"
    )
    record: StudyFeatureRecord
    expected: FeatureVector
    expected_digest: Digest
    matched: bool
    missing: tuple[AstFeature, ...]
    unexpected: tuple[AstFeature, ...]
    metadata_mismatches: tuple[str, ...]
    artifact_digest: Digest


def _witness_key(w):
    return w.token, w.line, w.end_line, w.node_kind


def _exact(value, model):
    if type(value) is not model:
        raise TypeError(f"Research boundary requires exact {model.__name__}")
    return model.model_validate_json(value.model_dump_json())


def _parse(source, symbol):
    if type(source) is not bytes or len(source) > MAX_SOURCE_BYTES:
        raise FeatureExtractionError("study_source_byte_budget_or_type")
    try:
        tree = ast.parse(source)
        stack, count = [(tree, 0)], 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if count > MAX_NODES or depth > MAX_DEPTH:
                raise FeatureExtractionError("study_ast_budget_exceeded")
            stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
        # Compilation validates duplicate parameters/illegal bindings; never eval/exec.
        compile(tree, "<study-static-source>", "exec", dont_inherit=True)
    except (SyntaxError, ValueError, UnicodeError, RecursionError) as error:
        raise FeatureExtractionError("study_source_syntax_invalid") from error
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol
    ]
    if len(definitions) != 1 or "." in symbol:
        raise FeatureExtractionError("study_target_must_be_one_top_level_function")
    function = definitions[0]
    if not isinstance(function, ast.FunctionDef) or function.decorator_list or function.type_params:
        raise FeatureExtractionError("study_async_decorator_or_type_parameters_unsupported")
    unsupported = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.Match,
        ast.Try,
        ast.TryStar,
        ast.AsyncFor,
        ast.While,
        ast.With,
        ast.AsyncWith,
        ast.Import,
        ast.ImportFrom,
        ast.Global,
        ast.Nonlocal,
        ast.NamedExpr,
        ast.Delete,
        ast.TypeAlias,
    )
    for statement in function.body:
        for node in ast.walk(statement):
            if isinstance(node, unsupported) or (
                isinstance(node, ast.comprehension) and node.is_async
            ):
                raise FeatureExtractionError("study_control_flow_or_binding_unsupported")
            if isinstance(node, (ast.For, ast.comprehension)) and not _plain_target(node.target):
                raise FeatureExtractionError("study_iteration_binding_unsupported")
    return tree, function


def _plain_target(node):
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Store)
    return isinstance(node, (ast.Tuple, ast.List)) and all(_plain_target(n) for n in node.elts)


def _parameters(args):
    return {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs} | {
        a.arg for a in (args.vararg, args.kwarg) if a is not None
    }


def _function_bindings(function):
    """Generator locals do not leak into the enclosing function's lexical locals."""
    names = _parameters(function.args)
    stack = list(function.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.GeneratorExp):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        stack.extend(ast.iter_child_nodes(node))
    return names


def _condition_nodes(test):
    stack = [test]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.GeneratorExp):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _numeric(node):
    return (isinstance(node, ast.Constant) and type(node.value) in (int, float)) or (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.USub, ast.UAdd))
        and isinstance(node.operand, ast.Constant)
        and type(node.operand.value) in (int, float)
    )


def _range_present(nodes):
    bounds = {}
    for node in nodes:
        if not isinstance(node, ast.Compare):
            continue
        values = (node.left, *node.comparators)
        for left, op, right in zip(values, node.ops, values[1:], strict=False):
            if not isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                continue
            for value, bound, reverse in ((left, right, False), (right, left, True)):
                if _numeric(bound) and isinstance(value, (ast.Name, ast.Attribute, ast.Subscript)):
                    lower = isinstance(op, (ast.Gt, ast.GtE)) != reverse
                    bounds.setdefault(ast.dump(value), set()).add("lower" if lower else "upper")
    return any(value == {"lower", "upper"} for value in bounds.values())


class _Extractor:
    def __init__(self, tree):
        self.bindings, self.module_names = _module_bindings(tree)
        for statement in tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stack = [statement]
            while stack:
                part = stack.pop()
                if isinstance(part, (ast.Import, ast.ImportFrom)):
                    for alias in part.names:
                        if alias.name == "*":
                            raise FeatureExtractionError("study_module_star_binding_unsupported")
                        if part is not statement:
                            name = alias.asname or (
                                alias.name.split(".")[0]
                                if isinstance(part, ast.Import)
                                else alias.name
                            )
                            self.module_names.add(name)
                            self.bindings.pop(name, None)
                if isinstance(part, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self.module_names.add(part.name)
                    self.bindings.pop(part.name, None)
                    continue
                stack.extend(ast.iter_child_nodes(part))
        self.witnesses = {}

    def add(self, token, node):
        witness = SyntaxWitness(
            token=token, line=node.lineno, end_line=node.end_lineno, node_kind=type(node).__name__
        )
        self.witnesses[_witness_key(witness)] = witness

    def condition(self, node, parameters, *, branches=True):
        nodes = tuple(_condition_nodes(node))
        if (
            branches
            and "is_member" in parameters
            and any(isinstance(part, ast.Name) and part.id == "is_member" for part in nodes)
        ):
            self.add("branch:is_member", node)
        if branches:
            for part in nodes:
                if isinstance(part, ast.Compare):
                    values = (part.left, *part.comparators)
                    for left, op, right in zip(values, part.ops, values[1:], strict=False):
                        if isinstance(op, (ast.Is, ast.IsNot)) and any(
                            isinstance(value, ast.Name)
                            and value.id in parameters
                            and isinstance(other, ast.Constant)
                            and other.value is None
                            for value, other in ((left, right), (right, left))
                        ):
                            self.add("branch:none", part)
        if _range_present(nodes):
            self.add("range:check", node)

    def walk(self, node, locals_, parameters, depth=0):
        if isinstance(node, ast.AnnAssign):
            # Local annotation expressions do not supply runtime body features.
            self.walk(node.target, locals_, parameters, depth)
            if node.value is not None:
                self.walk(node.value, locals_, parameters, depth)
            return
        if isinstance(node, ast.GeneratorExp):
            if depth >= MAX_GENERATORS:
                raise FeatureExtractionError("study_generator_depth_exceeded")
            bound = {
                part.id
                for generator in node.generators
                for part in ast.walk(generator.target)
                if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store)
            }
            inner, inner_parameters = locals_ | bound, parameters - bound
            for index, generator in enumerate(node.generators):
                self.walk(
                    generator.iter,
                    locals_ if index == 0 else inner,
                    parameters if index == 0 else inner_parameters,
                    depth + 1,
                )
                for test in generator.ifs:
                    self.condition(test, inner_parameters)
                    self.walk(test, inner, inner_parameters, depth + 1)
            if isinstance(node.elt, (ast.Compare, ast.BoolOp)):
                self.condition(node.elt, inner_parameters, branches=False)
            self.walk(node.elt, inner, inner_parameters, depth + 1)
            return
        if isinstance(node, (ast.If, ast.IfExp)):
            self.condition(node.test, parameters)
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Mult):
                self.add("decimal:multiply", node)
            elif isinstance(node.op, ast.Sub):
                self.add("decimal:subtract", node)
        if isinstance(node, ast.Call):
            resolved = _resolved_name(node.func, self.bindings, locals_)
            if resolved == "builtins.int" or (
                isinstance(node.func, ast.Name)
                and node.func.id == "int"
                and "int" not in locals_ | self.module_names
            ):
                self.add("int:parse", node)
            if resolved == "re.fullmatch":
                pattern = (
                    node.args[0]
                    if node.args
                    else next((kw.value for kw in node.keywords if kw.arg == "pattern"), None)
                )
                if isinstance(pattern, ast.Constant) and pattern.value in ("[0-9]", "[0-9]+"):
                    self.add("regex:ascii_digits", node)
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("isascii", "isdecimal"):
                self.add(f"str:{node.func.attr}", node)
        if (
            isinstance(node, (ast.Name, ast.Attribute))
            and isinstance(node.ctx, ast.Load)
            and (_resolved_name(node, self.bindings, locals_) == "decimal.ROUND_HALF_UP")
        ):
            self.add("round:half_up", node)
        for child in ast.iter_child_nodes(node):
            self.walk(child, locals_, parameters, depth)


def _signature(args):
    # Shape, not parameter names, literal defaults, types, return annotations or outcomes.
    kw_defaults = "".join("0" if value is None else "1" for value in args.kw_defaults)
    return (
        f"{SIGNATURE}:posonly={len(args.posonlyargs)};poskw={len(args.args)};"
        f"defaults={len(args.defaults)};vararg={int(args.vararg is not None)};"
        f"kwonly={len(args.kwonlyargs)};kwdefaults={kw_defaults};"
        f"varkw={int(args.kwarg is not None)}"
    )


def extract_study_features(source: bytes, context: StudyFeatureContext, *, context_anchor: Digest):
    """The separate trusted anchor is required; self-consistent caller JSON is insufficient."""
    context = _exact(context, StudyFeatureContext)
    _require(
        context.artifact_digest == context_anchor == digest_json_artifact(context),
        "study_feature_context_anchor_mismatch",
    )
    _require(type(source) is bytes, "study_feature_source_requires_bytes")
    _require(digest_bytes(source) == context.source_digest, "study_feature_source_digest_mismatch")
    tree, function = _parse(source, context.symbol)
    extractor = _Extractor(tree)
    locals_, parameters = _function_bindings(function), _parameters(function.args)
    for statement in function.body:
        extractor.walk(statement, locals_, parameters)
    witnesses = tuple(extractor.witnesses[key] for key in sorted(extractor.witnesses))
    features = FeatureVector(
        contract_family=context.contract_family,
        contract_version=context.contract_version,
        interface_kind=context.interface_kind,
        symbol_signature=_signature(function.args),
        module_group=context.module_group,
        ast_features=frozenset(w.token for w in witnesses),
    )
    return _seal(
        StudyFeatureRecord(
            vocabulary_digest=VOCABULARY_PIN,
            context_digest=context.artifact_digest,
            source_digest=context.source_digest,
            implementation_digests=inspection_implementation_digests(),
            features=features,
            witnesses=witnesses,
            artifact_digest=ZERO,
        )
    )


def audit_study_features(source, context, expected, *, context_anchor):
    """Keep both sides on mismatch; neither the annotation nor extractor adjudicates itself."""
    expected = _exact(expected, FeatureVector)
    record = extract_study_features(source, context, context_anchor=context_anchor)
    actual = record.features
    metadata = tuple(
        field
        for field in sorted(type(expected).model_fields)
        if field != "ast_features" and getattr(actual, field) != getattr(expected, field)
    )
    missing = tuple(sorted(expected.ast_features - actual.ast_features))
    unexpected = tuple(sorted(actual.ast_features - expected.ast_features))
    return _seal(
        StudyFeatureAudit(
            record=record,
            expected=expected,
            expected_digest=digest_bytes(canonical_json_bytes(expected)),
            matched=not (metadata or missing or unexpected),
            missing=missing,
            unexpected=unexpected,
            metadata_mismatches=metadata,
            artifact_digest=ZERO,
        )
    )


def study_training_example(features: FeatureVector, guard_applicable: bool):
    """Explicit projection only. No records, source IDs, context basis or labels-as-features."""
    features = _exact(features, FeatureVector)
    if type(guard_applicable) is not bool:
        raise TypeError("Research applicability must be an explicitly reviewed bool")
    return TrainingExample(features=features, guard_applicable=guard_applicable)


def verify_study_feature_record(record, source, context, *, context_anchor):
    """Rebuild witnesses, metadata and implementation pins, not just the self-digest."""
    record = _exact(record, StudyFeatureRecord)
    rebuilt = extract_study_features(source, context, context_anchor=context_anchor)
    _require(record == rebuilt, "study_feature_record_does_not_rebuild")
    return rebuilt


def verify_study_feature_audit(audit, source, context, *, context_anchor):
    audit = _exact(audit, StudyFeatureAudit)
    rebuilt = audit_study_features(source, context, audit.expected, context_anchor=context_anchor)
    _require(audit == rebuilt, "study_feature_audit_does_not_rebuild")
    return rebuilt


def verify_target_feature_audit(target, files, context, audit):
    """Target consumers share definition identity checks without reading any labels."""
    definition = (target.source_ref, target.symbol)
    if target.profile == "static-reexport-v2":
        export = resolve_static_reexport(
            files,
            module=target.module,
            symbol=target.symbol,
            import_root=target.import_root,
            algorithm="static-root-reexport.v2",
        )
        definition = (export["definition_ref"], export["definition_symbol"])
    _require(
        context.source_ref in {p.path for p in target.closure_pins}
        and (context.source_ref, context.symbol) == definition,
        "study_feature_subject_changed",
    )
    return verify_study_feature_audit(
        audit, files[context.source_ref], context, context_anchor=context.artifact_digest
    )
