"""Export clause witnesses from existing fits; no capture, refit, or execution."""

import argparse
import json
from pathlib import Path

from evidenceguard.errors import EvidenceGuardError
from evidenceguard.scope_explanations import explain_fitted_scopes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New explanation directory")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        explanations = explain_fitted_scopes(args.fit, output=args.output, cwd=args.cwd)
    except (EvidenceGuardError, OSError, ValueError) as error:
        parser.exit(2, f"Explanation rejected: {error}\n")
    print(json.dumps({key: item.artifact_digest for key, item in explanations.items()}, indent=2))


if __name__ == "__main__":
    main()
