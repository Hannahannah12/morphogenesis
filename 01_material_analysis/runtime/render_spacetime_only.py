"""Rebuild only the Exhibition space-time video from an existing source clip."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from exhibition_pipeline import ExhibitionMaterialProcessor, exhibition_canvas_size


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
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_every = max(1, round(source_fps / target_fps))
    output_fps = source_fps / sample_every
    available, first_frame = capture.read()
    if not available:
        capture.release()
        raise RuntimeError("The source contains no readable frames")
    output_size = exhibition_canvas_size(first_frame)
    processor = ExhibitionMaterialProcessor(
        first_frame,
        total_frames=frame_total,
        output_size=output_size,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.rendering.mp4")
    temporary.unlink(missing_ok=True)
    writer = create_h264_writer(temporary, output_fps, output_size)
    frame_index = 0
    written = 0
    frame = first_frame
    try:
        while True:
            spacetime = processor.process(frame).spacetime
            if frame_index % sample_every == 0:
                writer.write(spacetime)
                written += 1
            frame_index += 1
            if frame_index % 150 == 0 or frame_index == frame_total:
                print(
                    f"spacetime: {frame_index}/{frame_total} "
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
    parser.add_argument("--target-fps", type=float, default=15.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    render(
        args.source,
        args.destination,
        target_fps=args.target_fps,
        force=args.force,
    )


if __name__ == "__main__":
    main()
