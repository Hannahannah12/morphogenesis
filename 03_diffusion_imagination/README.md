# Direction 03 — Diffusion Imagination

This direction uses StreamDiffusion to place recorded or live crystal imagery
inside a continuous image-to-image feedback process. The camera/video frame is
the material input; SD-Turbo repeatedly interprets it through the current
machine-imagination prompt while preserving temporal continuity between frames.

## Current prototype

- exhibition interface: `00_websites/03_diffusion`
- GPU worker: `runtime/worker.py`, port `8091`
- isolated Python 3.10 environment: `.conda`
- model cache: `models/huggingface`
- real-video verification:
  `../09_experiments/previous_tests/03_diffusion_imagination/output/smoke_test`
- preserved earlier WebGL study: `00_websites/experiments/reaction_diffusion`

The Morphogenesis Agent remains a separate lightweight process on port `8080`.
The browser sends 512×512 source frames to the GPU worker over a local WebSocket
and displays the returned generated frames. The two Python environments do not
share packages.

## Start

Double-click `start_morphogenesis_system.bat` in the project root. It starts
the Morphogenesis Agent, which then manages:

1. the Control Room and all exhibition pages on `127.0.0.1:8080`;
2. the isolated StreamDiffusion worker from `.conda` on `127.0.0.1:8091`,
   after Structural Resonance has released the GPU.

The Agent stops its managed worker before a new analysis run and restarts it
after Direction 02 completes. `start_streamdiffusion_worker.bat` remains only
as a manual diagnostic launcher.

Then open `http://localhost:8080/00_websites/03_diffusion/`. The page explicitly
reports whether the GPU worker is offline, loading, ready, or in error. USB/UVC
cameras are preferred by label; the built-in camera is not silently selected
when no USB/UVC match is found.

## Rebuild the environment

The installed runtime follows the official StreamDiffusion Python 3.10 and CUDA
12.1 baseline. Recreate `.conda`, install
`requirements-streamdiffusion.txt`, then clone the official source:

`https://github.com/cumulo-autumn/StreamDiffusion.git`

into `runtime/StreamDiffusion` and install it editable with `--no-deps`. Model
weights download into `models/huggingface` on the first smoke test.

## Exhibition recording and fallback policy

Direction 03 remains live and does not block the saved 01 and 02 MP4 jobs. Once
the retained formation clip is available, the browser and local GPU worker
record one complete generated loop. The worker calculates the output frame rate
from the number of generated frames so that the resulting MP4 has the same
duration as the retained source clip. The destination is:

`../05_shared_data/exhibition/<ice_crystal_XX>/03_diffusion_imagination/diffusion_capture.mp4`

If the worker, network, or live generation becomes unavailable, the 03 page
loads this MP4 and follows the Agent's shared playback clock. The recorded
fallback is not regenerated when a valid file already exists.
