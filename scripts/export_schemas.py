"""Export the public persistence contracts from their authoritative models."""

import json
from pathlib import Path

from evidenceguard.baselines import FeatureVector, ScopePredicate
from evidenceguard.change_analysis import InspectionReport
from evidenceguard.demo import DemoReport
from evidenceguard.evaluation import EvaluationReport
from evidenceguard.evaluation_metrics import EvaluationMetrics, Prediction
from evidenceguard.features import FeatureRecord
from evidenceguard.independent_verifier import (
    AgentContext,
    CandidateRecord,
    CandidateTest,
    VerificationRequest,
)
from evidenceguard.models import Evidence, Guard, RunRecord
from evidenceguard.module_context import ModuleContext
from evidenceguard.pipeline import PipelineFailure, PipelineManifest
from evidenceguard.project_config import ProjectConfig
from evidenceguard.protocol import ExperimentProtocol, SplitManifest
from evidenceguard.replay import ReplayResult
from evidenceguard.report import CommandReport, ReplayPresentation
from evidenceguard.repository import RepositorySnapshot
from evidenceguard.scope import FitManifest, ScopeLearningResult, TrainingExample
from evidenceguard.scope_explanations import ScopeExplanation
from evidenceguard.verification_gate import GateResult
from evidenceguard.workspace import PipelineScenario, WorkspaceManifest

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
