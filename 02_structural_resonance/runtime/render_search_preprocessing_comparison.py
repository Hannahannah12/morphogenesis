"""Render current-vs-structure-enhanced search results as one review sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CURRENT = (
    PROJECT_ROOT
    / "05_shared_data"
    / "exhibition"
    / "ice_crystal_03"
    / "02_structural_resonance"
    / "manifest.json"
)
DEFAULT_EXPERIMENT = (
    PROJECT_ROOT
    / "09_experiments"
    / "05_structural_search_preprocessing_example"
    / "ice_crystal_03_patch_49"
    / "manifest.json"
)


def find_set(
    manifest: dict,
    patch_name: str,
    branch: str | None = None,
) -> dict:
    for resonance_set in manifest.get("resonanceSets", []):
        patch_value = str(resonance_set.get("patch", ""))
        patch_id = str(resonance_set.get("patchId", ""))
        patch_matches = (
            Path(patch_value).name == patch_name
            or patch_id == Path(patch_name).stem
        )
        branch_matches = (
            branch is None
            or resonance_set.get("branch") == branch
        )
        if patch_matches and branch_matches:
            return resonance_set
    raise RuntimeError(f"No resonance set was found for {patch_name}")


def resolve_result(manifest_path: Path, url: str) -> Path:
    prefix = "/"
    if url.startswith(prefix):
        return PROJECT_ROOT / url.removeprefix(prefix)
    return manifest_path.parent / url


def render_group(
    title: str,
    manifest_path: Path,
    resonance_set: dict,
    *,
    columns: int = 5,
    card_size: tuple[int, int] = (250, 190),
) -> np.ndarray:
    results = resonance_set.get("results", [])[:10]
    rows = max(1, (len(results) + columns - 1) // columns)
    card_width, card_height = card_size
    title_height = 54
    canvas = np.full(
        (title_height + rows * card_height, columns * card_width, 3),
        246,
        dtype=np.uint8,
    )
    cv2.putText(
        canvas,
        title,
        (14, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (10, 10, 10),
        1,
        cv2.LINE_AA,
    )
    keywords = " / ".join(str(value) for value in resonance_set.get("keywords", [])[:8])
    cv2.putText(
        canvas,
        keywords[:160],
        (14, 44),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        (55, 55, 55),
        1,
        cv2.LINE_AA,
    )
    for index, result in enumerate(results):
        row, column = divmod(index, columns)
        x = column * card_width
        y = title_height + row * card_height
        path = resolve_result(manifest_path, str(result["url"]))
        image = Image.open(path).convert("RGB")
        fitted = ImageOps.fit(
            image,
            (card_width - 10, card_height - 38),
            method=Image.Resampling.LANCZOS,
        )
        rendered = cv2.cvtColor(np.asarray(fitted), cv2.COLOR_RGB2BGR)
        canvas[
            y + 5 : y + 5 + rendered.shape[0],
            x + 5 : x + 5 + rendered.shape[1],
        ] = rendered
        label = (
            f"{index + 1:02d}  {result.get('category', '')}  "
            f"{float(result.get('score', 0)):.2f}"
        )
        cv2.putText(
            canvas,
            label[:38],
            (x + 8, y + card_height - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
    return canvas


def render(
    current_manifest: Path,
    experiment_manifest: Path,
    output: Path,
) -> None:
    current = json.loads(current_manifest.read_text(encoding="utf-8"))
    experiment = json.loads(experiment_manifest.read_text(encoding="utf-8"))
    current_set = find_set(current, "patch_49.jpg")
    contrast_set = find_set(experiment, "patch_49.jpg", "contrast")
    structure_set = find_set(experiment, "patch_49.jpg", "structure")
    current_group = render_group(
        "CURRENT SEARCH / original patch",
        current_manifest,
        current_set,
    )
    contrast_group = render_group(
        "EXPERIMENT A / independent contrast imagination",
        experiment_manifest,
        contrast_set,
    )
    structure_group = render_group(
        "EXPERIMENT B / independent structure imagination",
        experiment_manifest,
        structure_set,
    )
    gap = np.full((18, current_group.shape[1], 3), 255, dtype=np.uint8)
    sheet = np.vstack(
        [
            current_group,
            gap,
            contrast_group,
            gap,
            structure_group,
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), sheet)
    print(output, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--experiment", type=Path, default=DEFAULT_EXPERIMENT)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_EXPERIMENT.parent / "03_dual_branch_comparison.jpg",
    )
    args = parser.parse_args()
    render(
        args.current.resolve(),
        args.experiment.resolve(),
        args.output.resolve(),
    )


if __name__ == "__main__":
    main()
