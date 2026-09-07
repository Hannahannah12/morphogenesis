"""Delayed Structural Resonance search derived from the research Notebook.

Run this file with the existing `crystal` Conda environment, which contains the
same OpenAI CLIP ViT-B/32 and HOG dependencies used by the Notebook.

The worker preserves the Notebook's live iNaturalist + NASA candidate search,
CLIP threshold 0.6, and HOG threshold 0.5. Only the selected API results are
saved into the current crystal output so browser playback remains reliable
after the delayed search has completed.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
from pathlib import Path
import random
import shutil
from typing import Any

import clip
import nltk
from nltk.corpus import wordnet
import numpy as np
from PIL import Image
import requests
from scipy.spatial.distance import cosine
from skimage.feature import hog
import torch

from patch_preprocessing import PATCH_TRANSFORMS, transform_patch
from patch_quality import select_structural_patch_indices


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NLTK_DATA_ROOT = Path(__file__).resolve().parent / "nltk_data"
nltk.data.path.insert(0, str(NLTK_DATA_ROOT))
USER_AGENT = "Morphogenesis-Structural-Resonance/1.0"
INATURALIST_API = "https://api.inaturalist.org/v1/observations"
NASA_API = "https://images-api.nasa.gov/search"
BASE_WORDS = [
    "lichen", "coral", "fungi", "mycelium", "moss", "algae", "fern", "diatom",
    "neuron", "blood vessel", "leaf vein", "root system", "spider web", "honeycomb",
    "bacteria", "cell", "tree bark", "sea anemone", "river delta", "mountain",
    "canyon", "glacier", "lava", "sand dune", "fault", "erosion", "coastline",
    "cave", "stalactite", "nebula", "galaxy", "star", "aurora", "planet",
    "asteroid", "comet", "supernova", "ice crystal", "snowflake", "frost",
    "crack", "crystal", "diffraction", "turbulence", "vortex", "foam",
]


def expand_words(base_words: list[str]) -> list[str]:
    """Notebook cell 3: expand the hand-authored pool with WordNet lemmas."""
    expanded = set(base_words)
    for word in base_words:
        for synonym in wordnet.synsets(word):
            for lemma in synonym.lemmas():
                expanded.add(lemma.name().replace("_", " "))
    return list(expanded)


def project_url(path: Path) -> str:
    return "/" + path.resolve().relative_to(PROJECT_ROOT).as_posix()


def get_hog_features(image: Image.Image) -> np.ndarray:
    gray = np.array(image.convert("L").resize((128, 128)))
    features = hog(
        gray,
        orientations=8,
        pixels_per_cell=(16, 16),
        cells_per_block=(1, 1),
        visualize=False,
    )
    return features


def visual_fingerprint(image: Image.Image) -> int:
    """Compact difference hash for cross-query result de-duplication."""
    gray = np.asarray(
        image.convert("L").resize((9, 8), Image.Resampling.LANCZOS),
        dtype=np.int16,
    )
    bits = (gray[:, 1:] > gray[:, :-1]).reshape(-1)
    fingerprint = 0
    for index, bit in enumerate(bits):
        if bit:
            fingerprint |= 1 << index
    return fingerprint


def fingerprint_is_near_duplicate(
    fingerprint: int,
    selected: list[int],
    maximum_distance: int = 4,
) -> bool:
    return any(
        (fingerprint ^ previous).bit_count() <= maximum_distance
        for previous in selected
    )


def select_patch_indices(total: int, maximum: int) -> list[int]:
    """Automation policy for a Notebook that previously used current_patch."""
    if total <= 0 or maximum <= 0:
        return []
    if maximum == 1:
        return [total // 2]
    if total <= maximum:
        return list(range(total))
    return sorted(
        {
            min(total - 1, round(index * (total - 1) / (maximum - 1)))
            for index in range(maximum)
        }
    )


def query_live_apis(
    keywords: list[str],
    *,
    per_page: int,
) -> tuple[list[dict[str, str]], list[str]]:
    """Notebook cells 5/12: iNaturalist and NASA keyword candidate search."""
    candidates: list[dict[str, str]] = []
    errors: list[str] = []
    headers = {"User-Agent": USER_AGENT}
    for keyword in keywords:
        try:
            response = requests.get(
                INATURALIST_API,
                params={
                    "quality_grade": "research",
                    "photos": "true",
                    "per_page": per_page,
                    "taxon_name": keyword,
                },
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            for observation in response.json().get("results", []):
                photos = observation.get("photos") or []
                if not photos:
                    continue
                url = str(photos[0].get("url", "")).replace("square", "medium")
                if url:
                    candidates.append(
                        {
                            "source": "inat",
                            "category": keyword,
                            "url": url,
                        }
                    )
        except Exception as error:
            errors.append(f"iNaturalist / {keyword}: {error}")

        try:
            response = requests.get(
                NASA_API,
                params={
                    "q": keyword,
                    "media_type": "image",
                    "page_size": per_page,
                },
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            for item in response.json().get("collection", {}).get("items", []):
                links = item.get("links") or []
                if not links:
                    continue
                url = str(links[0].get("href", ""))
                if url:
                    candidates.append(
                        {
                            "source": "nasa",
                            "category": keyword,
                            "url": url,
                        }
                    )
        except Exception as error:
            errors.append(f"NASA / {keyword}: {error}")

    random.shuffle(candidates)
    unique: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        if candidate["url"] in seen_urls:
            continue
        seen_urls.add(candidate["url"])
        unique.append(candidate)
    return unique, errors


def download_candidate(
    candidate: dict[str, str],
) -> tuple[dict[str, str], Image.Image] | None:
    try:
        response = requests.get(
            candidate["url"],
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        response.raise_for_status()
        image = Image.open(BytesIO(response.content)).convert("RGB")
        image.load()
        return candidate, image
    except Exception:
        return None


def save_api_result(
    *,
    output_dir: Path,
    patch_id: str,
    result_number: int,
    candidate: dict[str, str],
    image: Image.Image,
    method: str,
    score: float,
    branch: str | None = None,
) -> dict[str, Any]:
    result_dir = output_dir / "search_results" / patch_id
    if branch:
        result_dir = result_dir / branch
    result_dir.mkdir(parents=True, exist_ok=True)
    destination = result_dir / f"{result_number:02d}.jpg"
    image.save(destination, format="JPEG", quality=90, optimize=True)
    return {
        "url": project_url(destination),
        "sourceUrl": candidate["url"],
        "provider": candidate["source"],
        "method": method,
        "score": round(score, 4),
        "category": candidate["category"],
    }


def retain_quality_patches(
    *,
    output_dir: Path,
    manifest: dict[str, Any],
    patch_paths: list[Path],
    selected_original_indices: list[int],
    patch_quality: list[Any],
    minimum_retained: int = 25,
) -> tuple[list[Path], list[int], list[dict[str, Any]]]:
    """Keep a size-balanced readable set at the exhibition target."""
    source_metadata = manifest.get("patchMetadata", [])

    def size_class(item: Any) -> str:
        if item.index < len(source_metadata):
            declared = str(
                source_metadata[item.index].get("sizeClass") or ""
            )
            if declared in {"small", "medium", "large"}:
                return declared
        side = max(item.width, item.height)
        if side <= 220:
            return "small"
        if side <= 420:
            return "medium"
        return "large"

    retained_original_indices = list(selected_original_indices)
    readable = sorted(
        [
            item
            for item in patch_quality
            if "black-background" not in item.rejection_reasons
            and "mostly-black" not in item.rejection_reasons
        ],
        key=lambda item: (
            not item.eligible,
            item.duplicate_of is not None,
            -item.score,
        ),
    )
    base_target, remainder = divmod(minimum_retained, 3)
    target_by_size = {
        "small": base_target,
        "medium": base_target + (1 if remainder >= 1 else 0),
        "large": base_target + (1 if remainder >= 2 else 0),
    }
    quality_by_index = {
        item.index: item
        for item in patch_quality
    }
    for class_name, target in target_by_size.items():
        current_count = sum(
            size_class(quality_by_index[index]) == class_name
            for index in retained_original_indices
            if index in quality_by_index
        )
        for item in readable:
            if current_count >= target:
                break
            if (
                item.index not in retained_original_indices
                and size_class(item) == class_name
            ):
                retained_original_indices.append(item.index)
                current_count += 1
    if len(retained_original_indices) < minimum_retained:
        for item in readable:
            if item.index not in retained_original_indices:
                retained_original_indices.append(item.index)
            if len(retained_original_indices) >= minimum_retained:
                break
    retained_original_indices = retained_original_indices[:minimum_retained]
    retained_original_indices.sort()
    if len(retained_original_indices) < minimum_retained:
        raise RuntimeError(
            "Patch quality filtering retained "
            f"{len(retained_original_indices)} readable patches; "
            f"at least {minimum_retained} are required"
        )

    patch_dir = output_dir / "patches"
    candidate_dir = output_dir / "patch_candidates"
    staging_dir = output_dir / "patches_selected"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    old_metadata = manifest.get("patchMetadata", [])
    candidate_metadata: list[dict[str, Any]] = []
    candidate_archive_is_source = bool(patch_paths) and all(
        path.parent.resolve() == candidate_dir.resolve()
        for path in patch_paths
    )
    if candidate_archive_is_source:
        for candidate_index, candidate_path in enumerate(patch_paths):
            metadata = (
                dict(old_metadata[candidate_index])
                if candidate_index < len(old_metadata)
                else {}
            )
            metadata.update(
                {
                    "id": f"candidate_{candidate_index + 1:02d}",
                    "file": candidate_path.relative_to(output_dir).as_posix(),
                    "candidateIndex": candidate_index,
                }
            )
            candidate_metadata.append(metadata)
    else:
        candidate_staging = output_dir / "patch_candidates_staging"
        if candidate_staging.exists():
            shutil.rmtree(candidate_staging)
        candidate_staging.mkdir(parents=True, exist_ok=True)
        for candidate_index, candidate_path in enumerate(patch_paths):
            destination = (
                candidate_staging / f"patch_{candidate_index + 1:02d}.jpg"
            )
            shutil.copy2(candidate_path, destination)
            metadata = (
                dict(old_metadata[candidate_index])
                if candidate_index < len(old_metadata)
                else {}
            )
            metadata.update(
                {
                    "id": f"candidate_{candidate_index + 1:02d}",
                    "file": (
                        candidate_dir / destination.name
                    ).relative_to(output_dir).as_posix(),
                    "candidateIndex": candidate_index,
                }
            )
            candidate_metadata.append(metadata)
        if candidate_dir.exists():
            shutil.rmtree(candidate_dir)
        candidate_dir.mkdir(parents=True, exist_ok=True)
        for staged_path in candidate_staging.glob("*.jpg"):
            shutil.copy2(staged_path, candidate_dir / staged_path.name)
        shutil.rmtree(candidate_staging)
    new_metadata: list[dict[str, Any]] = []
    old_to_new: dict[int, int] = {}
    for new_index, old_index in enumerate(retained_original_indices):
        patch_id = f"patch_{new_index + 1:02d}"
        destination = staging_dir / f"{patch_id}.jpg"
        shutil.copy2(patch_paths[old_index], destination)
        metadata = (
            dict(old_metadata[old_index])
            if old_index < len(old_metadata)
            else {}
        )
        metadata.update(
            {
                "id": patch_id,
                "file": f"patches/{patch_id}.jpg",
                "candidateIndex": old_index,
                "candidateFile": patch_paths[old_index].name,
            }
        )
        new_metadata.append(metadata)
        old_to_new[old_index] = new_index

    if patch_dir.exists():
        shutil.rmtree(patch_dir)
    patch_dir.mkdir(parents=True, exist_ok=True)
    for staged_path in staging_dir.glob("*.jpg"):
        shutil.copy2(staged_path, patch_dir / staged_path.name)
    shutil.rmtree(staging_dir)

    retained_paths = [
        patch_dir / f"patch_{index + 1:02d}.jpg"
        for index in range(len(retained_original_indices))
    ]
    selected_indices = [
        old_to_new[index]
        for index in selected_original_indices
        if index in old_to_new
    ]
    previous_candidate_count = int(
        manifest.get("candidatePatchCount", 0) or 0
    )
    candidate_patch_count = max(previous_candidate_count, len(patch_quality))
    manifest["candidatePatchCount"] = candidate_patch_count
    manifest["candidatePatches"] = [
        path.relative_to(output_dir).as_posix()
        for path in sorted(candidate_dir.glob("*.jpg"))
    ]
    manifest["candidatePatchMetadata"] = candidate_metadata
    manifest["retainedPatchCount"] = len(retained_paths)
    manifest["rejectedPatchCount"] = (
        candidate_patch_count - len(retained_paths)
    )
    manifest["patches"] = [
        path.relative_to(output_dir).as_posix()
        for path in retained_paths
    ]
    manifest["patchMetadata"] = new_metadata
    manifest["selectedPatchIndices"] = selected_indices
    current_audit = [
        item.serialize()
        for item in patch_quality
    ]
    previous_candidate_audit = manifest.get("candidatePatchQualityAudit", [])
    if len(previous_candidate_audit) < len(current_audit):
        manifest["candidatePatchQualityAudit"] = current_audit
    manifest["patchQualityAudit"] = current_audit
    manifest["patchRetentionPolicy"] = (
        f"near-completion candidates archived; at least {minimum_retained} "
        "readable nonblack patches retained with balanced size targets"
    )
    manifest["retainedPatchSizeTargets"] = target_by_size
    manifest["searchPatchSizeTargets"] = {
        "small": 3,
        "medium": 4,
        "large": 3,
    }
    return retained_paths, selected_indices, new_metadata


def run_search(
    manifest_path: Path,
    *,
    max_patches: int = 10,
    selected_patch_numbers: list[int] | None = None,
    top_k: int = 5,
    keyword_count: int = 10,
    per_page: int = 20,
    max_candidates: int = 240,
    patch_transform: str = "dual",
    ranking_mode: str = "structure_fusion",
    quality_only: bool = False,
    minimum_retained: int = 25,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    operator_selected = selected_patch_numbers is not None
    if operator_selected:
        patch_paths = [
            output_dir / value for value in manifest.get("patches", [])
        ]
        source_metadata = manifest.get("patchMetadata", [])
    else:
        candidate_values = manifest.get("candidatePatches", [])
        candidate_paths = [output_dir / value for value in candidate_values]
        candidate_paths = [path for path in candidate_paths if path.exists()]
        if len(candidate_paths) >= 40:
            patch_paths = candidate_paths
            source_metadata = manifest.get("candidatePatchMetadata", [])
        else:
            patch_paths = [
                output_dir / value for value in manifest.get("patches", [])
            ]
            source_metadata = manifest.get("patchMetadata", [])
    patch_paths = [path for path in patch_paths if path.exists()]
    search_root = output_dir / "search_results"
    if search_root.exists() and not quality_only:
        if operator_selected:
            for number in selected_patch_numbers or []:
                patch_index = number - 1
                if 0 <= patch_index < len(patch_paths):
                    shutil.rmtree(
                        search_root / patch_paths[patch_index].stem,
                        ignore_errors=True,
                    )
        else:
            shutil.rmtree(search_root)

    if not patch_paths:
        manifest["searchState"] = "no_patches"
        manifest["resonanceSets"] = []
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    manifest["patchMetadata"] = source_metadata
    if operator_selected:
        selected_patch_indices = sorted(
            {
                number - 1
                for number in selected_patch_numbers or []
                if 1 <= number <= len(patch_paths)
            }
        )
        invalid_numbers = sorted(
            {
                number
                for number in selected_patch_numbers or []
                if number < 1 or number > len(patch_paths)
            }
        )
        if invalid_numbers:
            raise ValueError(
                "Selected patch numbers are outside the manifest range: "
                + ", ".join(str(number) for number in invalid_numbers)
            )
        if not selected_patch_indices:
            raise ValueError("At least one valid selected patch number is required")
        manifest["patchSelectionMethod"] = (
            "operator-specified-1-based-manifest-patch-numbers"
        )
        manifest["selectedPatchNumbers"] = [
            index + 1
            for index in selected_patch_indices
        ]
    else:
        selected_original_indices, patch_quality = select_structural_patch_indices(
            patch_paths,
            max_patches,
            source_metadata,
        )
        patch_paths, selected_patch_indices, _ = retain_quality_patches(
            output_dir=output_dir,
            manifest=manifest,
            patch_paths=patch_paths,
            selected_original_indices=selected_original_indices,
            patch_quality=patch_quality,
            minimum_retained=minimum_retained,
        )
        search_target = min(max_patches, len(patch_paths))
        for retained_index in range(len(patch_paths)):
            if len(selected_patch_indices) >= search_target:
                break
            if retained_index not in selected_patch_indices:
                selected_patch_indices.append(retained_index)
        selected_patch_indices.sort()
    manifest["selectedPatchIndices"] = selected_patch_indices
    if quality_only:
        manifest["searchState"] = "quality_ready"
        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        return manifest
    manifest["searchState"] = "searching"
    manifest["resonanceSets"] = []
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    if not patch_paths or not selected_patch_indices:
        manifest["searchState"] = "no_quality_patches"
        manifest["resonanceSets"] = []
        manifest["patchQualitySelectionMethod"] = (
            "nonblack-texture-clarity+64px-visual-deduplication"
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        return manifest

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(
        f"loading CLIP ViT-B/32 on {device} / "
        f"{len(selected_patch_indices)} selected patches",
        flush=True,
    )
    model, preprocess = clip.load("ViT-B/32", device=device)
    model.eval()

    word_pool = expand_words(BASE_WORDS)
    text_tokens = clip.tokenize(word_pool).to(device)
    with torch.no_grad():
        text_features = model.encode_text(text_tokens)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    if patch_transform == "dual":
        branch_names = ("contrast", "structure")
    elif patch_transform in PATCH_TRANSFORMS:
        branch_names = (patch_transform,)
    else:
        raise ValueError(f"Unknown patch transform: {patch_transform}")

    resonance_sets: list[dict[str, Any]] = []
    api_errors: list[str] = []
    total_api_candidates = 0
    candidate_count_by_branch = {
        branch: 0
        for branch in branch_names
    }
    globally_selected_urls: set[str] = set()
    globally_selected_fingerprints: list[int] = []
    for patch_index in selected_patch_indices:
        patch_path = patch_paths[patch_index]
        print(
            f"patch {patch_index + 1:02d} / preparing {patch_path.name}",
            flush=True,
        )
        patch_image = Image.open(patch_path).convert("RGB")
        branch_data: dict[str, dict[str, Any]] = {}
        for branch in branch_names:
            search_patch_image = transform_patch(patch_image, branch)
            patch_tensor = preprocess(search_patch_image).unsqueeze(0).to(device)
            with torch.no_grad():
                patch_feature_tensor = model.encode_image(patch_tensor)
                patch_feature_tensor = (
                    patch_feature_tensor
                    / patch_feature_tensor.norm(dim=-1, keepdim=True)
                )
                keyword_scores = (
                    patch_feature_tensor @ text_features.T
                ).squeeze().cpu().numpy()
            keyword_indices = keyword_scores.argsort()[::-1][:keyword_count]
            keywords = [word_pool[int(index)] for index in keyword_indices]
            branch_data[branch] = {
                "image": search_patch_image,
                "clip": patch_feature_tensor.cpu().numpy().flatten(),
                "hog": get_hog_features(search_patch_image),
                "keywords": keywords,
            }

        patch_id = patch_path.stem
        for branch in branch_names:
            print(
                f"patch {patch_index + 1:02d} / {branch} / querying APIs",
                flush=True,
            )
            patch_clip = branch_data[branch]["clip"]
            patch_hog = branch_data[branch]["hog"]
            api_candidates, errors = query_live_apis(
                branch_data[branch]["keywords"],
                per_page=per_page,
            )
            api_errors.extend(
                f"{branch}: {error}"
                for error in errors
            )
            api_candidates = api_candidates[:max_candidates]
            print(
                f"patch {patch_index + 1:02d} / {branch} / "
                f"{len(api_candidates)} unique candidates",
                flush=True,
            )
            total_api_candidates += len(api_candidates)
            candidate_count_by_branch[branch] += len(api_candidates)

            downloaded: list[tuple[dict[str, str], Image.Image]] = []
            with ThreadPoolExecutor(max_workers=12) as executor:
                futures = [
                    executor.submit(download_candidate, candidate)
                    for candidate in api_candidates
                ]
                for future in as_completed(futures):
                    item = future.result()
                    if item is not None:
                        downloaded.append(item)

            candidate_tensors = [
                preprocess(image)
                for _, image in downloaded
            ]
            candidate_clip: list[np.ndarray] = []
            with torch.no_grad():
                for start in range(0, len(candidate_tensors), 32):
                    batch = torch.stack(
                        candidate_tensors[start : start + 32]
                    ).to(device)
                    features = model.encode_image(batch)
                    features = (
                        features
                        / features.norm(dim=-1, keepdim=True)
                    )
                    candidate_clip.extend(features.cpu().numpy())

            candidate_is_bw: list[bool] = []
            for _, image in downloaded:
                image_array = np.asarray(image)
                red = image_array[:, :, 0].astype(np.int16)
                green = image_array[:, :, 1].astype(np.int16)
                candidate_is_bw.append(
                    float(np.mean(np.abs(red - green))) < 15
                )
            candidate_hog = [
                get_hog_features(
                    transform_patch(image, branch)
                    if ranking_mode == "structure_fusion"
                    else image
                )
                for _, image in downloaded
            ]
            clip_bw_results: list[tuple[float, int]] = []
            clip_color_results: list[tuple[float, int]] = []
            hog_results: list[tuple[float, int]] = []
            fusion_results: list[tuple[float, int]] = []
            for candidate_index, candidate_feature in enumerate(candidate_clip):
                clip_score = float(np.dot(patch_clip, candidate_feature))
                if clip_score > 0.6:
                    target = (
                        clip_bw_results
                        if candidate_is_bw[candidate_index]
                        else clip_color_results
                    )
                    target.append((clip_score, candidate_index))
                hog_score = float(
                    1 - cosine(patch_hog, candidate_hog[candidate_index])
                )
                if np.isfinite(hog_score) and hog_score > 0.5:
                    hog_results.append((hog_score, candidate_index))
                if (
                    ranking_mode == "structure_fusion"
                    and clip_score > 0.58
                    and np.isfinite(hog_score)
                ):
                    fusion_score = (
                        0.72 * clip_score
                        + 0.28 * max(0.0, hog_score)
                    )
                    fusion_results.append((fusion_score, candidate_index))

            clip_bw_results.sort(reverse=True)
            clip_color_results.sort(reverse=True)
            hog_results.sort(reverse=True)
            fusion_results.sort(reverse=True)
            half = top_k // 2
            clip_results = (
                clip_bw_results[:half]
                + clip_color_results[:half]
            )
            clip_results.sort(reverse=True)
            if ranking_mode == "structure_fusion":
                ranked_groups = ((f"{branch}_fusion", fusion_results),)
            else:
                ranked_groups = (
                    (f"{branch}_clip", clip_results),
                    (f"{branch}_hog", hog_results),
                )

            selected: list[tuple[str, float, int]] = []
            selected_candidate_indices: set[int] = set()
            maximum_rank = max(
                (len(ranked) for _, ranked in ranked_groups),
                default=0,
            )
            for rank in range(maximum_rank):
                for method, ranked in ranked_groups:
                    if rank >= len(ranked):
                        continue
                    score, candidate_index = ranked[rank]
                    source_url = downloaded[candidate_index][0]["url"]
                    fingerprint = visual_fingerprint(
                        downloaded[candidate_index][1]
                    )
                    if (
                        source_url in globally_selected_urls
                        or fingerprint_is_near_duplicate(
                            fingerprint,
                            globally_selected_fingerprints,
                        )
                    ):
                        continue
                    selected.append((method, score, candidate_index))
                    selected_candidate_indices.add(candidate_index)
                    globally_selected_urls.add(source_url)
                    globally_selected_fingerprints.append(fingerprint)
                    if len(selected) >= top_k:
                        break
                if len(selected) >= top_k:
                    break

            # If the strict perceptual-distance pass is too selective, fill
            # from globally unique URLs while still rejecting exact visual
            # duplicates. This preserves result count without repeating files.
            if len(selected) < top_k:
                for rank in range(maximum_rank):
                    for method, ranked in ranked_groups:
                        if rank >= len(ranked):
                            continue
                        score, candidate_index = ranked[rank]
                        if candidate_index in selected_candidate_indices:
                            continue
                        source_url = downloaded[candidate_index][0]["url"]
                        fingerprint = visual_fingerprint(
                            downloaded[candidate_index][1]
                        )
                        if (
                            source_url in globally_selected_urls
                            or fingerprint_is_near_duplicate(
                                fingerprint,
                                globally_selected_fingerprints,
                                maximum_distance=0,
                            )
                        ):
                            continue
                        selected.append((method, score, candidate_index))
                        selected_candidate_indices.add(candidate_index)
                        globally_selected_urls.add(source_url)
                        globally_selected_fingerprints.append(fingerprint)
                        if len(selected) >= top_k:
                            break
                    if len(selected) >= top_k:
                        break

            display_results = [
                save_api_result(
                    output_dir=output_dir,
                    patch_id=patch_id,
                    result_number=result_number,
                    candidate=downloaded[candidate_index][0],
                    image=downloaded[candidate_index][1],
                    method=method,
                    score=score,
                    branch=branch,
                )
                for result_number, (method, score, candidate_index)
                in enumerate(selected, start=1)
            ]
            print(
                f"patch {patch_index + 1:02d} / {branch} / "
                f"saved {len(display_results)} results",
                flush=True,
            )
            serialized_clip = [
                result
                for result in display_results
                if "clip" in result["method"] or "fusion" in result["method"]
            ]
            serialized_hog = [
                result
                for result in display_results
                if result["method"].endswith("_hog")
            ]

            resonance_sets.append(
                {
                    "patchIndex": patch_index,
                    "patchId": patch_id,
                    "patch": project_url(patch_path),
                    "branch": branch,
                    "keywords": branch_data[branch]["keywords"],
                    "patchTransform": branch,
                    "clipResults": serialized_clip,
                    "hogResults": serialized_hog,
                    "results": display_results,
                }
            )

    result_count = sum(len(item["results"]) for item in resonance_sets)
    manifest["searchState"] = (
        "complete"
        if result_count
        else "api_no_matching_results"
    )
    manifest["searchPipeline"] = (
        "dual-contrast-structure-inaturalist-nasa-clip-hog"
    )
    manifest["patchPreprocessing"] = patch_transform
    manifest["searchBranches"] = list(branch_names)
    manifest["rankingMode"] = ranking_mode
    manifest["candidateSource"] = "live-inaturalist+nasa-apis"
    manifest["candidateCount"] = total_api_candidates
    manifest["candidateCountByBranch"] = candidate_count_by_branch
    manifest["wordPoolCount"] = len(word_pool)
    manifest["apiErrors"] = api_errors[-20:]
    manifest["searchResultLayout"] = (
        "search_results/<patch_id>/<contrast|structure>/<01..10>.jpg"
    )
    manifest["searchResultsPerPatch"] = {
        branch: top_k
        for branch in branch_names
    }
    manifest["patchQualitySelectionMethod"] = (
        "nonblack-texture-clarity+64px-visual-deduplication"
    )
    manifest["selectedPatchIndices"] = selected_patch_indices
    manifest["resonanceSets"] = resonance_sets
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--max-patches", type=int, default=10)
    parser.add_argument(
        "--selected-patches",
        nargs="+",
        type=int,
        help=(
            "Search these 1-based manifest patch numbers without filtering "
            "or renumbering the saved patch collection"
        ),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--minimum-retained",
        type=int,
        default=25,
        help="Minimum number of readable patches to keep after quality filtering",
    )
    parser.add_argument("--keyword-count", type=int, default=10)
    parser.add_argument("--per-page", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=240)
    parser.add_argument(
        "--patch-transform",
        choices=("dual", *PATCH_TRANSFORMS),
        default="dual",
    )
    parser.add_argument(
        "--ranking-mode",
        choices=("notebook", "structure_fusion"),
        default="structure_fusion",
    )
    parser.add_argument(
        "--quality-only",
        action="store_true",
        help="Prepare the 50-candidate archive and 25+ retained patches without API search",
    )
    args = parser.parse_args()
    result = run_search(
        args.manifest,
        max_patches=args.max_patches,
        selected_patch_numbers=args.selected_patches,
        top_k=args.top_k,
        keyword_count=args.keyword_count,
        per_page=args.per_page,
        max_candidates=args.max_candidates,
        patch_transform=args.patch_transform,
        ranking_mode=args.ranking_mode,
        quality_only=args.quality_only,
        minimum_retained=args.minimum_retained,
    )
    print(
        json.dumps(
            {
                "searchState": result.get("searchState"),
                "resonanceSets": len(result.get("resonanceSets", [])),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
