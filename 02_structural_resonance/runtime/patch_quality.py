"""Score DINO patches by structural readability before image search."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class PatchQuality:
    index: int
    file: str
    source_frame: int
    width: int
    height: int
    mean_luminance: float
    dark_pixel_ratio: float
    contrast: float
    sharpness: float
    edge_density: float
    gradient: float
    texture_coverage: float
    illumination_uniformity: float
    size_score: float
    aspect_score: float
    score: float
    eligible: bool
    rejection_reasons: list[str]
    duplicate_of: int | None = None
    visual_similarity: float | None = None

    def serialize(self) -> dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, float):
                payload[key] = round(value, 4)
        return payload


def score_patch(
    path: Path,
    index: int,
    source_frame: int,
) -> PatchQuality:
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"Could not read patch: {path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    mean_luminance = float(np.mean(gray))
    dark_pixel_ratio = float(np.mean(gray < 40))
    lower, upper = np.percentile(gray, (2, 98))
    contrast = float((upper - lower) / 255)
    sharpness = float(
        min(
            1,
            np.log1p(cv2.Laplacian(gray, cv2.CV_32F).var()) / 10,
        )
    )
    local = cv2.createCLAHE(
        clipLimit=2.2,
        tileGridSize=(6, 6),
    ).apply(gray)
    edges = cv2.Canny(local, 25, 90, L2gradient=True)
    edge_density = float(np.mean(edges > 0))
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gradient = float(
        np.mean(cv2.magnitude(gradient_x, gradient_y)) / 255
    )
    smoothed = cv2.GaussianBlur(gray, (3, 3), 0)
    smooth_x = cv2.Sobel(smoothed, cv2.CV_32F, 1, 0, ksize=3)
    smooth_y = cv2.Sobel(smoothed, cv2.CV_32F, 0, 1, ksize=3)
    smooth_magnitude = cv2.magnitude(smooth_x, smooth_y)
    tile_means: list[float] = []
    tile_gradients: list[float] = []
    for tile_y in range(6):
        y0 = tile_y * height // 6
        y1 = (tile_y + 1) * height // 6
        for tile_x in range(6):
            x0 = tile_x * width // 6
            x1 = (tile_x + 1) * width // 6
            tile_means.append(float(np.mean(smoothed[y0:y1, x0:x1])))
            tile_gradients.append(
                float(np.mean(smooth_magnitude[y0:y1, x0:x1]))
            )
    texture_coverage = float(
        np.mean(np.asarray(tile_gradients) > 8.0)
    )
    illumination_uniformity = float(
        1 - min(1, np.std(tile_means) / 48)
    )
    size_score = float(
        min(1, min(width, height) / 120)
        * min(1, (width * height) / (220 * 180))
    )
    aspect_score = float(min(width, height) / max(width, height))
    edge_quality = max(0.0, 1 - abs(edge_density - 0.16) / 0.16)
    # Global contrast alone often rewards a shadow or dark border. Structural
    # search needs fine texture distributed across the crop, so coverage,
    # local gradients and even illumination carry most of the score.
    score = float(
        0.08 * contrast
        + 0.18 * sharpness
        + 0.22 * min(1, gradient * 8)
        + 0.17 * edge_quality
        + 0.12 * texture_coverage
        + 0.10 * illumination_uniformity
        + 0.06 * size_score
        + 0.07 * aspect_score
    )

    reasons: list[str] = []
    if min(width, height) < 120:
        reasons.append("too-small")
    if width * height < 12_000:
        reasons.append("insufficient-area")
    if mean_luminance < 42:
        reasons.append("black-background")
    if dark_pixel_ratio > 0.68:
        reasons.append("mostly-black")
    if contrast < 0.16:
        reasons.append("flat-grey")
    if gradient < 0.035:
        reasons.append("weak-gradient")
    if edge_density < 0.04:
        reasons.append("no-readable-contour")
    if edge_density > 0.34:
        reasons.append("edge-noise")
    if texture_coverage < 0.72:
        reasons.append("sparse-texture")

    return PatchQuality(
        index=index,
        file=path.name,
        source_frame=int(source_frame),
        width=width,
        height=height,
        mean_luminance=mean_luminance,
        dark_pixel_ratio=dark_pixel_ratio,
        contrast=contrast,
        sharpness=sharpness,
        edge_density=edge_density,
        gradient=gradient,
        texture_coverage=texture_coverage,
        illumination_uniformity=illumination_uniformity,
        size_score=size_score,
        aspect_score=aspect_score,
        score=score,
        eligible=not reasons,
        rejection_reasons=reasons,
    )


def _normalise_descriptor(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float32).reshape(-1)
    values -= float(np.mean(values))
    return values / (float(np.linalg.norm(values)) + 1e-6)


def structural_descriptor(
    path: Path,
) -> tuple[np.ndarray, np.ndarray]:
    """Make a tiny cached descriptor for fast near-duplicate suppression."""
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"Could not read patch: {path}")
    resized = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
    enhanced = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8),
    ).apply(resized)
    gradient_x = cv2.Sobel(enhanced, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(enhanced, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gradient_x, gradient_y)
    layout = cv2.resize(
        enhanced,
        (24, 24),
        interpolation=cv2.INTER_AREA,
    )
    texture = cv2.resize(
        magnitude,
        (24, 24),
        interpolation=cv2.INTER_AREA,
    )
    return (
        _normalise_descriptor(layout),
        _normalise_descriptor(texture),
    )


def structural_similarity(
    first: tuple[np.ndarray, np.ndarray],
    second: tuple[np.ndarray, np.ndarray],
) -> float:
    layout = float(np.dot(first[0], second[0]))
    texture = float(np.dot(first[1], second[1]))
    return 0.35 * layout + 0.65 * texture


def select_structural_patch_indices(
    patch_paths: list[Path],
    maximum: int,
    metadata: list[dict[str, Any]] | None = None,
) -> tuple[list[int], list[PatchQuality]]:
    """Choose clear, evenly textured patches and suppress visual repeats."""
    if maximum <= 0 or not patch_paths:
        return [], []
    metadata = metadata or []
    quality: list[PatchQuality] = []
    for index, path in enumerate(patch_paths):
        source_frame = index
        if index < len(metadata):
            source_frame = int(
                metadata[index].get("sourceFrame", index)
            )
        quality.append(score_patch(path, index, source_frame))

    candidates = [item for item in quality if item.eligible]
    if not candidates:
        return [], quality
    ranked = sorted(
        candidates,
        key=lambda item: item.score,
        reverse=True,
    )
    descriptors = {
        item.index: structural_descriptor(patch_paths[item.index])
        for item in ranked
    }
    def size_class(item: PatchQuality) -> str:
        if item.index < len(metadata):
            declared = str(metadata[item.index].get("sizeClass") or "")
            if declared in {"small", "medium", "large"}:
                return declared
        side = max(item.width, item.height)
        if side <= 220:
            return "small"
        if side <= 420:
            return "medium"
        return "large"

    base_quota = maximum // 3
    quota = {
        "small": base_quota,
        "medium": maximum - base_quota * 2,
        "large": base_quota,
    }
    selected: list[PatchQuality] = []

    def choose_from(
        pool: list[PatchQuality],
        target: int,
        class_name: str,
        *,
        enforce_similarity: bool,
    ) -> None:
        while sum(size_class(item) == class_name for item in selected) < target:
            choices: list[tuple[float, PatchQuality, float]] = []
            for item in pool:
                if item in selected:
                    continue
                similarities = [
                    structural_similarity(
                        descriptors[item.index],
                        descriptors[accepted.index],
                    )
                    for accepted in selected
                ]
                closest_similarity = max(similarities, default=0.0)
                if enforce_similarity and closest_similarity >= 0.92:
                    continue
                closest_frame_distance = min(
                    (
                        abs(item.source_frame - accepted.source_frame)
                        for accepted in selected
                    ),
                    default=999,
                )
                temporal_penalty = (
                    0.14 * (6 - closest_frame_distance) / 6
                    if closest_frame_distance < 6
                    else 0.0
                )
                same_frame_count = sum(
                    accepted.source_frame == item.source_frame
                    for accepted in selected
                )
                diversity_score = (
                    item.score
                    - 0.38 * max(0.0, closest_similarity)
                    - temporal_penalty
                    - 0.18 * same_frame_count
                )
                choices.append(
                    (diversity_score, item, closest_similarity)
                )
            if not choices:
                break
            _, chosen, _ = max(choices, key=lambda choice: choice[0])
            selected.append(chosen)

    for size_class_name in ("small", "medium", "large"):
        class_pool = [
            item
            for item in ranked
            if size_class(item) == size_class_name
        ]
        choose_from(
            class_pool,
            quota[size_class_name],
            size_class_name,
            enforce_similarity=True,
        )

    # If a strict visual threshold leaves one size quota short, fill from the
    # best remaining readable patches while retaining the similarity penalty.
    while len(selected) < maximum:
        choices: list[tuple[float, PatchQuality, float]] = []
        for item in ranked:
            if item in selected:
                continue
            similarities = [
                structural_similarity(
                    descriptors[item.index],
                    descriptors[accepted.index],
                )
                for accepted in selected
            ]
            closest_similarity = max(similarities, default=0.0)
            closest_frame_distance = min(
                (
                    abs(item.source_frame - accepted.source_frame)
                    for accepted in selected
                ),
                default=999,
            )
            temporal_penalty = (
                0.14 * (6 - closest_frame_distance) / 6
                if closest_frame_distance < 6
                else 0.0
            )
            same_frame_count = sum(
                accepted.source_frame == item.source_frame
                for accepted in selected
            )
            diversity_score = (
                item.score
                - 0.38 * max(0.0, closest_similarity)
                - temporal_penalty
                - 0.18 * same_frame_count
            )
            choices.append(
                (diversity_score, item, closest_similarity)
            )
        if not choices:
            break
        _, chosen, _ = max(choices, key=lambda choice: choice[0])
        selected.append(chosen)

    for item in ranked:
        if item in selected or not selected:
            continue
        closest = max(
            selected,
            key=lambda accepted: structural_similarity(
                descriptors[item.index],
                descriptors[accepted.index],
            ),
        )
        closest_similarity = structural_similarity(
            descriptors[item.index],
            descriptors[closest.index],
        )
        if closest_similarity >= 0.92:
            item.duplicate_of = closest.index
            item.visual_similarity = closest_similarity
    return sorted(item.index for item in selected), quality
