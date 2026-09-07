"""Create a non-destructive still preview of a thinner Blob Track overlay."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from skimage.morphology import skeletonize


def blob_line_mask(frame: np.ndarray) -> np.ndarray:
    blue, green, red = cv2.split(frame)
    return (
        (blue.astype(np.int16) - red.astype(np.int16) > 42)
        & (green.astype(np.int16) - red.astype(np.int16) > 18)
        & (blue > 145)
        & (green > 115)
    ).astype(np.uint8) * 255


def render_frame(frame: np.ndarray, line_width: float) -> np.ndarray:
    mask = blob_line_mask(frame)
    cleanup_mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    clean_frame = cv2.inpaint(frame, cleanup_mask, 3, cv2.INPAINT_TELEA)
    thin_mask = skeletonize(mask > 0)

    line_color = np.array([255, 200, 100], dtype=np.uint8)
    if line_width == 0.5:
        height, width = clean_frame.shape[:2]
        result = cv2.resize(
            clean_frame,
            (width * 2, height * 2),
            interpolation=cv2.INTER_CUBIC,
        )
        doubled_mask = cv2.resize(
            thin_mask.astype(np.uint8),
            (width * 2, height * 2),
            interpolation=cv2.INTER_NEAREST,
        )
        subpixel_mask = skeletonize(doubled_mask > 0)
        result[subpixel_mask] = line_color
        result = cv2.resize(result, (width, height), interpolation=cv2.INTER_AREA)
    elif line_width == 1.0:
        result = clean_frame.copy()
        result[thin_mask] = line_color
    else:
        raise ValueError("Preview line width must be 0.5 or 1.0")
    return result


def render_preview(source: Path, destination: Path, line_width: float) -> None:
    frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"Could not read {source}")

    result = render_frame(frame, line_width)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), result):
        raise RuntimeError(f"Could not write {destination}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--line-width", type=float, choices=(0.5, 1.0), default=1.0)
    args = parser.parse_args()
    render_preview(args.source, args.destination, args.line_width)


if __name__ == "__main__":
    main()
