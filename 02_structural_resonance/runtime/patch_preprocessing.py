"""Optional hidden patch preprocessing for structure-led image search."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


PATCH_TRANSFORMS = ("original", "contrast", "structure")


def transform_patch(image: Image.Image, mode: str = "original") -> Image.Image:
    """Prepare one DINO patch for CLIP/HOG without changing the saved patch."""
    if mode not in PATCH_TRANSFORMS:
        raise ValueError(
            f"Unknown patch transform {mode!r}; choose from {PATCH_TRANSFORMS}"
        )
    rgb = np.asarray(image.convert("RGB"))
    if mode == "original":
        return Image.fromarray(rgb)

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(6, 6))
    contrast = clahe.apply(gray)
    contrast = cv2.bilateralFilter(contrast, 5, 28, 28)
    if mode == "contrast":
        low, high = np.percentile(contrast, (2.0, 98.0))
        stretched = np.clip(
            (contrast.astype(np.float32) - low)
            / max(1.0, float(high - low)),
            0,
            1,
        )
        # An S-curve creates real black and white anchors instead of merely
        # sharpening the original mid-grey surface.
        curved = 1.0 / (1.0 + np.exp(-8.0 * (stretched - 0.5)))
        curved = (curved - curved.min()) / max(
            1e-6,
            float(curved.max() - curved.min()),
        )
        strong_contrast = np.clip(curved * 255, 0, 255).astype(np.uint8)
        return Image.fromarray(
            cv2.cvtColor(strong_contrast, cv2.COLOR_GRAY2RGB)
        )

    median = float(np.median(contrast))
    # Structure mode keeps enough photographic information for CLIP while
    # making the same contours explicit for HOG and image-to-image ranking.
    structure_lower = max(18, round(0.55 * median))
    structure_upper = max(
        structure_lower + 24,
        min(230, round(1.25 * median)),
    )
    structure_edges = cv2.Canny(
        contrast,
        structure_lower,
        structure_upper,
        L2gradient=True,
    )
    structure_edges = cv2.morphologyEx(
        structure_edges,
        cv2.MORPH_CLOSE,
        np.ones((2, 2), np.uint8),
    )
    lifted = cv2.normalize(
        contrast,
        None,
        alpha=42,
        beta=238,
        norm_type=cv2.NORM_MINMAX,
    )
    structure = lifted.copy()
    structure[structure_edges > 0] = np.minimum(
        structure[structure_edges > 0],
        20,
    )
    structure = cv2.GaussianBlur(structure, (0, 0), 0.35)
    return Image.fromarray(cv2.cvtColor(structure, cv2.COLOR_GRAY2RGB))
