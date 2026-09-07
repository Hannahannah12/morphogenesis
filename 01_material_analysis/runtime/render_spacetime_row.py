"""Render one Notebook space-time sampling row as its own exhibition video."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from exhibition_pipeline import exhibition_canvas_size


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


def render(
    source: Path,
    destination: Path,
    *,
    source_row: int = 200,
    reference_height: int = 1080,
    target_fps: float = 15.0,
    force: bool = False,
) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() and not force:
        raise FileExistsError(
            f"{destination} already exists; pass --force to replace it"
        )

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")
    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or target_fps)
    frame_total = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    sample_every = max(1, round(source_fps / target_fps))
    output_fps = source_fps / sample_every
    available, first_frame = capture.read()
    if not available:
        capture.release()
        raise RuntimeError("The source contains no readable frames")

    source_height, source_width = first_frame.shape[:2]
    sampled_row = min(
        source_height - 1,
        round(source_height * source_row / reference_height),
    )
    output_size = exhibition_canvas_size(first_frame)
    canvas = np.full((frame_total, source_width, 3), 255, dtype=np.uint8)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.rendering.mp4")
    temporary.unlink(missing_ok=True)
    writer = create_h264_writer(temporary, output_fps, output_size)
    frame = first_frame
    frame_index = 0
    written = 0
    try:
        while True:
            canvas[min(frame_index, frame_total - 1), :] = frame[sampled_row, :]
            if frame_index % sample_every == 0:
                display = cv2.resize(canvas, output_size, interpolation=cv2.INTER_AREA)
                writer.write(display)
                written += 1
            frame_index += 1
            if frame_index % 300 == 0 or frame_index == frame_total:
                print(
                    f"row {source_row}: {frame_index}/{frame_total} "
                    f"({written} written)",
                    flush=True,
                )
            available, frame = capture.read()
            if not available:
                break
    finally:
        capture.release()
        writer.release()

    if written == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("No output frames were written")
    temporary.replace(destination)
    print(f"written: {destination}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--row", type=int, default=200)
    parser.add_argument("--target-fps", type=float, default=15.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    render(
        args.source,
        args.destination,
        source_row=args.row,
        target_fps=args.target_fps,
        force=args.force,
    )


if __name__ == "__main__":
    main()
