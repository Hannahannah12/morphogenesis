"""Render representative Exhibition Material frames without writing videos."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from exhibition_pipeline import ExhibitionMaterialProcessor


def label(frame: np.ndarray, text: str) -> np.ndarray:
    result = frame.copy()
    cv2.rectangle(result, (0, 0), (210, 32), (0, 0, 0), -1)
    cv2.putText(
        result,
        text,
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (170, 225, 255),
        1,
        cv2.LINE_AA,
    )
    return result


def render(source: Path, output: Path, timestamp: float) -> None:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, first = capture.read()
    if not ok:
        raise RuntimeError(f"No frames in {source}")
    processor = ExhibitionMaterialProcessor(first, frame_total)
    target = min(frame_total - 1, max(0, round(timestamp * fps)))
    output_frames = processor.process(first)
    for frame_index in range(1, target + 1):
        ok, frame = capture.read()
        if not ok:
            break
        output_frames = processor.process(frame)
    capture.release()
    preview = np.hstack([
        label(output_frames.edge, "EDGE / NATIVE ANALYSIS"),
        label(output_frames.threshold, "THRESHOLD / NATIVE ANALYSIS"),
        label(output_frames.motion, "MOTION / DEEP BLUE"),
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), preview):
        raise RuntimeError(f"Could not write {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--timestamp", type=float, default=8.0)
    args = parser.parse_args()
    render(args.source, args.output, args.timestamp)


if __name__ == "__main__":
    main()
