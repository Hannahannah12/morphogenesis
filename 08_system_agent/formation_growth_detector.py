"""Fast, illumination-resistant crystal growth onset detector.

The detector watches a central surface ROI and looks for sustained expansion of
fine local texture relative to a rolling baseline. It deliberately ignores
plain brightness change and never falls back to an arbitrary strongest frame.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


ProgressCallback = Callable[[float, str], None]


def _surface_features(frame: np.ndarray) -> tuple[float, float, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
    # Ignore screws, plate edges, side reflections and timestamp-like borders.
    roi = gray[14:166, 24:296]
    illumination = cv2.GaussianBlur(roi, (0, 0), 7)
    highpass = cv2.absdiff(roi, illumination)
    sobel_x = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(sobel_x, sobel_y)
    coverage = float((highpass > 7).mean())
    edge_density = float((gradient > 28).mean())
    low_frequency_change = float(np.abs(roi.astype(np.float32) - illumination).mean())
    return coverage, edge_density, low_frequency_change


def _normalized_surface_roi(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
    roi = gray[14:166, 24:296]
    return cv2.normalize(
        roi.astype(np.float32),
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)


def detect_growth_onset(
    path: Path,
    progress: ProgressCallback | None = None,
) -> dict[str, float | str]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_rate = 5.0
    sample_every = max(1, round(fps / sample_rate))
    records: list[dict[str, float]] = []
    frame_index = 0
    confirmed: dict[str, float] | None = None

    reference_samples = round(20 * sample_rate)
    minimum_reference_samples = round(5 * sample_rate)
    # Tools may enter repeatedly during setup. Crystal texture remains and
    # expands, so observe eight seconds, require broad persistence across the
    # window and demand that the final two seconds never fall back to baseline.
    excluded_recent = round(8.0 * sample_rate)
    confirmation_samples = round(8.0 * sample_rate)
    ending_samples = round(2.0 * sample_rate)

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % sample_every == 0:
            timestamp = frame_index / fps
            coverage, edge_density, low_frequency = _surface_features(frame)
            records.append({
                "time": timestamp,
                "coverage": coverage,
                "edge": edge_density,
                "lowFrequency": low_frequency,
            })
            if len(records) >= minimum_reference_samples + excluded_recent:
                reference_end = len(records) - excluded_recent
                reference_start = max(0, reference_end - reference_samples)
                reference = records[reference_start:reference_end]
                recent = records[-confirmation_samples:]
                coverages = np.array([item["coverage"] for item in reference])
                baseline = float(np.median(coverages))
                mad = float(np.median(np.abs(coverages - baseline)))
                deviation = max(0.035, 8.0 * mad)
                upper_threshold = max(
                    baseline + deviation,
                    baseline * 1.28,
                )
                lower_threshold = min(
                    baseline - deviation,
                    baseline * 0.82,
                )
                recent_start = float(np.median([
                    item["coverage"] for item in recent[:3]
                ]))
                recent_end = float(np.median([
                    item["coverage"] for item in recent[-3:]
                ]))
                growth = recent_end - recent_start
                ending_values = np.array([
                    item["coverage"] for item in recent[-ending_samples:]
                ])
                recent_values = np.array([
                    item["coverage"] for item in recent
                ])
                direction = (
                    "texture-expansion"
                    if growth >= 0
                    else "texture-smoothing"
                )
                if direction == "texture-expansion":
                    ending_confirmed = bool(np.all(
                        ending_values > upper_threshold
                    ))
                    persistent_fraction = float(np.mean(
                        recent_values > upper_threshold
                    ))
                    final_margin = recent_end - upper_threshold
                else:
                    ending_confirmed = bool(np.all(
                        ending_values < lower_threshold
                    ))
                    persistent_fraction = float(np.mean(
                        recent_values < lower_threshold
                    ))
                    final_margin = lower_threshold - recent_end

                # Crystallisation produces a growing field of fine texture.
                # A lighting step may persist, but it usually neither expands
                # enough nor reaches the absolute rolling-baseline margin.
                if (
                    ending_confirmed
                    and persistent_fraction >= 0.65
                    and abs(growth) > max(0.04, 5.0 * mad)
                ):
                    return_margin = max(0.008, 2.0 * mad)
                    backtrack_samples = round(12.0 * sample_rate)
                    backtrack = records[-backtrack_samples:]
                    onset_record = recent[0]
                    for item in backtrack:
                        changed = (
                            item["coverage"] > baseline + return_margin
                            if direction == "texture-expansion"
                            else item["coverage"] < baseline - return_margin
                        )
                        if changed:
                            onset_record = item
                            break
                    confidence = min(
                        0.99,
                        max(
                            0.55,
                            0.62
                            + abs(growth) * 2.1
                            + max(0.0, final_margin) * 1.4,
                        ),
                    )
                    confirmed = {
                        "onsetSeconds": round(onset_record["time"], 3),
                        "trimStartSeconds": round(
                            max(0.0, onset_record["time"] - 2.0),
                            3,
                        ),
                        "confidence": round(confidence, 3),
                        "baselineCoverage": round(baseline, 5),
                        "confirmedCoverage": round(recent_end, 5),
                        "coverageGrowth": round(growth, 5),
                        "changeDirection": direction,
                        "method": "rolling ROI texture-growth confirmation",
                    }
                    break
        frame_index += 1
        if progress and frame_index % max(1, round(frame_total / 20)) == 0:
            progress(
                min(0.94, frame_index / max(1, frame_total)),
                "Watching the surface ROI for sustained texture growth",
            )
    capture.release()
    if confirmed is None:
        raise RuntimeError(
            "No sustained crystal texture growth was detected; capture remains untrimmed"
        )
    return confirmed


def detect_formation_completion(
    path: Path,
    onset_seconds: float,
    change_direction: str,
    baseline_coverage: float,
    confirmed_coverage: float,
    hold_seconds: float = 2.0,
    progress: ProgressCallback | None = None,
) -> dict[str, float | str]:
    """Find the first stable, fully formed state and stop before dissolution.

    The onset detector establishes whether crystallisation expands or smooths
    the local texture metric. From that point onward, this pass follows the
    metric in the same signed direction. Completion is the first strong local
    maximum followed by retreat, or the beginning of a sustained plateau.
    Later movement is deliberately ignored because melting can create a second,
    visually strong peak.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_total / fps
    sample_rate = 5.0
    sample_every = max(1, round(fps / sample_rate))
    start_frame = max(0, round(onset_seconds * fps))
    # Both current samples complete quickly. Limiting this pass also prevents a
    # much later melt from becoming the apparent crystallisation maximum.
    analysis_end = min(duration, onset_seconds + 45.0)
    end_frame = min(frame_total, round(analysis_end * fps))
    reference_frame = max(0, round((onset_seconds - 2.0) * fps))
    capture.set(cv2.CAP_PROP_POS_FRAMES, reference_frame)
    reference_frames: list[np.ndarray] = []
    reference_step = max(1, round(fps / 2.0))
    for reference_index in range(reference_frame, start_frame):
        ok, frame = capture.read()
        if not ok:
            break
        if (reference_index - reference_frame) % reference_step == 0:
            reference_frames.append(_normalized_surface_roi(frame))
    if not reference_frames:
        raise RuntimeError("Could not build a pre-formation surface reference")
    reference_roi = np.median(
        np.stack(reference_frames).astype(np.float32),
        axis=0,
    ).astype(np.uint8)
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    records: list[dict[str, float]] = []
    frame_index = start_frame
    while frame_index < end_frame:
        ok, frame = capture.read()
        if not ok:
            break
        if (frame_index - start_frame) % sample_every == 0:
            timestamp = frame_index / fps
            coverage, _, _ = _surface_features(frame)
            if change_direction == "texture-expansion":
                # Expansion samples are best measured by how much of the plate
                # has changed relative to the pre-formation surface. Fine
                # texture peaks too early while the crystal front is still
                # spreading across the plate.
                normalized_roi = _normalized_surface_roi(frame)
                signed_progress = float(
                    (cv2.absdiff(normalized_roi, reference_roi) > 20).mean()
                )
            else:
                signed_progress = baseline_coverage - coverage
            records.append({
                "time": timestamp,
                "coverage": coverage,
                "progress": signed_progress,
            })
        frame_index += 1
        if progress and frame_index % max(1, round((end_frame - start_frame) / 10)) == 0:
            progress(
                min(0.95, (frame_index - start_frame) / max(1, end_frame - start_frame)),
                "Watching for a stable fully formed structure",
            )
    capture.release()

    if len(records) < round(5 * sample_rate):
        raise RuntimeError("Not enough post-onset frames to detect formation completion")

    raw = np.array([item["progress"] for item in records], dtype=np.float32)
    smooth_samples = max(3, round(1.0 * sample_rate))
    smoothed = np.array([
        float(np.median(raw[max(0, index - smooth_samples // 2) : index + smooth_samples // 2 + 1]))
        for index in range(len(raw))
    ])
    confirmed_progress = abs(confirmed_coverage - baseline_coverage)
    # Do not accept a small pause halfway through propagation. The stable state
    # must reach at least most of the structural excursion that originally
    # confirmed crystallisation.
    minimum_progress = (
        0.25
        if change_direction == "texture-expansion"
        else max(0.04, confirmed_progress * 0.8)
    )
    earliest_index = round(3.0 * sample_rate)
    plateau_samples = round(2.0 * sample_rate)
    retreat_samples = round(1.0 * sample_rate)
    peak_index = int(np.argmax(smoothed[: max(earliest_index + 1, plateau_samples)]))
    peak_value = float(smoothed[peak_index])
    completion_index: int | None = None
    method = ""

    for index in range(earliest_index, len(smoothed)):
        value = float(smoothed[index])
        if value > peak_value:
            peak_value = value
            peak_index = index
        if peak_value < minimum_progress:
            continue

        retreat = (
            max(0.015, peak_value * 0.03)
            if change_direction == "texture-expansion"
            else max(0.008, peak_value * 0.09)
        )
        if index >= peak_index + retreat_samples:
            recent = smoothed[index - retreat_samples + 1 : index + 1]
            if bool(np.all(recent < peak_value - retreat)):
                completion_index = (
                    peak_index
                    if change_direction == "texture-expansion"
                    else index
                )
                method = (
                    "maximum spatial coverage before sustained retreat"
                    if change_direction == "texture-expansion"
                    else "first structural maximum with sustained retreat confirmed"
                )
                break

        if change_direction != "texture-expansion" and index >= plateau_samples:
            recent = smoothed[index - plateau_samples + 1 : index + 1]
            plateau_range = float(np.max(recent) - np.min(recent))
            plateau_floor = float(np.min(recent))
            if (
                plateau_range <= 0.008
                and plateau_floor >= max(minimum_progress, peak_value * 0.82)
            ):
                completion_index = index - plateau_samples + 1
                method = "first sustained structural plateau"
                break

    if completion_index is None:
        # No melting is inferred here. The caller may keep the original ending
        # rather than fabricate a completion boundary.
        raise RuntimeError("No stable completion boundary was detected")

    completion_seconds = float(records[completion_index]["time"])
    trim_end_seconds = min(duration, completion_seconds + hold_seconds)
    return {
        "completionSeconds": round(completion_seconds, 3),
        "trimEndSeconds": round(trim_end_seconds, 3),
        "holdSeconds": round(hold_seconds, 3),
        "completionProgress": round(float(smoothed[completion_index]), 5),
        "completionMethod": method,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument(
        "--completion",
        action="store_true",
        help="Also detect the first fully formed plateau and two-second hold ending",
    )
    args = parser.parse_args()
    for video in args.videos:
        try:
            result = detect_growth_onset(video)
            if args.completion:
                result.update(detect_formation_completion(
                    video,
                    float(result["onsetSeconds"]),
                    str(result["changeDirection"]),
                    float(result["baselineCoverage"]),
                    float(result["confirmedCoverage"]),
                ))
            print(json.dumps({"video": str(video), **result}))
        except RuntimeError as error:
            print(json.dumps({"video": str(video), "error": str(error)}))


if __name__ == "__main__":
    main()
