"""Split recorded Structural combined panels and update Exhibition metadata."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_splitter():
    module_path = PROJECT_ROOT / "08_system_agent" / "import_previous_exhibition.py"
    specification = importlib.util.spec_from_file_location(
        "morphogenesis_previous_exhibition_import",
        module_path,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load splitter from {module_path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.split_structural_panels


def project_url(path: Path) -> str:
    return "/" + path.relative_to(PROJECT_ROOT).as_posix()


def update_json(path: Path, callback) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    callback(payload)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def split_crystal(crystal: str, *, force: bool = False) -> None:
    root = PROJECT_ROOT / "05_shared_data" / "exhibition" / crystal
    structural = root / "02_structural_resonance"
    paths = {
        "combined": structural / "attention_blob.mp4",
        "attentionMap": structural / "attention_map.mp4",
        "blobTrack": structural / "blob_track.mp4",
    }
    manifest_path = structural / "manifest.json"
    manifest_metadata = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    resonance_sets = manifest_metadata.get("resonanceSets", [])
    searched_patch_count = len(
        {
            item.get("patchIndex")
            for item in resonance_sets
            if isinstance(item, dict)
        }
    )
    search_result_count = sum(
        len(item.get("results", []))
        for item in resonance_sets
        if isinstance(item, dict)
    )
    splitter = load_splitter()
    splitter(
        paths["combined"],
        paths["attentionMap"],
        paths["blobTrack"],
        force=force,
    )

    def update_manifest(payload: dict[str, object]) -> None:
        payload["video"] = paths["combined"].name
        payload["videos"] = {
            name: path.name
            for name, path in paths.items()
        }

    def update_session(payload: dict[str, object]) -> None:
        directions = payload.get("directions")
        if not isinstance(directions, dict):
            return
        structural_state = directions.get("02_structural_resonance")
        if not isinstance(structural_state, dict):
            return
        urls = {
            name: project_url(path)
            for name, path in paths.items()
        }
        structural_state["outputUrl"] = urls["combined"]
        structural_state["outputUrls"] = list(urls.values())
        structural_state["videoUrls"] = urls
        structural_state["resonanceCount"] = len(
            manifest_metadata.get("resonanceSets", [])
        )
        structural_state["searchState"] = manifest_metadata.get(
            "searchState",
            structural_state.get("searchState", "pending"),
        )
        structural_state["searchBranches"] = manifest_metadata.get(
            "searchBranches",
            [],
        )
        structural_state["searchPatchCount"] = searched_patch_count
        structural_state["searchResultCount"] = search_result_count
        structural_state["candidatePatchCount"] = manifest_metadata.get(
            "candidatePatchCount",
            len(manifest_metadata.get("patches", [])),
        )
        structural_state["patchCount"] = len(
            manifest_metadata.get("patches", [])
        )
        suffix = " / combined, attention map and blob track videos available"
        message = str(
            structural_state.get("message", "Structural output is ready")
        )
        if not message.endswith(suffix):
            structural_state["message"] = message + suffix
        if manifest_metadata.get("searchState") == "complete":
            structural_state["message"] = (
                f"{searched_patch_count} representative patches / "
                f"{search_result_count} dual-search images ready"
            )

    def update_runtime(payload: dict[str, object]) -> None:
        if payload.get("crystal") != crystal:
            return
        jobs = payload.get("jobs")
        if not isinstance(jobs, dict):
            return
        structural_job = jobs.get("structural")
        if not isinstance(structural_job, dict):
            return
        urls = {
            name: project_url(path)
            for name, path in paths.items()
        }
        structural_job["outputUrl"] = urls["combined"]
        structural_job["outputUrls"] = list(urls.values())
        structural_job["videoUrls"] = urls
        structural_job["resonanceCount"] = len(
            manifest_metadata.get("resonanceSets", [])
        )
        structural_job["searchState"] = manifest_metadata.get(
            "searchState",
            structural_job.get("searchState", "pending"),
        )
        structural_job["searchBranches"] = manifest_metadata.get(
            "searchBranches",
            [],
        )
        structural_job["searchPatchCount"] = searched_patch_count
        structural_job["searchResultCount"] = search_result_count
        structural_job["candidatePatchCount"] = manifest_metadata.get(
            "candidatePatchCount",
            len(manifest_metadata.get("patches", [])),
        )
        structural_job["patchCount"] = len(
            manifest_metadata.get("patches", [])
        )
        if manifest_metadata.get("searchState") == "complete":
            structural_job["message"] = (
                f"{searched_patch_count} representative patches / "
                f"{search_result_count} dual-search images ready"
            )

    update_json(manifest_path, update_manifest)
    update_json(root / "session.json", update_session)
    update_json(
        PROJECT_ROOT / "08_system_agent" / "runtime" / "experiment.json",
        update_runtime,
    )
    print(f"metadata: {crystal}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "crystals",
        nargs="*",
        default=["ice_crystal_01", "ice_crystal_02", "ice_crystal_03"],
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for crystal in args.crystals:
        split_crystal(crystal, force=args.force)


if __name__ == "__main__":
    main()
