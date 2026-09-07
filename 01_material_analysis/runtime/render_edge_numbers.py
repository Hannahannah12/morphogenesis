"""Burn the exhibition's live edge measurements into a derived H.264 video."""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import cv2


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


def edge_readings(frame, sample_width: int = 240) -> list[tuple[int, int, float]]:
    height, width = frame.shape[:2]
    sample_height = max(100, round(sample_width * height / width))
    sample = cv2.resize(frame, (sample_width, sample_height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    readings: list[tuple[int, int, float]] = []
    for y in range(3, sample_height - 3, 2):
        for x in range(3, sample_width - 3, 2):
            center = int(gray[y, x])
            if center > 205:
                continue
            contrast = max(
                abs(center - int(gray[y, x - 2])),
                abs(center - int(gray[y, x + 2])),
                abs(center - int(gray[y - 2, x])),
                abs(center - int(gray[y + 2, x])),
            )
            if contrast < 20:
                continue
            strength = min(99.9, (contrast * 0.72 + (255 - center) * 0.28) / 2.55)
            readings.append((x, y, strength))

    readings.sort(key=lambda item: item[2], reverse=True)
    selected: list[tuple[int, int, float]] = []
    for reading in readings:
        if any(math.hypot(other[0] - reading[0], other[1] - reading[1]) < 11 for other in selected):
            continue
        selected.append(reading)
        if len(selected) >= 60:
            break

    scale_x = width / sample_width
    scale_y = height / sample_height
    return [
        (round(x * scale_x), round(y * scale_y), strength)
        for x, y, strength in selected
    ]


def annotate(frame):
    output = frame.copy()
    height, width = output.shape[:2]
    for index, (x, y, strength) in enumerate(edge_readings(frame), start=1):
        label = f"{index:02d}  {strength:.1f}"
        text_x = min(width - 68, max(2, x + 4))
        text_y = min(height - 3, max(8, y - 4))
        cv2.putText(
            output,
            label,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.24,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return output


def render(source: Path, destination: Path, *, force: bool = False) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() and not force:
        raise FileExistsError(f"{destination} already exists; pass --force to replace it")

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 15.0)
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.rendering.mp4")
    temporary.unlink(missing_ok=True)
    writer = create_h264_writer(temporary, fps, (width, height))

    written = 0
    try:
        while True:
            available, frame = capture.read()
            if not available:
                break
            writer.write(annotate(frame))
            written += 1
            if written % 150 == 0 or written == frame_total:
                print(f"edge numbers: {written}/{frame_total}", flush=True)
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
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    render(args.source, args.destination, force=args.force)


if __name__ == "__main__":
    main()
