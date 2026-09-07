"""Formal Material Analysis video pipeline extracted from the research notebook.

The four visual methods preserve the notebook's processing rules while making
input, output, crop, and browser encoding configurable for the System Agent.
Research masters are written as MP4; exhibition copies are written from the
same processed frames as VP8 WebM, so the website does not use a second visual
approximation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


ProgressCallback = Callable[[str, float, str], None]
METHODS = ("edge", "threshold", "spacetime", "motion")


def notify(
    callback: ProgressCallback | None,
    channel: str,
    progress: float,
    message: str,
) -> None:
    line = f"[{channel.upper()}] {progress * 100:6.2f}% / {message}"
    print(line, flush=True)
    if callback:
        callback(channel, max(0.0, min(1.0, progress)), message)


def open_capture(path: Path) -> tuple[cv2.VideoCapture, float, int]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open source video: {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    return capture, fps, frame_total


def square_frame(frame: np.ndarray, size: int) -> np.ndarray:
    height, width = frame.shape[:2]
    side = min(height, width)
    x = max(0, (width - side) // 2)
    y = max(0, (height - side) // 2)
    crop = frame[y : y + side, x : x + side]
    if crop.shape[0] == size and crop.shape[1] == size:
        return crop
    interpolation = cv2.INTER_AREA if side > size else cv2.INTER_CUBIC
    return cv2.resize(crop, (size, size), interpolation=interpolation)


def create_writer(path: Path, codec: str, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, size)
    if not writer.isOpened():
        raise RuntimeError(f"Could not create {codec} video: {path}")
    return writer


def render_frame_methods(
    source: Path,
    analysis_dir: Path,
    exhibition_dir: Path,
    start_seconds: float,
    size: int,
    web_size: int,
    web_fps: float,
    callback: ProgressCallback | None,
) -> tuple[dict[str, Path], dict[str, Path], list[np.ndarray], float]:
    capture, fps, frame_total = open_capture(source)
    start_frame = min(frame_total - 1, max(0, round(start_seconds * fps)))
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    retained_total = max(1, frame_total - start_frame)
    web_sample_every = max(1, round(fps / web_fps))
    actual_web_fps = fps / web_sample_every

    masters = {
        "edge": analysis_dir / "edge.mp4",
        "threshold": analysis_dir / "threshold.mp4",
        "motion": analysis_dir / "method4_Motion History Image.mp4",
    }
    web = {
        "edge": exhibition_dir / "01_edge.webm",
        "threshold": exhibition_dir / "02_threshold.webm",
        "motion": exhibition_dir / "04_motion.webm",
    }
    master_writers = {
        method: create_writer(path, "mp4v", fps, (size, size))
        for method, path in masters.items()
    }
    web_writers = {
        method: create_writer(path, "VP80", actual_web_fps, (web_size, web_size))
        for method, path in web.items()
    }

    ok, first_raw = capture.read()
    if not ok:
        capture.release()
        raise RuntimeError("No frame was available after the requested start time")
    first = square_frame(first_raw, size)
    first_gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    background = cv2.GaussianBlur(first_gray, (5, 5), 0)
    previous_gray = first_gray
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(8, 8))
    edge_kernel = np.ones((3, 3), np.uint8)
    threshold_kernel = np.ones((2, 2), np.uint8)
    rows = [min(size - 1, round(size * row / 1080)) for row in (200, 400, 600, 800)]
    row_slices: dict[int, list[np.ndarray]] = {row: [] for row in rows}

    notify(callback, "edge", 0, "background frame locked / blur 5x5 / diff threshold 25")
    notify(callback, "threshold", 0, "CLAHE 1.0 / adaptive Gaussian block 21 / C 5")
    notify(callback, "motion", 0, "frame difference threshold 15 / MAGMA colour map")
    notify(
        callback,
        "spacetime",
        0,
        "sampling notebook rows " + " / ".join(str(row) for row in rows),
    )

    frame_index = 0
    frame = first
    try:
        while True:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            difference = cv2.absdiff(background, cv2.GaussianBlur(gray, (5, 5), 0))
            _, edge_threshold = cv2.threshold(difference, 25, 255, cv2.THRESH_BINARY)
            edge_threshold = cv2.morphologyEx(
                edge_threshold,
                cv2.MORPH_OPEN,
                edge_kernel,
            )
            edge_threshold = cv2.morphologyEx(
                edge_threshold,
                cv2.MORPH_CLOSE,
                edge_kernel,
            )
            edges = cv2.Canny(edge_threshold, 10, 50)
            edge_bgr = cv2.cvtColor(cv2.bitwise_not(edges), cv2.COLOR_GRAY2BGR)

            enhanced = clahe.apply(gray)
            threshold_blur = cv2.GaussianBlur(enhanced, (3, 3), 0)
            threshold = cv2.adaptiveThreshold(
                threshold_blur,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                21,
                5,
            )
            threshold = cv2.morphologyEx(
                threshold,
                cv2.MORPH_OPEN,
                threshold_kernel,
            )
            threshold_bgr = cv2.cvtColor(threshold, cv2.COLOR_GRAY2BGR)

            motion_difference = cv2.absdiff(previous_gray, gray)
            _, motion_level = cv2.threshold(
                motion_difference,
                15,
                255,
                cv2.THRESH_TOZERO,
            )
            motion_bgr = cv2.applyColorMap(motion_level, cv2.COLORMAP_MAGMA)
            previous_gray = gray

            for row in rows:
                row_slices[row].append(gray[row, :].copy())

            rendered = {
                "edge": edge_bgr,
                "threshold": threshold_bgr,
                "motion": motion_bgr,
            }
            for method, output_frame in rendered.items():
                master_writers[method].write(output_frame)
                if frame_index % web_sample_every == 0:
                    web_writers[method].write(
                        cv2.resize(
                            output_frame,
                            (web_size, web_size),
                            interpolation=cv2.INTER_AREA,
                        )
                    )

            frame_index += 1
            if frame_index % 60 == 0 or frame_index == retained_total:
                progress = min(1.0, frame_index / retained_total)
                for method in ("edge", "threshold", "motion"):
                    notify(
                        callback,
                        method,
                        progress,
                        f"frame {frame_index:04d}/{retained_total:04d}",
                    )
                notify(
                    callback,
                    "spacetime",
                    progress * 0.45,
                    f"row samples {frame_index:04d}/{retained_total:04d}",
                )

            ok, raw = capture.read()
            if not ok:
                break
            frame = square_frame(raw, size)
    finally:
        capture.release()
        for writer in master_writers.values():
            writer.release()
        for writer in web_writers.values():
            writer.release()

    return masters, web, [np.asarray(row_slices[row], dtype=np.uint8) for row in rows], fps


def render_spacetime(
    row_matrices: list[np.ndarray],
    fps: float,
    analysis_dir: Path,
    exhibition_dir: Path,
    size: int,
    web_size: int,
    web_fps: float,
    callback: ProgressCallback | None,
) -> tuple[Path, Path]:
    total_frames = row_matrices[0].shape[0]
    master_path = analysis_dir / "spacetime_4rows.mp4"
    web_path = exhibition_dir / "03_spacetime.webm"
    master = create_writer(master_path, "mp4v", fps, (size, size))
    web_sample_every = max(1, round(fps / web_fps))
    web = create_writer(
        web_path,
        "VP80",
        fps / web_sample_every,
        (web_size, web_size),
    )
    gap = max(6, round(size * 0.012))
    panel_height = (size - gap * 3) // 4

    try:
        for frame_index in range(1, total_frames + 1):
            canvas = np.zeros((size, size), dtype=np.uint8)
            for panel_index, matrix in enumerate(row_matrices):
                history = matrix[:frame_index]
                rendered = cv2.resize(
                    history,
                    (size, panel_height),
                    interpolation=cv2.INTER_AREA,
                )
                y = panel_index * (panel_height + gap)
                canvas[y : y + panel_height] = rendered
            canvas_bgr = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
            master.write(canvas_bgr)
            if (frame_index - 1) % web_sample_every == 0:
                web.write(
                    cv2.resize(
                        canvas_bgr,
                        (web_size, web_size),
                        interpolation=cv2.INTER_AREA,
                    )
                )
            if frame_index % 45 == 0 or frame_index == total_frames:
                notify(
                    callback,
                    "spacetime",
                    0.45 + 0.55 * frame_index / total_frames,
                    f"growing four-row field {frame_index:04d}/{total_frames:04d}",
                )
    finally:
        master.release()
        web.release()
    return master_path, web_path


def run_material_pipeline(
    source: Path,
    analysis_dir: Path,
    exhibition_dir: Path,
    start_seconds: float = 0,
    size: int = 1080,
    web_size: int = 720,
    web_fps: float = 15,
    callback: ProgressCallback | None = None,
) -> dict[str, object]:
    source = source.resolve()
    analysis_dir.mkdir(parents=True, exist_ok=True)
    exhibition_dir.mkdir(parents=True, exist_ok=True)
    masters, web, rows, fps = render_frame_methods(
        source,
        analysis_dir,
        exhibition_dir,
        start_seconds,
        size,
        web_size,
        web_fps,
        callback,
    )
    spacetime_master, spacetime_web = render_spacetime(
        rows,
        fps,
        analysis_dir,
        exhibition_dir,
        size,
        web_size,
        web_fps,
        callback,
    )
    masters["spacetime"] = spacetime_master
    web["spacetime"] = spacetime_web
    ordered_web = [
        web["edge"],
        web["threshold"],
        web["spacetime"],
        web["motion"],
    ]
    manifest = {
        "pipeline": "formal-notebook-material-analysis",
        "source": str(source),
        "startSeconds": start_seconds,
        "processingSize": [size, size],
        "masterCodec": "mp4v",
        "masterOutputs": {key: str(value) for key, value in masters.items()},
        "exhibitionCodec": "VP8",
        "exhibitionOutputs": [str(path) for path in ordered_web],
    }
    (analysis_dir / "material_pipeline_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for method in METHODS:
        notify(callback, method, 1, "writer closed / output complete")
    return {
        "masters": masters,
        "web": web,
        "orderedWeb": ordered_web,
        "manifest": manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--exhibition-dir", type=Path, required=True)
    parser.add_argument("--start-seconds", type=float, default=0)
    parser.add_argument("--size", type=int, default=1080)
    parser.add_argument("--web-size", type=int, default=720)
    parser.add_argument("--web-fps", type=float, default=15)
    args = parser.parse_args()
    run_material_pipeline(
        source=args.source,
        analysis_dir=args.analysis_dir,
        exhibition_dir=args.exhibition_dir,
        start_seconds=max(0, args.start_seconds),
        size=args.size,
        web_size=args.web_size,
        web_fps=args.web_fps,
    )


if __name__ == "__main__":
    main()
