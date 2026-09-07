"""Create one non-destructive patch preprocessing comparison experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
from PIL import Image, ImageOps

from patch_preprocessing import PATCH_TRANSFORMS, transform_patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "09_experiments"
    / "05_structural_search_preprocessing_example"
    / "ice_crystal_03_patch_49"
)


def panel(image: Image.Image, label: str, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    fitted = ImageOps.contain(image.convert("RGB"), (width, height - 34))
    canvas = Image.new("RGB", size, "white")
    canvas.paste(
        fitted,
        ((width - fitted.width) // 2, 34 + (height - 34 - fitted.height) // 2),
    )
    array = cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
    cv2.putText(
        array,
        label,
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    return array


def create(source: Path, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    inputs = output / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    source_image = Image.open(source).convert("RGB")
    variants: dict[str, Image.Image] = {}
    for mode in PATCH_TRANSFORMS:
        transformed = transform_patch(source_image, mode)
        transformed.save(inputs / f"{mode}.jpg", quality=95)
        variants[mode] = transformed

    comparison = np.hstack(
        [
            panel(variants[mode], mode, (360, 270))
            for mode in PATCH_TRANSFORMS
        ]
    )
    comparison_path = output / "01_preprocessing_comparison.jpg"
    cv2.imwrite(str(comparison_path), comparison)

    search_patch_dir = output / "patches"
    search_patch_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, search_patch_dir / "patch_49.jpg")
    manifest = {
        "pipeline": "structural-search-preprocessing-example",
        "sourceCrystal": "ice_crystal_03",
        "sourcePatch": str(source),
        "patches": ["patches/patch_49.jpg"],
        "resonanceSets": [],
        "searchState": "waiting",
        "experiment": (
            "Search one original patch using hidden structure preprocessing; "
            "the official Exhibition manifest is not modified."
        ),
    }
    manifest_path = output / "manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(comparison_path, flush=True)
    print(manifest_path, flush=True)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    create(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
