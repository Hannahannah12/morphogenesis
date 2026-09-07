# Direction 01 — Material Analysis

This direction reads crystal formation through edge detection, thresholding,
motion history, space-time slicing, and crystal skeleton extraction.

- Notebooks are in `notebooks/`.
- Recorded analysis outputs are in `output/`.
- The exhibition entry is `../00_websites/01_material/`.

## Exhibition pipeline (current)

`runtime/exhibition_pipeline.py` is the live, stateful Material Analysis
processor used by the System Agent. It is an automated transcription of the
tested Notebook cells, not a second analysis method. Each incoming frame
advances four presentation streams:

- Edge / white field with black lines
- Threshold / white field with black structures
- four-row Space-time / white field, black labels, original source colour
- adjacent-frame Motion / lifted black-blue palette

For each captured crystal session the Agent writes H.264 MP4 files to:

`../05_shared_data/exhibition/<ice_crystal_XX>/01_material_analysis/`

The current exhibition flow is:

`capture -> detect formation -> retain 2 s preroll -> process 01/02/03 -> archive later`

The Agent starts Material Analysis and Structural Resonance in parallel.
Diffusion Imagination may attach independently when its page and GPU worker are
available. Jupyter is not part of the exhibition runtime.

## Research / formal pipeline (manual archive tool)

`runtime/material_pipeline.py` contains the earlier manual video runner extracted from
`notebooks/crystal_analysis.ipynb`. It is retained for research reproduction and
comparison, but the Agent does not call it during exhibition.

It preserves the Notebook rules:

- Edge: first-frame background difference, threshold 25, morphology, Canny 10/50
- Threshold: CLAHE 1.0, adaptive Gaussian threshold, block 21, C 5
- Space-time: rows 200, 400, 600, and 800 accumulated into four stacked fields
- Motion: adjacent-frame difference, threshold 15, MAGMA colour map

Example:

```powershell
03_diffusion_imagination\.conda\python.exe `
  01_material_analysis\runtime\material_pipeline.py `
  --source 05_shared_data\input\ice_crystal_03.mp4 `
  --start-seconds 8.8 `
  --analysis-dir 09_experiments\previous_tests\01_material_analysis\output\ice_crystal_03\analysis_formal `
  --exhibition-dir 09_experiments\previous_tests\01_material_analysis\output\ice_crystal_03\exhibition_formal
```

These older outputs remain research assets. Neither output replaces the raw
camera recording or the current centralized Exhibition session.

## Legacy website video export

Older research results can still be converted manually with:

```powershell
03_diffusion_imagination\.conda\python.exe 01_material_analysis\runtime\render_exhibition.py --crystal ice_crystal_01
```

This legacy path is not needed for new Exhibition Pipeline sessions.
