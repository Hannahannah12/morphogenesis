"""Combine Attention Map and Blob Track into a separate exhibition video."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def combine(attention_path: Path, blob_path: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")

    attention = cv2.VideoCapture(str(attention_path))
    blob = cv2.VideoCapture(str(blob_path))
    if not attention.isOpened() or not blob.isOpened():
        attention.release()
        blob.release()
        raise RuntimeError("Could not open both component videos")

    fps = float(attention.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(attention.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(attention.get(cv2.CAP_PROP_FRAME_HEIGHT))
    blob_width = int(blob.get(cv2.CAP_PROP_FRAME_WIDTH))
    blob_height = int(blob.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (width, height) != (blob_width, blob_height):
        attention.release()
        blob.release()
        raise RuntimeError("Attention Map and Blob Track dimensions do not match")

    temporary = destination.with_name(f"{destination.stem}.rendering{destination.suffix}")
    writer = cv2.VideoWriter(
        str(temporary),
        cv2.VideoWriter_fourcc(*"avc1"),
        fps,
        (width * 2, height),
    )
    if not writer.isOpened():
        attention.release()
        blob.release()
        raise RuntimeError(f"Could not create {temporary}")

    frame_index = 0
    try:
        while True:
            attention_ok, attention_frame = attention.read()
            blob_ok, blob_frame = blob.read()
            if not attention_ok or not blob_ok:
                break
            writer.write(np.hstack((attention_frame, blob_frame)))
            frame_index += 1
            if frame_index % 120 == 0:
                print(f"frames {frame_index}", flush=True)
    finally:
        attention.release()
        blob.release()
        writer.release()

    if frame_index == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("No combined frames were rendered")
    temporary.replace(destination)
    print(f"written: {destination} / {frame_index} frames", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attention", type=Path)
    parser.add_argument("blob", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    combine(args.attention, args.blob, args.destination)


if __name__ == "__main__":
    main()
