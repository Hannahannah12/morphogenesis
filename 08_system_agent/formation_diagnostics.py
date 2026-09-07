"""Create a timestamped contact sheet for formation-onset diagnostics."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=None)
    parser.add_argument("--metrics", action="store_true")
    args = parser.parse_args()

    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {args.video}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fourcc_value = int(capture.get(cv2.CAP_PROP_FOURCC))
    codec = "".join(
        chr((fourcc_value >> (8 * index)) & 0xFF)
        for index in range(4)
    )
    duration = frame_count / fps
    end = min(duration, args.end) if args.end is not None else duration
    timestamps = np.arange(max(0.0, args.start), end, args.interval)

    width, height = 320, 180
    cells: list[np.ndarray] = []
    reference_roi: np.ndarray | None = None
    for timestamp in timestamps:
        capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp * 1000))
        ok, frame = capture.read()
        if not ok:
            continue
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        if args.metrics:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            roi = gray[14:166, 24:296]
            illumination = cv2.GaussianBlur(roi, (0, 0), 7)
            highpass = cv2.absdiff(roi, illumination)
            local_normalized = cv2.normalize(
                roi.astype(np.float32),
                None,
                0,
                255,
                cv2.NORM_MINMAX,
            ).astype(np.uint8)
            if reference_roi is None:
                reference_roi = local_normalized
            reference_difference = cv2.absdiff(local_normalized, reference_roi)
            sobel_x = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
            gradient = cv2.magnitude(sobel_x, sobel_y)
            print(json.dumps({
                "time": round(float(timestamp), 3),
                "edgeDensity": round(float((gradient > 28).mean()), 5),
                "highpassCoverage": round(float((highpass > 7).mean()), 5),
                "gradientMean": round(float(gradient.mean()), 4),
                "laplacianVariance": round(
                    float(cv2.Laplacian(roi, cv2.CV_32F).var()),
                    4,
                ),
                "referenceChange12": round(
                    float((reference_difference > 12).mean()),
                    5,
                ),
                "referenceChange20": round(
                    float((reference_difference > 20).mean()),
                    5,
                ),
            }))
        cv2.rectangle(frame, (0, 0), (112, 26), (0, 0, 0), -1)
        cv2.putText(
            frame,
            f"{timestamp:06.1f} s",
            (8, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (143, 220, 255),
            1,
            cv2.LINE_AA,
        )
        cells.append(frame)
    capture.release()

    columns = 4
    rows = math.ceil(len(cells) / columns)
    sheet = np.zeros((rows * height, columns * width, 3), dtype=np.uint8)
    for index, cell in enumerate(cells):
        row, column = divmod(index, columns)
        sheet[row * height : (row + 1) * height, column * width : (column + 1) * width] = cell
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), sheet):
        raise RuntimeError(f"Could not write {args.output}")
    print(f"duration={duration:.3f}")
    print(f"codec={codec}")
    print(f"samples={len(cells)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
