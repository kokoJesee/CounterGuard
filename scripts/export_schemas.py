"""Export the public persistence contracts from their authoritative models."""

import json
from pathlib import Path

from counterguard.baselines import FeatureVector, ScopePredicate
from counterguard.change_analysis import InspectionReport
from counterguard.demo import DemoReport
from counterguard.evaluation import EvaluationReport
from counterguard.evaluation_metrics import EvaluationMetrics, Prediction
from counterguard.features import FeatureRecord
from counterguard.independent_verifier import (
    AgentContext,
    CandidateRecord,
    CandidateTest,
    VerificationRequest,
)
from counterguard.models import Evidence, Guard, RunRecord
from counterguard.module_context import ModuleContext
from counterguard.pipeline import PipelineFailure, PipelineManifest
from counterguard.project_config import ProjectConfig
from counterguard.protocol import ExperimentProtocol, SplitManifest
from counterguard.registry import RegistryEntry, RegistryEvent, RegistryIdentity
from counterguard.replay import ReplayResult
from counterguard.report import CommandReport, ReplayPresentation
from counterguard.repository import RepositorySnapshot
from counterguard.runners.docker import DockerExecutionAuthorization, DockerPolicyV1
from counterguard.scope import FitManifest, ScopeLearningResult, TrainingExample
from counterguard.scope_explanations import ScopeExplanation
from counterguard.verification_gate import GateResult
from counterguard.workspace import PipelineScenario, WorkspaceManifest

MODELS = {
    "evidence": Evidence,
    "guard": Guard,
    "run-record": RunRecord,
    "feature-vector": FeatureVector,
    "feature-extraction": FeatureRecord,
    "scope-predicate": ScopePredicate,
    "experiment-protocol": ExperimentProtocol,
    "split-manifest": SplitManifest,
    "module-context": ModuleContext,
    "training-example": TrainingExample,
    "scope-learning": ScopeLearningResult,
    "fit-manifest": FitManifest,
    "replay-result": ReplayResult,
    "scope-explanation": ScopeExplanation,
    "evaluation-report": EvaluationReport,
    "evaluation-metrics": EvaluationMetrics,
    "evaluation-prediction": Prediction,
    "verification-request": VerificationRequest,
    "candidate-test": CandidateTest,
    "agent-context": AgentContext,
    "candidate-record": CandidateRecord,
    "verification-gate": GateResult,
    "pipeline-scenario": PipelineScenario,
    "pipeline-workspace": WorkspaceManifest,
    "pipeline-run": PipelineManifest,
    "pipeline-failure": PipelineFailure,
    "command-report": CommandReport,
    "replay-presentation": ReplayPresentation,
    "demo-report": DemoReport,
    "project-config": ProjectConfig,
    "repository-snapshot": RepositorySnapshot,
    "repository-inspection": InspectionReport,
    "docker-policy": DockerPolicyV1,
    "docker-execution-authorization": DockerExecutionAuthorization,
    "registry": RegistryIdentity,
    "registry-entry": RegistryEntry,
    "registry-event": RegistryEvent,
}

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "schemas"
    root.mkdir(exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (root / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
