"""Re-render existing Exhibition Material sessions without rerunning detection.

The retained formation clip is the only input. Outputs are written to temporary
MP4 files and atomically replace the current exhibition files after all four
writers close successfully. Raw camera media and the other research directions
are never modified.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import time

import cv2

from exhibition_pipeline import (
    ExhibitionMaterialProcessor,
    exhibition_canvas_size,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXHIBITION_ROOT = PROJECT_ROOT / "05_shared_data" / "exhibition"
TARGET_FPS = 15.0
METHODS = ("edge", "threshold", "spacetime", "motion")


def create_writer(
    path: Path,
    fps: float,
    size: tuple[int, int],
) -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"avc1"),
        fps,
        size,
    )
    if not writer.isOpened():
        writer.release()
        raise RuntimeError(f"Could not create browser-ready H.264 MP4: {path}")
    return writer


def replace_with_retry(source: Path, destination: Path) -> None:
    deadline = time.monotonic() + 12.0
    while True:
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.3)


def render(crystal: str) -> None:
    session_root = EXHIBITION_ROOT / crystal
    source = session_root / "source" / "crystallization.mp4"
    output_dir = session_root / "01_material_analysis"
    if not source.exists():
        raise FileNotFoundError(source)

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, first = capture.read()
    if not ok:
        capture.release()
        raise RuntimeError(f"No readable frames in {source}")

    sample_every = max(1, round(fps / TARGET_FPS))
    output_fps = fps / sample_every
    output_frames = max(1, math.ceil(frame_total / sample_every))
    output_size = exhibition_canvas_size(first)
    temporary = {
        method: output_dir / f".{method}.rendering.mp4"
        for method in METHODS
    }
    final = {
        method: output_dir / f"{method}.mp4"
        for method in METHODS
    }
    writers = {
        method: create_writer(path, output_fps, output_size)
        for method, path in temporary.items()
    }
    processor = ExhibitionMaterialProcessor(
        first,
        total_frames=frame_total,
        output_size=output_size,
    )

    frame_index = 0
    written = 0
    raw = first
    try:
        while True:
            outputs = processor.process(raw).as_dict()
            if frame_index % sample_every == 0:
                for method, rendered in outputs.items():
                    writers[method].write(rendered)
                written += 1
                if written % 90 == 0 or written == output_frames:
                    percent = min(100.0, written / output_frames * 100)
                    print(
                        f"{crystal}: {written}/{output_frames} "
                        f"frames ({percent:.1f}%)",
                        flush=True,
                    )
            frame_index += 1
            ok, raw = capture.read()
            if not ok:
                break
    finally:
        capture.release()
        for writer in writers.values():
            writer.release()

    if written == 0:
        raise RuntimeError(f"No output frames were written for {crystal}")
    for method in METHODS:
        replace_with_retry(temporary[method], final[method])
    print(
        f"{crystal}: complete / {written / output_fps:.3f}s / "
        f"{output_size[0]}x{output_size[1]}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "crystals",
        nargs="+",
        help="Session names such as ice_crystal_01",
    )
    args = parser.parse_args()
    for crystal in args.crystals:
        if not crystal.startswith("ice_crystal_"):
            raise ValueError(f"Invalid session name: {crystal}")
        render(crystal)


if __name__ == "__main__":
    main()
