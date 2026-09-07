# GitHub submission profile

This repository is the clean submission copy of Morphogenesis. The local
workspace remains the complete installation archive; `.gitignore` determines
which parts are intentionally omitted from GitHub.

## Included

- the current exhibition and Control Room websites
- the five-screen Exhibition Mode
- Material Analysis, Structural Resonance, and Diffusion Imagination code
- research notebooks and hardware source files
- the current trimmed exhibition media under `05_shared_data/exhibition`

Large current media and binary production assets are tracked with Git LFS.

## Intentionally omitted

- `00_websites/archive` — already published as a separate GitHub website
- downloaded Python environments, StreamDiffusion checkout, and model weights
- raw source captures under `05_shared_data/input`
- previous tests, invalid runs, stabilisation trials, and patch reprocessing
- exhibition `revisions` and `_preserved_originals`
- exact `*_0_5px.mp4` duplicates where the canonical filename is retained
- the complete `07_3d_touchdesigner` direction, which was not used in the final work
- runtime state, logs, temporary previews, and local credentials

These files remain untouched in the local installation workspace. They are not
deleted; they are only excluded from this repository.

## Before the first push

Install Git LFS, then initialise it for the local user if necessary:

```powershell
git lfs install
```

Check the proposed commit before staging:

```powershell
git status --short
git lfs ls-files
```

Never force-add ignored files. In particular, do not commit
`08_system_agent/openai.env` or any downloaded model directory.
