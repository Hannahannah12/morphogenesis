# Direction 02 — Structural Resonance Search

This direction contains the DINO feature-activation workflow, selected crystal
patches, CLIP/HOG searches, image variants, and search-result visualisations.

- `notebooks/structural_resonance_attention.ipynb` extracts activation regions.
- `notebooks/structural_resonance_search.ipynb` performs structural searches.
- Previous Notebook results are retained in
  `../09_experiments/previous_tests/02_structural_resonance/output/`.

## Exhibition pipeline

The Agent does not execute the Jupyter notebooks cell by cell during the
installation. Instead, two runtime workers preserve their tested methods:

- `runtime/exhibition_pipeline.py` runs the DINO
  `vit_base_patch16_224.dino` attention map, stable-frame rule, threshold 120,
  contour-area rule, and patch extraction. It preserves the Notebook's
  brightness-onset and 20-frame stability thresholds, but applies them to the
  first growth event. This prevents a later melt or camera change from being
  mistaken for crystallisation. The patch window begins after the first stable
  growth window and covers the following 100 frames. Landscape sources are
  analysed without a centre-square crop; the two display panels remain
  720×720 and the final browser video is 1440×720.
- `runtime/search_worker.py` runs the Notebook WordNet expansion, live
  iNaturalist and NASA Images API searches, CLIP ViT-B/32 similarity threshold
  0.6, and HOG similarity threshold 0.5.

WordNet data is stored in `runtime/nltk_data` so the exhibition does not depend
on a temporary Jupyter download. Only API candidates selected by CLIP/HOG are
saved into the current crystal output; the webpage never depends on remote image
URLs during playback.

For a captured crystal, the live worker writes:

`../05_shared_data/exhibition/<ice_crystal_XX>/02_structural_resonance/`

This folder contains `attention_blob.mp4`, `patches/`, `search_results/`, and
`manifest.json`.
The Structural Resonance webpage reads that manifest when the Agent marks the
job complete.
