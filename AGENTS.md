# Morphogenesis Project Agent

## Project identity

Morphogenesis observes crystal formation to investigate relationships between
matter, perception, and computation. The physical installation combines a
Peltier-cooled aluminium plate, thin water film, peristaltic pump, linear stage,
MLX90614 temperature sensing, and macro video observation.

## One Agent, two modes

### Studio mode

- Preserve the numbered top-level project structure.
- Keep all public-facing exhibition pages inside `00_websites`.
- Keep the three research directions separate:
  - `01_material_analysis`
  - `02_structural_resonance`
  - `03_diffusion_imagination`
- Keep the former Crystal-driven Generation direction in
  `09_experiments/04_crystal_driven_generation`, outside the System Agent and
  Control Room, until its role is defined.
- Store shared source media in `05_shared_data`; do not duplicate large input
  videos between directions.
- When moving input, output, notebook, or website files, update every affected
  notebook and website path in the same change.
- Never overwrite raw experiment media. Create a new output location for a new
  experiment or transformation.
- Keep hardware and TouchDesigner support work in their existing numbered
  sections rather than treating them as new research directions.

### Live mode

- Start the local system with `python 08_system_agent/agent.py`.
- The runtime serves all websites and owns the `/api/agent/*` state interface.
- Use `http://localhost:8080/control/` as the private operator Control Room.
- Exhibition pages report a heartbeat so the Control Room can distinguish
  ready files from pages that are actually open.
- Temperature must only be displayed from a connected Arduino sensor. When the
  sensor is absent, display `--.-` and an explicit disconnected state.
- Do not generate or display simulated temperature values.
- V0 is observation only: `hardwareEnabled` must remain `false`.

## Hardware safety boundary

- Do not energise the Peltier, pump, or linear stage merely to test software.
- Do not enable physical actuator commands without an explicit request from the
  user and a verified Arduino-side safety layer.
- Arduino must enforce hard temperature limits, maximum pump and motor runtime,
  communication heartbeat timeout, startup-off defaults, and emergency stop.
- A webpage or language model may request a high-level state but must never be
  the sole layer responsible for actuator safety.

## Current runtime states

- `IDLE` — system at rest; Archive view
- `OBSERVING` — request live observation without physical actuation
- `GROWING` — high-level growth state; no physical sensing is fabricated
- `ARCHIVING` — return to recorded media and prepare experiment records

Add physical control only as a later version after real sensor-only observation
has been tested and logged.
