# Morphogenesis

This workspace is organised around the installation's exhibition surfaces,
three computational directions, and their shared material inputs.

`AGENTS.md` gives the Morphogenesis Project Agent its persistent project map,
working rules, and hardware safety boundary.

## Project structure

- `00_websites` — public-facing and exhibition display websites
- `01_material_analysis` — edge, threshold, space-time, motion, and skeleton studies
- `02_structural_resonance` — DINO feature activation, patch extraction, and structural search
- `03_diffusion_imagination` — live, structure-aware diffusion and machine imagination
- `05_shared_data` — source videos and shared project media
- `06_hardware` — Arduino, Peltier, pump, stepper, and temperature code
- `07_3d_touchdesigner` — retained local 3D and TouchDesigner experiments; not
  included in the final GitHub coursework submission
- `08_system_agent` — project server, connection health, progress, and future orchestration

Earlier Notebook exports and smoke tests are grouped in
`09_experiments/previous_tests/`. Current Agent-generated session assets are
kept separately in `05_shared_data/exhibition/crystal_N/`.

For the clean GitHub coursework package, see `GITHUB_SUBMISSION.md`. The
standalone Archive website is intentionally excluded because it is maintained
in a separate GitHub publication; the complete local installation remains
unchanged.

## Websites

For the complete StreamDiffusion installation, double-click:

`start_morphogenesis_system.bat`

This starts the lightweight Agent on port `8080` and the isolated GPU worker on
port `8091`. They run as separate processes and do not share Python packages.

To run only Morphogenesis Agent V0, which also serves this project through localhost:

```powershell
python 08_system_agent/agent.py
```

You can also double-click `start_morphogenesis_agent.bat`.
This starts the Agent and opens the private Control Room:

`http://localhost:8080/control/`

- Live observation: `http://localhost:8080/00_websites/live/`
- Morphogenesis archive: `http://localhost:8080/00_websites/archive/`
- 01 / Material Analysis: `http://localhost:8080/00_websites/01_material/`
- 02 / Structural Resonance: `http://localhost:8080/00_websites/02_structural/`
- 03 / Diffusion Imagination: `http://localhost:8080/00_websites/03_diffusion/`
- Exhibition processing: `http://localhost:8080/00_websites/backstage/`

Current recorded/live rehearsals are orchestrated by
`08_system_agent/experiment_pipeline.py`. Their browser-ready assets are grouped
per crystal in `05_shared_data/exhibition/crystal_N/`; research notebooks remain
method references and are not launched during exhibition.

The Crystal-driven Generation experiment is archived at
`09_experiments/04_crystal_driven_generation`. Its standalone page remains
available at `http://localhost:8080/00_websites/experiments/04_crystal_driven/`,
but it is not listed or monitored by the System Agent.
