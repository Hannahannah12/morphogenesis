"""Create a non-destructive stabilized source and rebuild Material outputs."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from exhibition_pipeline import ExhibitionMaterialProcessor, exhibition_canvas_size


METHODS = ("edge", "threshold", "spacetime", "motion")


def create_h264_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def moving_average(curve: np.ndarray, radius: int) -> np.ndarray:
    if len(curve) == 0 or radius <= 0:
        return curve.copy()
    padded = np.pad(curve, (radius, radius), mode="edge")
    kernel = np.ones(radius * 2 + 1, dtype=np.float64) / (radius * 2 + 1)
    return np.convolve(padded, kernel, mode="same")[radius:-radius]


def smooth_trajectory(trajectory: np.ndarray, radius: int) -> np.ndarray:
    result = trajectory.copy()
    for axis in range(trajectory.shape[1]):
        result[:, axis] = moving_average(trajectory[:, axis], radius)
    return result


def subpixel_peak(response: np.ndarray, x: int, y: int) -> tuple[float, float]:
    def offset(before: float, center: float, after: float) -> float:
        denominator = before - 2 * center + after
        if abs(denominator) < 1e-9:
            return 0.0
        return float(np.clip(0.5 * (before - after) / denominator, -0.75, 0.75))

    dx = 0.0
    dy = 0.0
    if 0 < x < response.shape[1] - 1:
        dx = offset(response[y, x - 1], response[y, x], response[y, x + 1])
    if 0 < y < response.shape[0] - 1:
        dy = offset(response[y - 1, x], response[y, x], response[y + 1, x])
    return x + dx, y + dy


def estimate_fixed_lock(
    source: Path,
    *,
    anchor_points: list[tuple[float, float]] | None = None,
    search_pad_ratio: float = 0.03,
    max_translation: float = 14.0,
    max_rotation_degrees: float = 1.0313,
) -> tuple[np.ndarray, dict[str, float | int]]:
    """Lock every frame directly to two static plate screws in frame one."""
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, first = capture.read()
    if not ok:
        capture.release()
        raise RuntimeError(f"No readable frames in {source}")

    height, width = first.shape[:2]
    first_gray = cv2.GaussianBlur(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    circles = cv2.HoughCircles(
        cv2.medianBlur(first_gray, 7),
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=round(width * 0.12),
        param1=80,
        param2=24,
        minRadius=max(6, round(height * 0.01)),
        maxRadius=max(20, round(height * 0.065)),
    )
    candidates = [] if circles is None else [
        (float(x), float(y))
        for x, y, _ in circles[0]
        if height * 0.34 < y < height * 0.66
    ]
    left = min((point for point in candidates if point[0] < width * 0.42), default=(width * 0.194, height * 0.496), key=lambda point: point[0])
    right = max((point for point in candidates if point[0] > width * 0.58), default=(width * 0.762, height * 0.499), key=lambda point: point[0])
    reference_points = np.asarray(anchor_points or [left, right], dtype=np.float64)
    half = max(34, round(height * 0.06))
    pad = max(18, round(height * search_pad_ratio))
    max_rotation = math.radians(max_rotation_degrees)

    templates = []
    template_boxes = []
    for center_x, center_y in reference_points:
        x0 = max(0, min(width - half * 2, round(center_x) - half))
        y0 = max(0, min(height - half * 2, round(center_y) - half))
        templates.append(first_gray[y0 : y0 + half * 2, x0 : x0 + half * 2])
        template_boxes.append((x0, y0))
    reference_points = np.asarray([
        (x0 + template.shape[1] / 2, y0 + template.shape[0] / 2)
        for template, (x0, y0) in zip(templates, template_boxes)
    ], dtype=np.float64)

    corrections: list[tuple[float, float, float]] = []
    scores: list[float] = []
    frame_index = 1
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        current_points = []
        frame_scores = []
        for template, (template_x, template_y) in zip(templates, template_boxes):
            search_x = max(0, template_x - pad)
            search_y = max(0, template_y - pad)
            search_right = min(width, template_x + template.shape[1] + pad)
            search_bottom = min(height, template_y + template.shape[0] + pad)
            search = gray[search_y:search_bottom, search_x:search_right]
            response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(response)
            peak_x, peak_y = subpixel_peak(response, location[0], location[1])
            current_points.append((
                search_x + peak_x + template.shape[1] / 2,
                search_y + peak_y + template.shape[0] / 2,
            ))
            frame_scores.append(float(score))

        current_points_array = np.asarray(current_points, dtype=np.float64)
        if min(frame_scores) >= 0.34:
            reference_vector = reference_points[1] - reference_points[0]
            current_vector = current_points_array[1] - current_points_array[0]
            angle = math.atan2(reference_vector[1], reference_vector[0]) - math.atan2(current_vector[1], current_vector[0])
            angle = float(np.clip(angle, -max_rotation, max_rotation))
            cosine = math.cos(angle)
            sine = math.sin(angle)
            rotation = np.asarray([[cosine, -sine], [sine, cosine]])
            translation = reference_points.mean(axis=0) - rotation @ current_points_array.mean(axis=0)
            dx = float(np.clip(translation[0], -max_translation, max_translation))
            dy = float(np.clip(translation[1], -max_translation, max_translation))
        else:
            best = int(np.argmax(frame_scores))
            dx = float(np.clip(reference_points[best, 0] - current_points_array[best, 0], -max_translation, max_translation))
            dy = float(np.clip(reference_points[best, 1] - current_points_array[best, 1], -max_translation, max_translation))
            angle = 0.0
        corrections.append((dx, dy, angle))
        scores.extend(frame_scores)
        frame_index += 1
        if frame_index % 180 == 0 or frame_index == frame_total:
            print(f"fixed lock: {frame_index}/{frame_total}", flush=True)
    capture.release()

    corrected = np.asarray(corrections, dtype=np.float64)
    if len(corrected):
        for axis in range(3):
            corrected[:, axis] = moving_average(corrected[:, axis], 1)
    statistics = {
        "frames": frame_total,
        "lockPoints": [[round(float(x), 2), round(float(y), 2)] for x, y in reference_points],
        "meanTemplateConfidence": round(float(np.mean(scores)) if scores else 0.0, 4),
        "minimumTemplateConfidence": round(float(np.min(scores)) if scores else 0.0, 4),
        "searchPadPixels": pad,
        "translationLimitPixels": max_translation,
        "rotationLimitDegrees": max_rotation_degrees,
        "correctionTranslationPeakPixels": round(float(np.max(np.abs(corrected[:, :2]))) if len(corrected) else 0.0, 3),
        "correctionRotationPeakDegrees": round(float(np.degrees(np.max(np.abs(corrected[:, 2])))) if len(corrected) else 0.0, 4),
    }
    return corrected, statistics


def estimate_transforms(source: Path) -> tuple[np.ndarray, dict[str, float | int]]:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    ok, first = capture.read()
    if not ok:
        capture.release()
        raise RuntimeError(f"No readable frames in {source}")

    height, width = first.shape[:2]
    work_width = min(640, width)
    work_height = max(1, round(height * work_width / width))
    scale_x = width / work_width
    scale_y = height / work_height

    def prepare(frame: np.ndarray) -> np.ndarray:
        resized = cv2.resize(frame, (work_width, work_height), interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY), (5, 5), 0)

    reference = prepare(first)
    previous = reference
    transforms: list[tuple[float, float, float]] = []
    tracked_counts: list[int] = []
    frame_index = 1

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        current = prepare(frame)
        changed = cv2.absdiff(previous, reference)
        _, dynamic = cv2.threshold(changed, 18, 255, cv2.THRESH_BINARY)
        dynamic = cv2.dilate(dynamic, np.ones((7, 7), np.uint8), iterations=1)
        stable_mask = cv2.bitwise_not(dynamic)
        points = cv2.goodFeaturesToTrack(
            previous,
            maxCorners=260,
            qualityLevel=0.012,
            minDistance=18,
            blockSize=7,
            mask=stable_mask,
        )
        dx = dy = angle = 0.0
        tracked = 0
        if points is not None and len(points) >= 8:
            next_points, status, _ = cv2.calcOpticalFlowPyrLK(
                previous,
                current,
                points,
                None,
                winSize=(21, 21),
                maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
            )
            if next_points is not None and status is not None:
                valid = status.reshape(-1).astype(bool)
                before = points.reshape(-1, 2)[valid]
                after = next_points.reshape(-1, 2)[valid]
                tracked = len(before)
                if tracked >= 8:
                    affine, _ = cv2.estimateAffinePartial2D(
                        before,
                        after,
                        method=cv2.RANSAC,
                        ransacReprojThreshold=1.6,
                        maxIters=1200,
                        confidence=0.995,
                    )
                    if affine is not None:
                        dx = float(np.clip(affine[0, 2] * scale_x, -5.0, 5.0))
                        dy = float(np.clip(affine[1, 2] * scale_y, -5.0, 5.0))
                        angle = float(np.clip(math.atan2(affine[1, 0], affine[0, 0]), -0.009, 0.009))
        transforms.append((dx, dy, angle))
        tracked_counts.append(tracked)
        previous = current
        frame_index += 1
        if frame_index % 180 == 0 or frame_index == frame_total:
            print(f"tracking: {frame_index}/{frame_total}", flush=True)
    capture.release()

    measured = np.asarray(transforms, dtype=np.float64)
    trajectory = np.cumsum(measured, axis=0)
    radius = max(6, round(source_fps * 0.5))
    smoothed = smooth_trajectory(trajectory, radius)
    corrected = measured + (smoothed - trajectory)
    statistics = {
        "frames": frame_total,
        "smoothingRadiusFrames": radius,
        "meanTrackedPoints": round(float(np.mean(tracked_counts)) if tracked_counts else 0.0, 2),
        "rawTranslationPeakPixels": round(float(np.max(np.abs(measured[:, :2]))) if len(measured) else 0.0, 3),
        "correctionTranslationPeakPixels": round(float(np.max(np.abs(corrected[:, :2]))) if len(corrected) else 0.0, 3),
        "correctionRotationPeakDegrees": round(float(np.degrees(np.max(np.abs(corrected[:, 2])))) if len(corrected) else 0.0, 4),
    }
    return corrected, statistics


def stabilize_frame(
    frame: np.ndarray,
    correction: np.ndarray | None,
    zoom: float,
) -> np.ndarray:
    height, width = frame.shape[:2]
    if correction is None:
        warped = frame
    else:
        dx, dy, angle = correction
        cosine = math.cos(angle)
        sine = math.sin(angle)
        matrix = np.array(
            [[cosine, -sine, dx], [sine, cosine, dy]],
            dtype=np.float32,
        )
        warped = cv2.warpAffine(
            frame,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
    crop_width = max(2, round(width / zoom))
    crop_height = max(2, round(height / zoom))
    x = (width - crop_width) // 2
    y = (height - crop_height) // 2
    cropped = warped[y : y + crop_height, x : x + crop_width]
    return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_CUBIC)


def render(
    source: Path,
    destination: Path,
    *,
    zoom: float = 1.04,
    mode: str = "trajectory",
    include_spacetime: bool = True,
    fixed_points: list[tuple[float, float]] | None = None,
    fixed_search_pad_ratio: float = 0.03,
    fixed_max_translation: float = 14.0,
    fixed_max_rotation_degrees: float = 1.0313,
) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() and any(destination.rglob("*.mp4")):
        raise FileExistsError(f"Preview outputs already exist in {destination}")

    corrections, statistics = (
        estimate_fixed_lock(
            source,
            anchor_points=fixed_points,
            search_pad_ratio=fixed_search_pad_ratio,
            max_translation=fixed_max_translation,
            max_rotation_degrees=fixed_max_rotation_degrees,
        )
        if mode == "fixed-lock"
        else estimate_transforms(source)
    )
    capture = cv2.VideoCapture(str(source))
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, first = capture.read()
    if not ok:
        capture.release()
        raise RuntimeError(f"No readable frames in {source}")

    height, width = first.shape[:2]
    output_size = exhibition_canvas_size(first)
    sample_every = max(1, round(fps / 15.0))
    output_fps = fps / sample_every
    source_path = destination / "source" / "crystallization_stabilized.mp4"
    material_dir = destination / "01_material_analysis"
    source_writer = create_h264_writer(source_path, fps, (width, height))
    material_methods = tuple(
        method for method in METHODS if include_spacetime or method != "spacetime"
    )
    material_writers = {
        method: create_h264_writer(material_dir / f"{method}.mp4", output_fps, output_size)
        for method in material_methods
    }

    stabilized_first = stabilize_frame(first, None, zoom)
    processor = ExhibitionMaterialProcessor(
        stabilized_first,
        total_frames=frame_total,
        output_size=output_size,
    )
    frame = first
    frame_index = 0
    try:
        while True:
            correction = None if frame_index == 0 else corrections[frame_index - 1]
            stabilized = stabilize_frame(frame, correction, zoom)
            source_writer.write(stabilized)
            outputs = processor.process(stabilized).as_dict()
            if frame_index % sample_every == 0:
                for method, writer in material_writers.items():
                    writer.write(outputs[method])
            frame_index += 1
            if frame_index % 150 == 0 or frame_index == frame_total:
                print(f"rendering: {frame_index}/{frame_total}", flush=True)
            ok, frame = capture.read()
            if not ok:
                break
    finally:
        capture.release()
        source_writer.release()
        for writer in material_writers.values():
            writer.release()

    statistics.update({
        "source": str(source),
        "mode": mode,
        "zoom": zoom,
        "sourceFps": fps,
        "materialFps": output_fps,
        "materialOutputs": list(material_methods),
        "outputSize": list(output_size),
    })
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "stabilization.json").write_text(
        json.dumps(statistics, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(statistics, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--zoom", type=float, default=1.04)
    parser.add_argument("--mode", choices=("trajectory", "fixed-lock"), default="trajectory")
    parser.add_argument("--skip-spacetime", action="store_true")
    parser.add_argument("--fixed-point", action="append", default=[])
    parser.add_argument("--fixed-search-pad-ratio", type=float, default=0.03)
    parser.add_argument("--fixed-max-translation", type=float, default=14.0)
    parser.add_argument("--fixed-max-rotation-degrees", type=float, default=1.0313)
    args = parser.parse_args()
    fixed_points = []
    for value in args.fixed_point:
        x, y = value.split(",", 1)
        fixed_points.append((float(x), float(y)))
    if fixed_points and len(fixed_points) != 2:
        parser.error("--fixed-point must be supplied exactly twice")
    render(
        args.source,
        args.destination,
        zoom=args.zoom,
        mode=args.mode,
        include_spacetime=not args.skip_spacetime,
        fixed_points=fixed_points or None,
        fixed_search_pad_ratio=args.fixed_search_pad_ratio,
        fixed_max_translation=args.fixed_max_translation,
        fixed_max_rotation_degrees=args.fixed_max_rotation_degrees,
    )


if __name__ == "__main__":
    main()
