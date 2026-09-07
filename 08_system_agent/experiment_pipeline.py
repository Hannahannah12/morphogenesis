"""Recorded-video rehearsal for the Morphogenesis Exhibition Pipeline.

The script treats an existing crystal video as if it came from the live camera:
it detects the first persistent material change, keeps a two-second pre-roll,
and renders Notebook-faithful, browser-ready MP4 outputs while publishing
progress to the System Agent through a JSON state file.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import math
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from formation_growth_detector import (
    detect_formation_completion,
    detect_growth_onset,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_ROOT = PROJECT_ROOT / "05_shared_data" / "input"
EXHIBITION_ROOT = PROJECT_ROOT / "05_shared_data" / "exhibition"
STRUCTURAL_SEARCH_PYTHON = (
    Path.home() / "anaconda3" / "envs" / "crystal" / "python.exe"
)
DEFAULT_STATE_PATH = PROJECT_ROOT / "08_system_agent" / "runtime" / "experiment.json"
TARGET_FPS = 15.0
SQUARE_OUTPUT_SIZE = (720, 720)
LANDSCAPE_OUTPUT_SIZE = (1280, 720)
RECORDED_ENTRY_HOLD_SECONDS = 6.0
STRUCTURAL_PATCH_LOOKBACK_SECONDS = 4.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionState:
    def __init__(self, path: Path, crystal: str, source_path: Path, kind: str) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.data: dict[str, Any] = {
            "id": f"{crystal}-{'live-capture' if kind == 'live_capture' else 'recorded-rehearsal'}",
            "crystal": crystal,
            "kind": kind,
            "phase": "starting",
            "capturePolicy": {
                "mode": "formation_only",
                "sourceMode": kind,
                "recordStartTrigger": "cooling_started" if kind == "live_capture" else "recorded_rehearsal_source",
                "preRollSeconds": 2.0,
                "postCompletionHoldSeconds": 2.0,
                "liveStopCondition": "stable_structural_plateau",
                "offlineStartDetection": "rolling_roi_texture_growth",
                "preserveRawCapture": True,
                "excludeDissolution": True,
            },
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
            "sourceUrl": "/" + source_path.relative_to(PROJECT_ROOT).as_posix(),
            "playback": {
                "revision": 1,
                "stage": "raw",
                "url": "/" + source_path.relative_to(PROJECT_ROOT).as_posix(),
                "startedAtEpochMs": round(time.time() * 1000),
                "offsetSeconds": 0,
                "durationSeconds": None,
            },
            "detection": {
                "state": "waiting",
                "onsetSeconds": None,
                "trimStartSeconds": None,
                "confidence": None,
                "method": "persistent visual change",
            },
            "jobs": {
                "capture": self.job("complete", 1, "Recorded camera source connected"),
                "detection": self.job("running", 0, "Watching for persistent formation"),
                "trim": self.job("waiting", 0, "Waiting for formation onset"),
                "material": self.job("waiting", 0, "Waiting for trimmed source"),
                "structural": self.job("waiting", 0, "Waiting for trimmed source"),
                "diffusion": self.job(
                    "waiting_page",
                    0,
                    "Live Diffusion will use the trimmed source when its GPU worker is ready",
                    mode="live",
                    recordingPolicy="required_one_per_crystal",
                    fallbackPolicy="synchronized_recording_on_worker_failure",
                ),
            },
            "events": [
                self.event("capture", "Recorded crystal video is acting as the live camera"),
            ],
            "console": [
                self.console_line("agent", f"session {crystal}-recorded-rehearsal created"),
                self.console_line("capture", f"opening {source_path.name} as simulated camera input"),
            ],
        }
        self.write()

    @staticmethod
    def job(state: str, progress: float, message: str, **extra: Any) -> dict[str, Any]:
        return {
            "state": state,
            "progress": round(float(progress), 3),
            "message": message,
            "updatedAt": utc_now(),
            **extra,
        }

    @staticmethod
    def event(kind: str, message: str, **extra: Any) -> dict[str, Any]:
        return {"at": utc_now(), "kind": kind, "message": message, **extra}

    @staticmethod
    def console_line(channel: str, message: str) -> dict[str, str]:
        return {"at": utc_now(), "channel": channel, "message": message}

    def log(self, channel: str, message: str) -> None:
        with self.lock:
            self.data.setdefault("console", []).append(self.console_line(channel, message))
            self.data["console"] = self.data["console"][-220:]

    def write(self) -> None:
        with self.lock:
            self.data["updatedAt"] = utc_now()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            payload = json.dumps(self.data, ensure_ascii=False, indent=2)
            temporary.write_text(payload, encoding="utf-8")
            try:
                os.replace(temporary, self.path)
            except PermissionError:
                # OneDrive can briefly lock the destination while indexing it.
                self.path.write_text(payload, encoding="utf-8")
                temporary.unlink(missing_ok=True)

    def phase(self, value: str) -> None:
        with self.lock:
            self.data["phase"] = value
            self.log("state", f"phase -> {value}")
            self.write()

    def update_job(
        self,
        name: str,
        state: str,
        progress: float,
        message: str,
        **extra: Any,
    ) -> None:
        with self.lock:
            self.data["jobs"][name] = self.job(state, progress, message, **extra)
            percent = max(0, min(100, round(float(progress) * 100)))
            self.log(name, f"{state} {percent:03d}% / {message}")
            self.write()

    def add_event(self, kind: str, message: str, **extra: Any) -> None:
        with self.lock:
            self.data["events"].append(self.event(kind, message, **extra))
            self.data["events"] = self.data["events"][-40:]
            self.log(kind, message)
            self.write()

    def set_playback(self, stage: str, url: str, duration: float) -> None:
        with self.lock:
            previous_revision = int(self.data["playback"].get("revision", 0))
            self.data["playback"] = {
                "revision": previous_revision + 1,
                "stage": stage,
                "url": url,
                "startedAtEpochMs": round(time.time() * 1000),
                "offsetSeconds": 0,
                "durationSeconds": round(duration, 3),
            }
            self.log("playback", f"revision {previous_revision + 1} -> {stage} / {url}")
            self.write()


def open_video(path: Path) -> tuple[cv2.VideoCapture, float, int, int, int]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return capture, fps, frames, width, height


def detect_onset(
    path: Path,
    state: SessionState,
) -> tuple[float, float, float | None]:
    def progress(value: float, message: str) -> None:
        state.update_job(
            "detection",
            "running",
            min(0.94, 0.12 + value * 0.82),
            message,
        )

    result = detect_growth_onset(path, progress)
    onset = float(result["onsetSeconds"])
    trim_start = float(result["trimStartSeconds"])
    confidence = float(result["confidence"])
    completion: dict[str, float | str] | None = None
    should_trim_at_completion = state.data.get("kind") in {
        "live_capture",
        "recorded_rehearsal",
    }
    if should_trim_at_completion:
        state.update_job(
            "detection",
            "running",
            0.95,
            "Formation found; locating the fully formed plateau",
        )
        completion = detect_formation_completion(
            path,
            onset,
            str(result["changeDirection"]),
            float(result["baselineCoverage"]),
            float(result["confirmedCoverage"]),
            hold_seconds=2.0,
        )
    state.data["detection"] = {
        "state": "detected",
        "onsetSeconds": round(onset, 3),
        "trimStartSeconds": round(trim_start, 3),
        "confidence": round(float(confidence), 3),
        "method": str(result["method"]),
        "changeDirection": result.get("changeDirection"),
        "baselineCoverage": result.get("baselineCoverage"),
        "confirmedCoverage": result.get("confirmedCoverage"),
        "coverageGrowth": result.get("coverageGrowth"),
        **(completion or {}),
    }
    state.update_job(
        "detection",
        "complete",
        1,
        (
            f"Formation {onset:.1f}s → "
            f"{float(completion['trimEndSeconds']):.1f}s"
            if completion
            else f"Formation detected at {onset:.1f}s"
        ),
    )
    state.add_event(
        "formation",
        (
            f"Formation {onset:.1f}s → {float(completion['completionSeconds']):.1f}s; "
            "preserving two seconds before and after"
            if completion
            else f"Formation begins at {onset:.1f}s; preserving a two-second pre-roll"
        ),
        onsetSeconds=round(onset, 3),
    )
    state.phase("formation_detected")
    trim_end = float(completion["trimEndSeconds"]) if completion else None
    return onset, trim_start, trim_end


def create_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            raise RuntimeError(
                f"Could not create browser-ready H.264 MP4: {path}"
            )
        # A page from the previous session may need one poll cycle to unload.
        time.sleep(0.25)


def exhibition_canvas_size(width: int, height: int) -> tuple[int, int]:
    """Use native exhibition geometry without stretching or centre cropping."""
    aspect = width / max(1, height)
    if 0.9 <= aspect <= 1.1:
        return SQUARE_OUTPUT_SIZE
    return LANDSCAPE_OUTPUT_SIZE


def crop_exhibition_roi(frame: np.ndarray) -> np.ndarray:
    """Remove the plate's top screw-hole border without changing aspect ratio.

    Six percent is removed from the top and three percent from each side. The
    retained width and height are therefore both 94% of the source, so square
    and landscape recordings preserve their original geometry.
    """
    height, width = frame.shape[:2]
    top = min(height - 2, max(0, round(height * 0.06)))
    side = min((width - 2) // 2, max(0, round(width * 0.03)))
    return frame[top:height, side:width - side]


def fit_frame(frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Fit the complete frame into an exhibition canvas with black padding."""
    target_width, target_height = size
    height, width = frame.shape[:2]
    scale = min(target_width / width, target_height / height)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    interpolation = cv2.INTER_AREA if scale <= 1 else cv2.INTER_CUBIC
    resized = cv2.resize(
        frame,
        (resized_width, resized_height),
        interpolation=interpolation,
    )
    canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
    x = (target_width - resized_width) // 2
    y = (target_height - resized_height) // 2
    canvas[y : y + resized_height, x : x + resized_width] = resized
    return canvas


def render_trimmed(
    path: Path,
    output: Path,
    start: float,
    end: float | None,
    state: SessionState,
) -> float:
    capture, fps, frame_total, source_width, source_height = open_video(path)
    output_size = exhibition_canvas_size(source_width, source_height)
    start_frame = round(start * fps)
    end_frame = min(frame_total, round(end * fps)) if end is not None else frame_total
    sample_every = max(1, round(fps / TARGET_FPS))
    output_fps = fps / sample_every
    output_frames = max(1, math.ceil((end_frame - start_frame) / sample_every))
    writer = create_writer(output, output_fps, output_size)
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    source_index = start_frame
    written = 0
    state.update_job("trim", "running", 0, "Removing the inactive cooling interval")
    while source_index < end_frame:
        ok, frame = capture.read()
        if not ok:
            break
        if (source_index - start_frame) % sample_every == 0:
            writer.write(fit_frame(crop_exhibition_roi(frame), output_size))
            written += 1
            if written % 60 == 0:
                state.update_job(
                    "trim",
                    "running",
                    written / output_frames,
                    "Writing the formation clip with two-second pre-roll",
                )
        source_index += 1
    capture.release()
    writer.release()
    duration = written / output_fps
    url = "/" + output.relative_to(PROJECT_ROOT).as_posix()
    state.update_job(
        "trim",
        "complete",
        1,
        "Formation clip ready",
        outputUrl=url,
        resolution=f"{output_size[0]}x{output_size[1]}",
    )
    state.add_event(
        "trim",
        (
            f"Inactive lead-in and post-formation dissolution removed; "
            f"retained clip is {duration:.1f}s"
            if end is not None
            else f"Inactive lead-in removed; retained clip is {duration:.1f}s"
        ),
    )
    state.set_playback("trimmed_source", url, duration)
    state.phase("source_ready")
    return duration


def render_material_exhibition(
    source: Path,
    trim_start: float,
    trim_end: float | None,
    output_dir: Path,
    state: SessionState,
) -> list[str]:
    runtime_dir = PROJECT_ROOT / "01_material_analysis" / "runtime"
    if str(runtime_dir) not in sys.path:
        sys.path.insert(0, str(runtime_dir))
    from exhibition_pipeline import ExhibitionMaterialProcessor

    capture, fps, frame_total, source_width, source_height = open_video(source)
    output_size = exhibition_canvas_size(source_width, source_height)
    start_frame = min(frame_total - 1, max(0, round(trim_start * fps)))
    end_frame = (
        min(frame_total, max(start_frame + 1, round(trim_end * fps)))
        if trim_end is not None
        else frame_total
    )
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    sample_every = max(1, round(fps / TARGET_FPS))
    output_fps = fps / sample_every
    retained_source_frames = max(1, end_frame - start_frame)
    retained_output_frames = max(
        1,
        math.ceil(retained_source_frames / sample_every),
    )
    paths = {
        "edge": output_dir / "edge.mp4",
        "threshold": output_dir / "threshold.mp4",
        "spacetime": output_dir / "spacetime.mp4",
        "motion": output_dir / "motion.mp4",
    }
    ok, first_raw = capture.read()
    if not ok:
        capture.release()
        raise RuntimeError("No source frame was available for Exhibition Material")
    writers = {
        method: create_writer(path, output_fps, output_size)
        for method, path in paths.items()
    }
    first_roi = crop_exhibition_roi(first_raw)
    processor = ExhibitionMaterialProcessor(
        first_roi,
        total_frames=retained_source_frames,
        output_size=output_size,
    )
    state.log(
        "material",
        (
            "Notebook-faithful one-pass Exhibition processor initialised / "
            f"{output_size[0]}x{output_size[1]}"
        ),
    )
    state.log("edge", "Notebook cells 2/3 / fixed background / threshold 25 / Canny 10:50")
    state.log("threshold", "Notebook cells 5/6 / CLAHE 1.0 / block 21 / C 5")
    state.log("spacetime", "Notebook cells 10/11 / growing rows 200 / 400 / 600 / 800")
    state.log(
        "motion",
        "Notebook cells 13/14 / adjacent-frame difference / threshold 15",
    )
    state.update_job(
        "material",
        "running",
        0,
        "Notebook-faithful Exhibition Analysis is processing",
        pipeline="notebook-faithful-exhibition-material",
        resolution=f"{output_size[0]}x{output_size[1]}",
    )

    source_index = start_frame
    written = 0
    raw = first_raw
    try:
        while source_index < end_frame:
            outputs = processor.process(crop_exhibition_roi(raw)).as_dict()
            if (source_index - start_frame) % sample_every == 0:
                for method, rendered in outputs.items():
                    writers[method].write(rendered)
                written += 1
                if written % 45 == 0 or written == retained_output_frames:
                    progress = min(1.0, written / retained_output_frames)
                    for method in ("edge", "threshold", "spacetime", "motion"):
                        state.log(
                            method,
                            (
                                f"frame {written:04d}/{retained_output_frames:04d} / "
                                f"{progress * 100:05.1f}%"
                            ),
                        )
                    state.update_job(
                        "material",
                        "running",
                        progress,
                        (
                            "Four Notebook-faithful streams / "
                            f"frame {written}/{retained_output_frames}"
                        ),
                        pipeline="notebook-faithful-exhibition-material",
                    )
            source_index += 1
            ok, raw = capture.read()
            if not ok:
                break
    finally:
        capture.release()
        for writer in writers.values():
            writer.release()

    urls = [
        "/" + paths[method].relative_to(PROJECT_ROOT).as_posix()
        for method in ("edge", "threshold", "spacetime", "motion")
    ]
    for method, url in zip(("edge", "threshold", "spacetime", "motion"), urls):
        state.log(method, f"Exhibition stream ready / {url}")
    state.update_job(
        "material",
        "complete",
        1,
        "Four Notebook-faithful Exhibition streams are ready",
        outputUrls=urls,
        pipeline="notebook-faithful-exhibition-material",
        resolution=f"{output_size[0]}x{output_size[1]}",
    )
    state.add_event("material", "01 / Notebook-faithful Exhibition Analysis became available")
    return urls


def render_structural(
    trimmed: Path,
    output: Path,
    state: SessionState,
    patch_start_seconds: float | None = None,
) -> str:
    module_path = (
        PROJECT_ROOT
        / "02_structural_resonance"
        / "runtime"
        / "exhibition_pipeline.py"
    )
    specification = importlib.util.spec_from_file_location(
        "morphogenesis_structural_exhibition",
        module_path,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load structural pipeline: {module_path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)

    def report(channel: str, progress: float, message: str) -> None:
        state.log(channel, message)
        state.update_job(
            "structural",
            "running",
            progress,
            message,
            pipeline="notebook-faithful-dino-structural",
        )

    state.update_job(
        "structural",
        "running",
        0,
        "Loading Notebook DINO structural pipeline",
        pipeline="notebook-faithful-dino-structural",
    )
    result = module.run_structural_pipeline(
        trimmed,
        output.parent,
        patch_start_seconds=patch_start_seconds,
        callback=report,
    )
    video_path = Path(result["video"])
    video_urls = {
        name: "/" + Path(path).relative_to(PROJECT_ROOT).as_posix()
        for name, path in result["videos"].items()
    }
    manifest_path = Path(result["manifest"])
    url = video_urls["combined"]
    manifest_url = "/" + manifest_path.relative_to(PROJECT_ROOT).as_posix()
    patch_count = len(result["patches"])
    candidate_patch_count = patch_count
    search_patch_limit = min(10, patch_count)
    search_state = "pending"
    resonance_count = 0
    search_worker = (
        PROJECT_ROOT
        / "02_structural_resonance"
        / "runtime"
        / "search_worker.py"
    )
    if STRUCTURAL_SEARCH_PYTHON.exists():
        state.update_job(
            "structural",
            "searching",
            0.94,
            (
                "iNaturalist/NASA + CLIP/HOG dual search / "
                f"{search_patch_limit} representative patches of {patch_count}"
            ),
            outputUrl=url,
            outputUrls=list(video_urls.values()),
            videoUrls=video_urls,
            manifestUrl=manifest_url,
            patchCount=patch_count,
            searchState="running",
            pipeline="notebook-faithful-dino-inaturalist-nasa-clip-hog",
        )
        state.log(
            "resonance",
            "Notebook iNaturalist + NASA APIs / CLIP ViT-B/32 + HOG search",
        )
        completed = subprocess.run(
            [
                str(STRUCTURAL_SEARCH_PYTHON),
                str(search_worker),
                str(manifest_path),
                "--max-patches",
                str(search_patch_limit),
                "--top-k",
                "5",
            ],
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        if completed.returncode == 0:
            search_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            patch_count = len(search_manifest.get("patches", []))
            search_state = str(search_manifest.get("searchState", "complete"))
            resonance_count = len(search_manifest.get("resonanceSets", []))
            state.log(
                "resonance",
                f"search complete / {resonance_count} patch resonance sets",
            )
        else:
            search_state = "error"
            state.log(
                "resonance",
                "search error / " + completed.stderr.strip()[-500:],
            )
    else:
        state.log(
            "resonance",
            "search waiting / crystal Conda environment was not found",
        )
    state.log(
        "structural",
        (
            f"DINO writer closed / {patch_count} retained of "
            f"{candidate_patch_count} candidate patches / {url}"
        ),
    )
    state.update_job(
        "structural",
        "complete",
        1,
        (
            f"DINO attention, {patch_count} retained patches and "
            f"{resonance_count} resonance sets are ready"
        ),
        outputUrl=url,
        outputUrls=list(video_urls.values()),
        videoUrls=video_urls,
        manifestUrl=manifest_url,
        candidatePatchCount=candidate_patch_count,
        patchCount=patch_count,
        resonanceCount=resonance_count,
        searchState=search_state,
        pipeline="notebook-faithful-dino-inaturalist-nasa-clip-hog",
        resolution=result["videoResolution"],
    )
    state.add_event(
        "structural",
        "02 / DINO attention and Notebook patch extraction became available",
    )
    return url


def write_session_manifest(session_dir: Path, state: SessionState) -> Path:
    """Snapshot the completed crystal session beside all Exhibition assets."""
    manifest_path = session_dir / "session.json"
    payload = {
        "schemaVersion": 1,
        "pipeline": "morphogenesis-exhibition",
        "crystal": state.data["crystal"],
        "outputLayout": "single-current",
        "capturePolicy": state.data["capturePolicy"],
        "sessionRootUrl": "/" + session_dir.relative_to(PROJECT_ROOT).as_posix(),
        "rawSourceUrl": state.data["sourceUrl"],
        "createdAt": state.data["createdAt"],
        "updatedAt": utc_now(),
        "phase": state.data["phase"],
        "detection": state.data["detection"],
        "playback": state.data["playback"],
        "directions": {
            "01_material_analysis": state.data["jobs"]["material"],
            "02_structural_resonance": state.data["jobs"]["structural"],
            "03_diffusion_imagination": state.data["jobs"]["diffusion"],
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.replace(temporary, manifest_path)
    except PermissionError:
        # OneDrive can briefly lock the destination while indexing it.
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.unlink(missing_ok=True)
    return manifest_path


def run(
    crystal: str,
    state_path: Path,
    source_override: Path | None = None,
    kind: str = "recorded_rehearsal",
    showcase_seconds: int = 300,
    trimmed_name: str = "crystallization.mp4",
    allow_full_clip: bool = False,
) -> None:
    source = (source_override or (INPUT_ROOT / f"{crystal}.mp4")).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    session_dir = EXHIBITION_ROOT / crystal
    source_dir = session_dir / "source"
    material_dir = session_dir / "01_material_analysis"
    structural_dir = session_dir / "02_structural_resonance"
    diffusion_dir = session_dir / "03_diffusion_imagination"
    for directory in (
        source_dir,
        material_dir,
        structural_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    state = SessionState(state_path, crystal, source, kind)
    state.data["sessionRootUrl"] = (
        "/" + session_dir.relative_to(PROJECT_ROOT).as_posix()
    )
    state.data["outputLayout"] = "single-current"
    state.write()
    try:
        capture, fps, frame_total, _, _ = open_video(source)
        capture.release()
        source_duration = frame_total / fps
        state.data["playback"]["durationSeconds"] = round(source_duration, 3)
        state.write()
        state.phase("observing")
        state.update_job(
            "detection",
            "running",
            0,
            "Simulated live entry / awaiting visible formation",
        )
        state.add_event(
            "capture",
            "Shared live entry is visible on 01, 02 and 03",
        )
        if kind != "live_capture":
            time.sleep(RECORDED_ENTRY_HOLD_SECONDS)
        try:
            _, trim_start, trim_end = detect_onset(source, state)
        except RuntimeError:
            if not allow_full_clip:
                raise
            trim_start, trim_end = 0.0, source_duration
            state.data["detection"] = {
                "state": "full_clip",
                "onsetSeconds": 0,
                "trimStartSeconds": 0,
                "trimEndSeconds": round(source_duration, 3),
                "method": "operator-provided crystallization clip",
            }
            state.update_job(
                "detection",
                "complete",
                1,
                "Operator-provided crystallization clip / full duration retained",
            )
            state.add_event(
                "formation",
                "No separate onset required; the supplied source is already a crystallization clip",
            )

        trimmed = source_dir / Path(trimmed_name).name
        render_trimmed(source, trimmed, trim_start, trim_end, state)

        state.phase("processing")
        structural_output = structural_dir / "attention_blob.mp4"
        detection = state.data.get("detection") or {}
        completion_seconds = detection.get("completionSeconds")
        structural_patch_start_seconds = (
            max(
                0.0,
                float(completion_seconds)
                - float(trim_start)
                - STRUCTURAL_PATCH_LOOKBACK_SECONDS,
            )
            if completion_seconds is not None
            else None
        )
        state.add_event(
            "dispatch",
            (
                "Material and Structural workers started in parallel; "
                "Structural attention covers the full clip; patches use the "
                "four-second near-completion window"
            ),
            structuralPatchStartSeconds=structural_patch_start_seconds,
        )
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="exhibition") as pool:
            material_future = pool.submit(
                render_material_exhibition,
                source,
                trim_start,
                trim_end,
                material_dir,
                state,
            )
            structural_future = pool.submit(
                render_structural,
                trimmed,
                structural_output,
                state,
                structural_patch_start_seconds,
            )
            material_future.result()
            structural_future.result()

        state.update_job(
            "diffusion",
            "waiting_page",
            0,
            "Trimmed source is ready; Diffusion will play live when its GPU worker is ready",
            sourceUrl="/" + trimmed.relative_to(PROJECT_ROOT).as_posix(),
            mode="live",
            recordingPolicy="required_one_per_crystal",
            fallbackPolicy="synchronized_recording_on_worker_failure",
            recordingUrl=(
                "/"
                + (diffusion_dir / "diffusion_capture.mp4")
                .relative_to(PROJECT_ROOT)
                .as_posix()
            ),
        )
        state.phase("outputs_ready")
        state.add_event("session", "Recorded rehearsal processing is complete")
        session_manifest = write_session_manifest(session_dir, state)
        state.log(
            "session",
            "manifest ready / "
            + "/"
            + session_manifest.relative_to(PROJECT_ROOT).as_posix(),
        )
        state.write()
    except Exception as error:
        state.data["phase"] = "error"
        state.data["error"] = f"{type(error).__name__}: {error}"
        state.add_event("error", state.data["error"])
        state.write()
        write_session_manifest(session_dir, state)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crystal", default="ice_crystal_03")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--kind", choices=["recorded_rehearsal", "live_capture"], default="recorded_rehearsal")
    parser.add_argument("--showcase-seconds", type=int, default=300)
    parser.add_argument("--trimmed-name", default="crystallization.mp4")
    parser.add_argument("--allow-full-clip", action="store_true")
    args = parser.parse_args()
    crystal_number = args.crystal.removeprefix("ice_crystal_")
    if (
        not args.crystal.startswith("ice_crystal_")
        or len(crystal_number) != 2
        or not crystal_number.isdigit()
    ):
        raise ValueError("Crystal must be named like ice_crystal_03")
    run(
        args.crystal,
        args.state,
        args.source,
        args.kind,
        args.showcase_seconds,
        args.trimmed_name,
        args.allow_full_clip,
    )


if __name__ == "__main__":
    main()
