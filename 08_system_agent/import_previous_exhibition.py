"""Import selected Notebook-era results into the unified Exhibition layout.

This migration does not rerun either analysis pipeline. It copies only the
assets used by the three exhibition pages, converts recorded videos to H.264
MP4, gives patches stable sequential names, and writes the same manifest/session
shape used by the live Agent pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_INPUT = PROJECT_ROOT / "05_shared_data" / "input"
EXHIBITION_ROOT = PROJECT_ROOT / "05_shared_data" / "exhibition"
PREVIOUS_ROOT = PROJECT_ROOT / "09_experiments" / "previous_tests"

MATERIAL_FILES = {
    "edge": "01_edge.webm",
    "threshold": "02_threshold.webm",
    "spacetime": "03_spacetime.webm",
    "motion": "04_motion.webm",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def numeric_patch_key(path: Path) -> tuple[int, int, str]:
    match = re.fullmatch(r"patch_(\d+)_(\d+)", path.stem)
    if not match:
        return (10**9, 10**9, path.name)
    return (int(match.group(1)), int(match.group(2)), path.name)


def open_video(path: Path) -> tuple[cv2.VideoCapture, float, int, int, int]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return capture, fps, frames, width, height


def create_h264_writer(
    path: Path,
    fps: float,
    size: tuple[int, int],
) -> cv2.VideoWriter:
    deadline = time.monotonic() + 10
    while True:
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"avc1"),
            fps,
            size,
        )
        if writer.isOpened():
            return writer
        writer.release()
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Could not create H.264 MP4: {path}")
        time.sleep(0.25)


def fit_frame(
    frame: np.ndarray,
    size: tuple[int, int],
    background: tuple[int, int, int],
) -> np.ndarray:
    target_width, target_height = size
    height, width = frame.shape[:2]
    scale = min(target_width / width, target_height / height)
    resized_width = max(2, round(width * scale / 2) * 2)
    resized_height = max(2, round(height * scale / 2) * 2)
    interpolation = cv2.INTER_AREA if scale <= 1 else cv2.INTER_CUBIC
    resized = cv2.resize(
        frame,
        (resized_width, resized_height),
        interpolation=interpolation,
    )
    canvas = np.empty((target_height, target_width, 3), dtype=np.uint8)
    canvas[:] = background
    x = (target_width - resized_width) // 2
    y = (target_height - resized_height) // 2
    canvas[y : y + resized_height, x : x + resized_width] = resized
    return canvas


def transcode(
    source: Path,
    destination: Path,
    size: tuple[int, int],
    *,
    background: tuple[int, int, int] = (0, 0, 0),
    force: bool = False,
) -> dict[str, float | int | str]:
    if destination.exists() and not force:
        capture, fps, frames, width, height = open_video(destination)
        capture.release()
        return {
            "path": destination.as_posix(),
            "fps": round(fps, 3),
            "frames": frames,
            "width": width,
            "height": height,
            "duration": round(frames / max(fps, 0.001), 3),
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.importing.mp4")
    temporary.unlink(missing_ok=True)
    capture, fps, frame_total, _, _ = open_video(source)
    writer = create_h264_writer(temporary, fps, size)
    written = 0
    try:
        while True:
            available, frame = capture.read()
            if not available:
                break
            writer.write(fit_frame(frame, size, background))
            written += 1
            if written % 300 == 0:
                print(
                    f"{destination.name}: {written}/{frame_total}",
                    flush=True,
                )
    finally:
        capture.release()
        writer.release()
    if written == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"No frames were decoded from {source}")
    temporary.replace(destination)
    print(f"written: {destination}", flush=True)
    return {
        "path": destination.as_posix(),
        "fps": round(fps, 3),
        "frames": written,
        "width": size[0],
        "height": size[1],
        "duration": round(written / max(fps, 0.001), 3),
    }


def split_structural_panels(
    combined: Path,
    attention_destination: Path,
    blob_destination: Path,
    *,
    force: bool = False,
) -> None:
    if (
        attention_destination.exists()
        and blob_destination.exists()
        and not force
    ):
        return
    capture, fps, frame_total, width, height = open_video(combined)
    split_x = width // 2
    destinations = {
        "attention": attention_destination,
        "blob": blob_destination,
    }
    temporary = {
        name: path.with_name(f"{path.stem}.importing.mp4")
        for name, path in destinations.items()
    }
    writers: dict[str, cv2.VideoWriter] = {}
    try:
        for path in destinations.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        for path in temporary.values():
            path.unlink(missing_ok=True)
        writers["attention"] = create_h264_writer(
            temporary["attention"],
            fps,
            (720, 720),
        )
        writers["blob"] = create_h264_writer(
            temporary["blob"],
            fps,
            (720, 720),
        )
        written = 0
        while True:
            available, frame = capture.read()
            if not available:
                break
            attention = frame[:, :split_x]
            blob = frame[:, split_x:]
            writers["attention"].write(
                fit_frame(attention, (720, 720), (0, 0, 0))
            )
            writers["blob"].write(
                fit_frame(blob, (720, 720), (0, 0, 0))
            )
            written += 1
            if written % 300 == 0:
                print(
                    f"split {combined.name}: {written}/{frame_total}",
                    flush=True,
                )
    finally:
        capture.release()
        for writer in writers.values():
            writer.release()
    for name, path in destinations.items():
        temporary[name].replace(path)
        print(f"written: {path}", flush=True)


def parse_result_name(path: Path) -> dict[str, object]:
    stem = path.stem
    method_match = re.match(r"^(clip|hog|canny|threshold)_", stem, re.I)
    method = method_match.group(1).lower() if method_match else "legacy"
    without_method = re.sub(
        r"^(clip|hog|canny|threshold)_",
        "",
        stem,
        flags=re.I,
    )
    score_match = re.search(r"_(-?\d+(?:\.\d+)?)$", without_method)
    score = float(score_match.group(1)) if score_match else None
    label = re.sub(r"^\d+_", "", without_method)
    if score_match:
        label = label[: score_match.start()].rstrip("_")
    return {
        "provider": "previous_test",
        "method": method,
        "score": score,
        "category": label or "unlabelled",
        "legacyFile": path.name,
    }


def select_legacy_results(directory: Path, limit: int = 10) -> list[Path]:
    images = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ),
        key=lambda path: path.name.lower(),
    )
    primary = [path for path in images if re.match(r"^\d{2}_", path.name)]
    clip = [path for path in images if path.name.lower().startswith("clip_")]
    remaining = [path for path in images if path not in primary and path not in clip]
    selected: list[Path] = []
    for group in (primary, clip, remaining):
        for path in group:
            if path not in selected:
                selected.append(path)
            if len(selected) >= limit:
                return selected
    return selected


def copy_structural_assets(
    crystal: str,
    destination: Path,
    *,
    force: bool,
) -> tuple[dict[str, object], dict[str, float | int | str]]:
    previous = (
        PREVIOUS_ROOT
        / "02_structural_resonance"
        / "output"
        / crystal
    )
    structural_dir = destination / "02_structural_resonance"
    patch_source = previous / "attention_maps" / "patches"
    patch_destination = structural_dir / "patches"
    patch_destination.mkdir(parents=True, exist_ok=True)

    video_info = transcode(
        previous / "exhibition" / "attention_blob.webm",
        structural_dir / "attention_blob.mp4",
        (1440, 720),
        force=force,
    )
    split_structural_panels(
        structural_dir / "attention_blob.mp4",
        structural_dir / "attention_map.mp4",
        structural_dir / "blob_track.mp4",
        force=force,
    )

    source_patches = sorted(
        (
            path
            for path in patch_source.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ),
        key=numeric_patch_key,
    )
    patches: list[str] = []
    metadata: list[dict[str, object]] = []
    for index, source_patch in enumerate(source_patches, start=1):
        name = f"patch_{index:02d}.jpg"
        target = patch_destination / name
        if force or not target.exists():
            shutil.copy2(source_patch, target)
        relative = f"patches/{name}"
        patches.append(relative)
        frame, source_index, _ = numeric_patch_key(source_patch)
        metadata.append(
            {
                "path": relative,
                "sourceFile": source_patch.name,
                "frame": None if frame >= 10**9 else frame,
                "sourcePatchIndex": None if source_index >= 10**9 else source_index,
            }
        )

    resonance_sets: list[dict[str, object]] = []
    legacy_search_dirs = sorted(
        (
            path
            for path in patch_source.iterdir()
            if path.is_dir() and re.fullmatch(r"patch_\d+", path.name)
        ),
        key=lambda path: int(path.name.removeprefix("patch_")),
    )
    for legacy_patch_dir in legacy_search_dirs:
        old_index = int(legacy_patch_dir.name.removeprefix("patch_"))
        if old_index >= len(patches):
            continue
        result_source = legacy_patch_dir / "found_photos"
        if not result_source.exists():
            continue
        selected = select_legacy_results(result_source)
        if not selected:
            continue
        set_name = f"patch_{old_index + 1:02d}"
        result_destination = structural_dir / "search_results" / set_name
        result_destination.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, object]] = []
        for result_index, source_result in enumerate(selected, start=1):
            result_name = f"{result_index:02d}.jpg"
            target = result_destination / result_name
            if force or not target.exists():
                shutil.copy2(source_result, target)
            result = {
                "url": (
                    f"/05_shared_data/exhibition/{crystal}/"
                    f"02_structural_resonance/search_results/{set_name}/{result_name}"
                ),
                **parse_result_name(source_result),
            }
            results.append(result)
        resonance_sets.append(
            {
                "patchIndex": old_index,
                "patch": (
                    f"/05_shared_data/exhibition/{crystal}/"
                    f"02_structural_resonance/{patches[old_index]}"
                ),
                "keywords": sorted(
                    {
                        str(result["category"])
                        for result in results
                        if result.get("category")
                    }
                ),
                "clipResults": [
                    result
                    for result in results
                    if result.get("method") in {"clip", "legacy"}
                ],
                "hogResults": [
                    result for result in results if result.get("method") == "hog"
                ],
                "results": results,
            }
        )

    manifest: dict[str, object] = {
        "pipeline": "migrated-notebook-recorded",
        "source": (
            f"/05_shared_data/exhibition/{crystal}/source/crystallization.mp4"
        ),
        "model": "vit_base_patch16_224.dino",
        "selectionMethod": "original-notebook-patch-sequence",
        "video": "attention_blob.mp4",
        "videos": {
            "combined": "attention_blob.mp4",
            "attentionMap": "attention_map.mp4",
            "blobTrack": "blob_track.mp4",
        },
        "patches": patches,
        "patchMetadata": metadata,
        "resonanceSets": resonance_sets,
        "migration": {
            "source": (
                f"09_experiments/previous_tests/02_structural_resonance/"
                f"output/{crystal}"
            ),
            "note": (
                "Copied from the tested Notebook output; no structural analysis "
                "or image search was rerun."
            ),
        },
    }
    manifest_path = structural_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest, video_info


def import_crystal(crystal: str, *, force: bool) -> Path:
    destination = EXHIBITION_ROOT / crystal
    material_previous = (
        PREVIOUS_ROOT
        / "01_material_analysis"
        / "output"
        / crystal
        / "exhibition"
    )
    material_destination = destination / "01_material_analysis"

    source_info = transcode(
        SHARED_INPUT / f"{crystal}.mp4",
        destination / "source" / "crystallization.mp4",
        (1280, 720),
        force=force,
    )

    material_urls: list[str] = []
    for method, legacy_name in MATERIAL_FILES.items():
        transcode(
            material_previous / legacy_name,
            material_destination / f"{method}.mp4",
            (720, 720),
            background=(255, 255, 255),
            force=force,
        )
        material_urls.append(
            f"/05_shared_data/exhibition/{crystal}/"
            f"01_material_analysis/{method}.mp4"
        )

    structural, structural_video = copy_structural_assets(
        crystal,
        destination,
        force=force,
    )
    now = utc_now()
    structural_video_urls = {
        name: (
            f"/05_shared_data/exhibition/{crystal}/"
            f"02_structural_resonance/{filename}"
        )
        for name, filename in structural["videos"].items()
    }
    session = {
        "schemaVersion": 1,
        "pipeline": "morphogenesis-exhibition-migrated",
        "crystal": crystal,
        "outputLayout": "per-crystal",
        "sessionRootUrl": f"/05_shared_data/exhibition/{crystal}",
        "rawSourceUrl": f"/05_shared_data/input/{crystal}.mp4",
        "createdAt": now,
        "updatedAt": now,
        "phase": "outputs_ready",
        "detection": {
            "state": "historical_recording",
            "onsetSeconds": None,
            "trimStartSeconds": None,
            "confidence": None,
            "method": "Previous Notebook test; detection metadata was not recorded",
        },
        "playback": {
            "revision": 1,
            "stage": "recorded_source",
            "url": (
                f"/05_shared_data/exhibition/{crystal}/source/crystallization.mp4"
            ),
            "startedAtEpochMs": None,
            "offsetSeconds": 0,
            "durationSeconds": source_info["duration"],
        },
        "directions": {
            "01_material_analysis": {
                "state": "complete",
                "progress": 1.0,
                "message": "Four tested Notebook exhibition streams imported",
                "updatedAt": now,
                "outputUrls": material_urls,
                "pipeline": "previous-notebook-exhibition",
                "resolution": "720x720",
            },
            "02_structural_resonance": {
                "state": "complete",
                "progress": 1.0,
                "message": (
                    f"DINO video, {len(structural['patches'])} patches and "
                    f"{len(structural['resonanceSets'])} saved search sets imported"
                ),
                "updatedAt": now,
                "outputUrl": (
                    f"/05_shared_data/exhibition/{crystal}/"
                    "02_structural_resonance/attention_blob.mp4"
                ),
                "outputUrls": list(structural_video_urls.values()),
                "videoUrls": structural_video_urls,
                "manifestUrl": (
                    f"/05_shared_data/exhibition/{crystal}/"
                    "02_structural_resonance/manifest.json"
                ),
                "patchCount": len(structural["patches"]),
                "resonanceCount": len(structural["resonanceSets"]),
                "searchState": (
                    "complete" if structural["resonanceSets"] else "not_recorded"
                ),
                "pipeline": "previous-notebook-dino",
                "resolution": (
                    f"{structural_video['width']}x{structural_video['height']}"
                ),
            },
            "03_diffusion_imagination": {
                "state": "waiting_page",
                "progress": 0.0,
                "message": (
                    "Recorded source is available; historical Diffusion output "
                    "was intentionally not required for this import"
                ),
                "updatedAt": now,
                "sourceUrl": (
                    f"/05_shared_data/exhibition/{crystal}/"
                    "source/crystallization.mp4"
                ),
                "mode": "live",
                "recordingPolicy": "required_one_per_crystal",
                "fallbackPolicy": "synchronized_recording_on_worker_failure",
                "recordingUrl": (
                    f"/05_shared_data/exhibition/{crystal}/"
                    "03_diffusion_imagination/diffusion_capture.mp4"
                ),
            },
        },
    }
    session_path = destination / "session.json"
    session_path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"session: {session_path}", flush=True)
    return session_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "crystals",
        nargs="*",
        default=["ice_crystal_01", "ice_crystal_02"],
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace already imported exhibition files.",
    )
    args = parser.parse_args()
    for crystal in args.crystals:
        if not re.fullmatch(r"ice_crystal_\d{2}", crystal):
            raise ValueError(f"Invalid crystal identifier: {crystal}")
        import_crystal(crystal, force=args.force)


if __name__ == "__main__":
    main()
