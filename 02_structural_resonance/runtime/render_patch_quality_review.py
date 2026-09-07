"""Render selected and rejected patch examples for visual QA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from patch_quality import select_structural_patch_indices


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "05_shared_data"
    / "exhibition"
    / "ice_crystal_03"
    / "02_structural_resonance"
    / "manifest.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "09_experiments"
    / "05_structural_search_preprocessing_example"
    / "04_patch_quality_selection.jpg"
)


def card(
    path: Path,
    label: str,
    *,
    size: tuple[int, int] = (360, 245),
) -> np.ndarray:
    width, height = size
    image = cv2.imread(str(path))
    canvas = np.full((height, width, 3), 246, dtype=np.uint8)
    target_height = height - 38
    scale = min(width / image.shape[1], target_height / image.shape[0])
    resized = cv2.resize(
        image,
        (
            max(1, round(image.shape[1] * scale)),
            max(1, round(image.shape[0] * scale)),
        ),
        interpolation=cv2.INTER_AREA,
    )
    x = (width - resized.shape[1]) // 2
    y = 34 + (target_height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    cv2.putText(
        canvas,
        label,
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (15, 15, 15),
        1,
        cv2.LINE_AA,
    )
    return canvas


def render(manifest_path: Path, output: Path, maximum: int = 6) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    patch_paths = [
        root / value
        for value in manifest.get("patches", [])
    ]
    selected, quality = select_structural_patch_indices(
        patch_paths,
        maximum,
        manifest.get("patchMetadata", []),
    )
    selected_set = set(selected)
    chosen = sorted(
        (item for item in quality if item.index in selected_set),
        key=lambda item: selected.index(item.index),
    )
    rejected = sorted(
        (item for item in quality if not item.eligible),
        key=lambda item: item.score,
    )[:6]
    selected_cards = [
        card(
            patch_paths[item.index],
            (
                f"SELECTED {item.file} / score {item.score:.3f} / "
                f"frame {item.source_frame}"
            ),
        )
        for item in chosen
    ]
    rejected_cards = [
        card(
            patch_paths[item.index],
            (
                f"REJECTED {item.file} / "
                f"{','.join(item.rejection_reasons)}"
            ),
        )
        for item in rejected
    ]
    selected_grid = np.vstack(
        [
            np.hstack(selected_cards[:3]),
            np.hstack(selected_cards[3:6]),
        ]
    )
    rejected_grid = np.vstack(
        [
            np.hstack(rejected_cards[:3]),
            np.hstack(rejected_cards[3:6]),
        ]
    )
    title = np.full(
        (52, selected_grid.shape[1], 3),
        255,
        dtype=np.uint8,
    )
    cv2.putText(
        title,
        "STRUCTURE QUALITY SELECTION / top 6",
        (14, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.68,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    divider = np.full(
        (52, selected_grid.shape[1], 3),
        255,
        dtype=np.uint8,
    )
    cv2.putText(
        divider,
        "AUTO-REJECTED EXAMPLES / flat, small or weak contour",
        (14, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    sheet = np.vstack([title, selected_grid, divider, rejected_grid])
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), sheet)
    print(output, flush=True)
    print("selected", selected, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--maximum", type=int, default=6)
    args = parser.parse_args()
    render(
        args.manifest.resolve(),
        args.output.resolve(),
        args.maximum,
    )


if __name__ == "__main__":
    main()
