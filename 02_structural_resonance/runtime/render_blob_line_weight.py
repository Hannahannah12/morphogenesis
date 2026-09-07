"""Render a separate Blob Track video with a lighter overlay line weight.

The source video is never overwritten. Existing detections are retained while
only the cyan overlay is reconstructed at the requested visual weight.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from preview_blob_line_weight import render_frame


def render_video(source: Path, destination: Path, line_width: float) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Destination must be different from the source video")
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    temporary = destination.with_name(f"{destination.stem}.rendering{destination.suffix}")
    writer = cv2.VideoWriter(
        str(temporary),
        cv2.VideoWriter_fourcc(*"avc1"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Could not create {temporary}")

    completed = False
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            writer.write(render_frame(frame, line_width))
            frame_index += 1
            if frame_index % 60 == 0 or frame_index == frame_total:
                print(f"frames {frame_index}/{frame_total}", flush=True)
        completed = frame_index > 0
    finally:
        capture.release()
        writer.release()

    if not completed:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("No video frames were rendered")
    temporary.replace(destination)
    print(f"written: {destination}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--line-width", type=float, choices=(0.5, 1.0), default=0.5)
    args = parser.parse_args()
    render_video(args.source, args.destination, args.line_width)


if __name__ == "__main__":
    main()
