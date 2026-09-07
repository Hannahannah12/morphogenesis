"""Notebook-faithful DINO attention and patch extraction for exhibition.

The implementation is derived from:
  - structural_resonance_attention.ipynb cells 3–5 and 7–11

The Notebook remains the method authority. This module automates its manual
cell sequence and writes only assets consumed by the exhibition website.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Callable

import cv2
import numpy as np
from PIL import Image
import timm
import torch
import torchvision.transforms as transforms


ProgressCallback = Callable[[str, float, str], None]
BLUES_LUT_PATH = Path(__file__).with_name("dino_blues_lut.npy")
SQUARE_OUTPUT_SIZE = (720, 720)
LANDSCAPE_OUTPUT_SIZE = (1280, 720)
CANDIDATE_PATCH_TARGET = 50
MINIMUM_PATCH_COUNT = 40
PATCH_SAMPLE_EVERY = 2
MIN_PATCH_MEAN_LUMINANCE = 85.0
MULTISCALE_PATCH_SIZES = {
    "small": 160,
    "medium": 320,
    "large": 560,
}
ATTENTION_PEAKS_PER_FRAME = 2


def notify(
    callback: ProgressCallback | None,
    channel: str,
    progress: float,
    message: str,
) -> None:
    if callback is not None:
        callback(channel, max(0.0, min(1.0, float(progress))), message)


def exhibition_canvas_size(width: int, height: int) -> tuple[int, int]:
    aspect = width / max(1, height)
    if 0.9 <= aspect <= 1.1:
        return SQUARE_OUTPUT_SIZE
    return LANDSCAPE_OUTPUT_SIZE


def fit_frame(frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Fit the complete frame without stretching or centre cropping."""
    target_width, target_height = size
    height, width = frame.shape[:2]
    scale = min(target_width / width, target_height / height)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    interpolation = cv2.INTER_AREA if scale <= 1 else cv2.INTER_CUBIC
    resized = cv2.resize(
        frame,
        (resized_width, resized_height),
        interpolation=interpolation,
    )
    canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
    x = (target_width - resized_width) // 2
    y = (target_height - resized_height) // 2
    canvas[y : y + resized_height, x : x + resized_width] = resized
    return canvas


def find_formation_timeline(source: Path) -> tuple[dict[str, int | str], list[float]]:
    """Find the first completed growth event using Notebook thresholds.

    Notebook cells 3–5 use a 10-frame brightness rise of 0.5 for onset and a
    20-frame brightness standard deviation below 0.3 for stability. The
    research clip used by the Notebook ends after crystallisation, so its
    global brightness peak belongs to the growth event. Exhibition recordings
    may continue through a later melt or camera change. The live worker must
    therefore use the first stable window after onset, not a later global peak.
    """
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open structural source: {source}")
    brightness: list[float] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness.append(float(np.mean(gray)))
    capture.release()
    if not brightness:
        raise RuntimeError("Structural source contains no frames")

    values = np.asarray(brightness, dtype=np.float32)
    global_peak = int(np.argmax(values))
    onset: int | None = None
    for index in range(10, len(values)):
        if float(values[index] - values[index - 10]) > 0.5:
            onset = index
            break

    window = 20
    stable_window_start: int | None = None
    if onset is not None:
        onset_brightness = float(values[onset])
        for index in range(onset, max(onset, len(values) - window)):
            observed_rise = float(
                np.max(values[onset : index + window]) - onset_brightness
            )
            if observed_rise <= 0.5:
                continue
            if float(np.std(values[index : index + window])) < 0.3:
                stable_window_start = index
                break

    if stable_window_start is not None and onset is not None:
        # Stability is only known after all 20 frames have been observed.
        complete = min(len(values) - 1, stable_window_start + window)
        local_values = values[onset : complete + 1]
        formation_peak = onset + int(np.argmax(local_values))
        method = "notebook-first-growth-stability"
    else:
        # Keep the Notebook global-peak path only as a fallback when no
        # reliable first-growth onset/stability pair exists.
        formation_peak = global_peak
        stable_window_start = None
        for index in range(
            formation_peak,
            max(formation_peak, len(values) - window),
        ):
            if float(np.std(values[index : index + window])) < 0.3:
                stable_window_start = index
                break
        if stable_window_start is None:
            stable_window_start = min(
                len(values) - 1,
                max(formation_peak, round(len(values) * 0.72)),
            )
            complete = stable_window_start
            method = "notebook-global-peak-last-resort"
        else:
            complete = min(len(values) - 1, stable_window_start + window)
            method = "notebook-global-peak-fallback"

    timeline: dict[str, int | str] = {
        "onsetFrame": -1 if onset is None else onset,
        "formationPeakFrame": formation_peak,
        "globalBrightnessPeakFrame": global_peak,
        "stableWindowStartFrame": stable_window_start,
        "completeFrame": complete,
        "selectionMethod": method,
    }
    return timeline, brightness


def create_h264_writer(
    path: Path,
    fps: float,
    size: tuple[int, int],
) -> cv2.VideoWriter:
    """Wait briefly for the previous exhibition page to release one output."""
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
            raise RuntimeError(f"Could not create structural video: {path}")
        time.sleep(0.25)


def run_structural_pipeline(
    source: Path,
    output_dir: Path,
    *,
    panel_size: int | None = None,
    patch_start_seconds: float | None = None,
    callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """Run DINO attention, blob selection and Notebook patch extraction."""
    source = source.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    patch_dir = output_dir / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    for previous_patch in patch_dir.glob("*.jpg"):
        previous_patch.unlink()
    if not BLUES_LUT_PATH.exists():
        raise RuntimeError(f"Notebook Blues LUT is missing: {BLUES_LUT_PATH}")
    blues_lut = np.load(BLUES_LUT_PATH)

    timeline, brightness = find_formation_timeline(source)
    detected_stable_frame = int(timeline["completeFrame"])
    notify(
        callback,
        "structural",
        0.04,
        (
            f"Notebook first growth complete at frame {detected_stable_frame} / "
            f"onset {timeline['onsetFrame']} / "
            f"local peak {timeline['formationPeakFrame']}"
        ),
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = timm.create_model(
        "vit_base_patch16_224.dino",
        pretrained=True,
    ).to(device)
    model.eval()
    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )
    notify(
        callback,
        "structural",
        0.08,
        f"DINO vit_base_patch16_224.dino loaded on {device}",
    )

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open structural source: {source}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 15)
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    source_size = exhibition_canvas_size(source_width, source_height)
    if panel_size is None:
        panel_size = 720
    # Attention is rendered for the complete formation clip. Patch extraction
    # is independently constrained to a late formation window, so early
    # attention remains visible without allowing early frames into the saved
    # patch collection.
    if patch_start_seconds is None:
        patch_start_frame = min(
            detected_stable_frame,
            max(0, frame_total - 1),
        )
        patch_selection_method = "notebook-detected-stability"
    else:
        patch_start_frame = min(
            max(0, round(float(patch_start_seconds) * fps)),
            max(0, frame_total - 1),
        )
        patch_selection_method = "near-completion-window-override"
    patch_end_frame = min(frame_total, patch_start_frame + 100)
    patch_window_frames = max(1, patch_end_frame - patch_start_frame)
    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    video_paths = {
        "combined": output_dir / "attention_blob.mp4",
        "attentionMap": output_dir / "attention_map.mp4",
        "blobTrack": output_dir / "blob_track.mp4",
    }
    writers: dict[str, cv2.VideoWriter] = {}
    try:
        writers["combined"] = create_h264_writer(
            video_paths["combined"],
            fps,
            (panel_size * 2, panel_size),
        )
        writers["attentionMap"] = create_h264_writer(
            video_paths["attentionMap"],
            fps,
            (panel_size, panel_size),
        )
        writers["blobTrack"] = create_h264_writer(
            video_paths["blobTrack"],
            fps,
            (panel_size, panel_size),
        )
    except Exception:
        for writer in writers.values():
            writer.release()
        capture.release()
        raise

    # Keep the literal Notebook cell 11 thresholds. The previous Exhibition
    # worker scaled these down at 720px, which admitted too many tiny blobs.
    area_threshold = 500
    patch_paths: list[Path] = []
    patch_metadata: list[dict[str, object]] = []
    rejected_dark_patch_count = 0
    frame_index = 0
    processed_frames = 0

    try:
        while frame_index < frame_total:
            ok, raw = capture.read()
            if not ok:
                break
            frame = fit_frame(raw, source_size)
            frame_height, frame_width = frame.shape[:2]
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            image = Image.fromarray(frame_rgb)
            tensor = transform(image).unsqueeze(0).to(device)
            with torch.no_grad():
                features = model.forward_features(tensor)
            patch_features = features[0, 1:, :]
            weights = patch_features.norm(dim=-1).reshape(14, 14)
            weights = weights.detach().float().cpu().numpy()
            minimum = float(weights.min())
            span = float(weights.max() - minimum)
            attention = (weights - minimum) / max(span, 1e-8)
            attention = cv2.resize(
                attention,
                (frame_width, frame_height),
                interpolation=cv2.INTER_LINEAR,
            )

            # Notebook cell 10: plt.cm.Blues(attn_norm).
            attention_uint8 = np.clip(attention * 255, 0, 255).astype(np.uint8)
            attention_rgb = blues_lut[attention_uint8]
            attention_color = cv2.cvtColor(
                attention_rgb,
                cv2.COLOR_RGB2BGR,
            )

            _, blob_mask = cv2.threshold(
                attention_uint8,
                120,
                255,
                cv2.THRESH_BINARY,
            )
            contours, _ = cv2.findContours(
                blob_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            boxes: list[tuple[int, int, int, int]] = []
            marked = frame.copy()
            for contour in contours:
                if cv2.contourArea(contour) <= area_threshold:
                    continue
                x, y, width, height = cv2.boundingRect(contour)
                boxes.append((x, y, width, height))
                cv2.rectangle(
                    marked,
                    (x, y),
                    (x + width, y + height),
                    (255, 200, 100),
                    2,
                )

            # Store patch candidates only from the near-completion window,
            # while the attention videos above continue across the full clip.
            relative = frame_index - patch_start_frame
            if (
                patch_start_frame <= frame_index < patch_end_frame
                and relative % PATCH_SAMPLE_EVERY == 0
            ):
                peak_attention = attention.copy()
                suppression_radius = max(
                    80,
                    min(frame_width, frame_height) // 8,
                )
                for peak_index in range(ATTENTION_PEAKS_PER_FRAME):
                    peak_y_value, peak_x_value = np.unravel_index(
                        int(np.argmax(peak_attention)),
                        peak_attention.shape,
                    )
                    peak_y = int(peak_y_value)
                    peak_x = int(peak_x_value)
                    for size_class, requested_size in (
                        MULTISCALE_PATCH_SIZES.items()
                    ):
                        crop_size = min(
                            requested_size,
                            frame_width,
                            frame_height,
                        )
                        x = max(
                            0,
                            min(
                                frame_width - crop_size,
                                peak_x - crop_size // 2,
                            ),
                        )
                        y = max(
                            0,
                            min(
                                frame_height - crop_size,
                                peak_y - crop_size // 2,
                            ),
                        )
                        patch = frame[
                            y : y + crop_size,
                            x : x + crop_size,
                        ]
                        patch_gray = cv2.cvtColor(
                            patch,
                            cv2.COLOR_BGR2GRAY,
                        )
                        patch_mean_luminance = float(np.mean(patch_gray))
                        if (
                            patch_mean_luminance
                            < MIN_PATCH_MEAN_LUMINANCE
                        ):
                            rejected_dark_patch_count += 1
                            continue
                        patch_number = len(patch_paths) + 1
                        patch_id = f"_candidate_{patch_number:04d}"
                        patch_path = patch_dir / f"{patch_id}.jpg"
                        cv2.imwrite(str(patch_path), patch)
                        patch_paths.append(patch_path)
                        patch_metadata.append(
                            {
                                "id": patch_id,
                                "file": patch_path.relative_to(
                                    output_dir
                                ).as_posix(),
                                "sourceFrame": frame_index,
                                "contourIndex": None,
                                "attentionPeakIndex": peak_index,
                                "boundingBox": [
                                    x,
                                    y,
                                    crop_size,
                                    crop_size,
                                ],
                                "meanLuminance": round(
                                    patch_mean_luminance,
                                    3,
                                ),
                                "candidateType": (
                                    "attention-peak-multiscale"
                                ),
                                "sizeClass": size_class,
                                "requestedCropSize": requested_size,
                            }
                        )
                    y0 = max(0, peak_y - suppression_radius)
                    y1 = min(
                        frame_height,
                        peak_y + suppression_radius + 1,
                    )
                    x0 = max(0, peak_x - suppression_radius)
                    x1 = min(
                        frame_width,
                        peak_x + suppression_radius + 1,
                    )
                    peak_attention[y0:y1, x0:x1] = -1

            attention_panel = fit_frame(
                attention_color,
                (panel_size, panel_size),
            )
            marked_panel = fit_frame(
                marked,
                (panel_size, panel_size),
            )
            writers["combined"].write(
                np.hstack([attention_panel, marked_panel])
            )
            writers["attentionMap"].write(attention_panel)
            writers["blobTrack"].write(marked_panel)
            frame_index += 1
            processed_frames += 1
            if (
                processed_frames % 10 == 0
                or frame_index == patch_end_frame
            ):
                notify(
                    callback,
                    "structural",
                    (
                        0.08
                        + 0.82
                        * processed_frames
                        / max(1, frame_total)
                    ),
                    (
                        f"DINO full frame {frame_index}/{frame_total} / "
                        f"{len(patch_paths)} late patch candidates"
                    ),
                )
    finally:
        capture.release()
        for writer in writers.values():
            writer.release()

    detected_patch_candidate_count = len(patch_paths)
    if detected_patch_candidate_count < MINIMUM_PATCH_COUNT:
        raise RuntimeError(
            "Near-completion patch extraction produced "
            f"{detected_patch_candidate_count} candidates; "
            f"at least {MINIMUM_PATCH_COUNT} are required"
        )

    if detected_patch_candidate_count > CANDIDATE_PATCH_TARGET:
        target_by_size = {
            "small": 17,
            "medium": 17,
            "large": 16,
        }
        selected_candidate_indices = []
        for size_class, target in target_by_size.items():
            class_indices = [
                index
                for index, metadata in enumerate(patch_metadata)
                if metadata.get("sizeClass") == size_class
            ]
            take = min(target, len(class_indices))
            if take:
                positions = np.linspace(
                    0,
                    len(class_indices) - 1,
                    take,
                ).round().astype(int)
                selected_candidate_indices.extend(
                    class_indices[position]
                    for position in positions
                )
        selected_set = set(selected_candidate_indices)
        remaining = CANDIDATE_PATCH_TARGET - len(selected_set)
        if remaining > 0:
            available = [
                index
                for index in range(detected_patch_candidate_count)
                if index not in selected_set
            ]
            positions = np.linspace(
                0,
                len(available) - 1,
                remaining,
            ).round().astype(int)
            selected_set.update(
                available[position]
                for position in positions
            )
        size_order = {"small": 0, "medium": 1, "large": 2}
        selected_candidate_indices = sorted(
            selected_set,
            key=lambda index: (
                int(patch_metadata[index]["sourceFrame"]),
                size_order.get(
                    str(patch_metadata[index].get("sizeClass")),
                    3,
                ),
                int(
                    patch_metadata[index].get(
                        "attentionPeakIndex",
                        0,
                    )
                ),
            ),
        )
    else:
        selected_candidate_indices = list(
            range(detected_patch_candidate_count)
        )

    selected_paths: list[Path] = []
    selected_metadata: list[dict[str, object]] = []
    selected_set = set(selected_candidate_indices)
    for new_index, candidate_index in enumerate(selected_candidate_indices):
        patch_id = f"patch_{new_index + 1:02d}"
        destination = patch_dir / f"{patch_id}.jpg"
        patch_paths[candidate_index].replace(destination)
        metadata = dict(patch_metadata[candidate_index])
        metadata.update(
            {
                "id": patch_id,
                "file": destination.relative_to(output_dir).as_posix(),
                "candidateIndex": candidate_index,
            }
        )
        selected_paths.append(destination)
        selected_metadata.append(metadata)
    for candidate_index, candidate_path in enumerate(patch_paths):
        if candidate_index not in selected_set:
            candidate_path.unlink(missing_ok=True)
    patch_paths = selected_paths
    patch_metadata = selected_metadata

    manifest_path = output_dir / "manifest.json"
    manifest = {
        "pipeline": "notebook-faithful-dino-structural",
        "source": str(source),
        "model": "vit_base_patch16_224.dino",
        "sourceResolution": f"{source_size[0]}x{source_size[1]}",
        "videoResolution": f"{panel_size * 2}x{panel_size}",
        **timeline,
        "stableFrame": patch_start_frame,
        "detectedStableFrame": detected_stable_frame,
        "patchStartFrame": patch_start_frame,
        "patchStartSeconds": round(patch_start_frame / fps, 3),
        "patchSelectionMethod": patch_selection_method,
        "patchEndFrame": patch_end_frame,
        "brightnessSamples": len(brightness),
        "attentionThreshold": 120,
        "contourAreaAt1080": 500,
        "patchWindowFrames": patch_window_frames,
        "candidatePatchTarget": CANDIDATE_PATCH_TARGET,
        "minimumCandidatePatchCount": MINIMUM_PATCH_COUNT,
        "detectedPatchCandidateCount": detected_patch_candidate_count,
        "patchSampleEvery": PATCH_SAMPLE_EVERY,
        "patchCropPolicy": "dino-attention-peaks-multiscale",
        "patchCropSizes": MULTISCALE_PATCH_SIZES,
        "attentionPeaksPerSampledFrame": ATTENTION_PEAKS_PER_FRAME,
        "candidatePatchSizeTargets": {
            "small": 17,
            "medium": 17,
            "large": 16,
        },
        "minimumPatchMeanLuminance": MIN_PATCH_MEAN_LUMINANCE,
        "rejectedDarkPatchCount": rejected_dark_patch_count,
        "video": video_paths["combined"].name,
        "videos": {
            name: path.name
            for name, path in video_paths.items()
        },
        "patches": [
            patch_path.relative_to(output_dir).as_posix()
            for patch_path in patch_paths
        ],
        "patchMetadata": patch_metadata,
        "resonanceSets": [],
        "searchState": "pending",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    notify(
        callback,
        "structural",
        0.92,
        f"DINO attention and {len(patch_paths)} patches are ready",
    )
    return {
        "video": video_paths["combined"],
        "videos": video_paths,
        "manifest": manifest_path,
        "patches": patch_paths,
        "stableFrame": patch_start_frame,
        "sourceResolution": f"{source_size[0]}x{source_size[1]}",
        "videoResolution": f"{panel_size * 2}x{panel_size}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--panel-size", type=int, default=720)
    parser.add_argument("--patch-start-seconds", type=float)
    args = parser.parse_args()
    result = run_structural_pipeline(
        args.source,
        args.output,
        panel_size=args.panel_size,
        patch_start_seconds=args.patch_start_seconds,
    )
    print(
        json.dumps(
            {
                "manifest": str(result["manifest"]),
                "candidatePatches": len(result["patches"]),
                "video": str(result["video"]),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
