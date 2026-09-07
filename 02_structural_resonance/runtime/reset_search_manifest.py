"""Reset saved search metadata without touching patches or analysis videos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH_FIELDS = (
    "apiErrors",
    "candidateCount",
    "candidateCountByBranch",
    "candidateSource",
    "patchQualityAudit",
    "patchSelectionMethod",
    "selectedPatchIndices",
    "patchPreprocessing",
    "rankingMode",
    "resonanceSets",
    "searchBranches",
    "searchPipeline",
    "searchResultLayout",
    "searchResultsPerPatch",
)


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def reset_manifest(path: Path) -> None:
    path = path.resolve()
    if PROJECT_ROOT not in path.parents:
        raise ValueError(f"Manifest is outside the project: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for field in SEARCH_FIELDS:
        payload.pop(field, None)
    payload["resonanceSets"] = []
    payload["searchState"] = "waiting"
    payload["searchPolicy"] = (
        "6 representative patches / contrast 5 + structure 5"
    )
    write_json(path, payload)

    try:
        crystal_root = path.parents[1]
        is_exhibition = (
            crystal_root.parent.name == "exhibition"
            and path.parent.name == "02_structural_resonance"
        )
    except IndexError:
        is_exhibition = False
    if not is_exhibition:
        print(f"reset: {path}", flush=True)
        return

    crystal = crystal_root.name
    session_path = crystal_root / "session.json"
    if session_path.exists():
        session = json.loads(session_path.read_text(encoding="utf-8"))
        structural = session.get("directions", {}).get(
            "02_structural_resonance",
        )
        if isinstance(structural, dict):
            structural["resonanceCount"] = 0
            structural["searchState"] = "waiting"
            structural["searchBranches"] = ["contrast", "structure"]
            structural["message"] = (
                "DINO video and patches are ready / dual search waiting"
            )
            write_json(session_path, session)

    runtime_path = (
        PROJECT_ROOT / "08_system_agent" / "runtime" / "experiment.json"
    )
    if runtime_path.exists():
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        if runtime.get("crystal") == crystal:
            structural = runtime.get("jobs", {}).get("structural")
            if isinstance(structural, dict):
                structural["resonanceCount"] = 0
                structural["searchState"] = "waiting"
                structural["searchBranches"] = ["contrast", "structure"]
                structural["message"] = (
                    "DINO video and patches are ready / dual search waiting"
                )
                write_json(runtime_path, runtime)
    print(f"reset: {path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.manifests:
        reset_manifest(path)


if __name__ == "__main__":
    main()
