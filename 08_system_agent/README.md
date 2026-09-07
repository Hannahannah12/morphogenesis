# Morphogenesis Agent V0

This local service is the single entry point for the Morphogenesis project. It
serves all exhibition websites, reports installation and connection state,
tracks project milestones, and records state changes.

V0 never sends commands to physical hardware. Arduino safety and actuator
control will be added only after observation mode has been tested.

## Start

Double-click `start_morphogenesis_agent.bat` in the project root, or run:

```powershell
python 08_system_agent/agent.py
```

Then open the private system dashboard:

`http://localhost:8080/control/`

The Control Room reports:

- Agent connection, state, MLX90640 temperatures, and sensor source
- whether Live, Archive, and Generation are ready, open, or visible
- Arduino Mega and camera connection controls
- every project section and its current file count
- notebook JSON integrity
- recent Agent state changes

It also opens each exhibition page, changes the V0 state, and provides a safe
return to `IDLE`.

The audience-facing Live page remains at:

`http://localhost:8080/00_websites/live/`

Use the Control Room to test `IDLE`, `OBSERVING`, `GROWING`, and `ARCHIVING`,
and to connect or disconnect the Arduino Mega. The Live page is output-only.
Ambient, Center, and Minimum remain blank until real MLX90640 frames arrive.

State changes are written to `08_system_agent/logs/agent.jsonl`.

## API

The sensor endpoints used by the Control Room and Live output are:

- `GET /api/agent/thermal-frame` - latest real 32 x 24 MLX90640 frame
- `GET /api/agent/serial-ports` - available Arduino serial ports
- `POST /api/agent/sensor` - connect or disconnect the Mega

- `GET /api/agent/status` — state and hardware safety status
- `GET /api/agent/project` — recognised project sections and file counts
- `GET /api/agent/health` — Control Room system and page health
- `GET /api/agent/logs` — recent Agent events
- `POST /api/agent/command` — change state with `{"state":"GROWING"}`
- `POST /api/agent/client` — receive page heartbeat and Live client details

## Creative AI / Diffusion

The Diffusion page can send one compressed snapshot from the active archive
video or USB camera to OpenAI. The Agent keeps the API key private, asks for an
exhibition-facing `Observation -> Curiosity -> Transformation -> Prompt` trace,
and passes the final prompt to StreamDiffusion. It sends a new snapshot only
when an imagination cycle runs; it does not upload a continuous video stream.

Local credentials live in the ignored file `08_system_agent/openai.env`:

```text
OPENAI_API_KEY=
OPENAI_PROMPT_MODEL=gpt-5.6-sol
```

Restart the Agent after changing this file. An API key also needs available API
billing/quota; a ChatGPT subscription alone does not supply API quota.

The endpoint is `POST /api/agent/imagine-prompt`.

## Safety boundary

`hardwareEnabled` is always `false` in V0. Future actuator commands must pass
through an Arduino safety layer with temperature limits, timeouts, a heartbeat,
and a physical emergency stop.

## Recorded live rehearsal

The Agent can treat an existing shared video as a simulated camera session. It
detects the first persistent formation event and the first fully formed stable
state. It retains two seconds before onset and two seconds after completion,
excluding later dissolution. The Agent publishes one shared playback clock to
the three exhibition pages and renders the Notebook-faithful 01 and 02 outputs
in the background. Direction 03 follows the same retained source as a live
StreamDiffusion session. One synchronized generated loop is saved for every
crystal and becomes the automatic fallback if the live worker or network is
interrupted.

Start the `ice_crystal_03` rehearsal through `POST /api/agent/experiment` with:

```json
{"action": "start", "crystal": "ice_crystal_03"}
```

The current session is available from `GET /api/agent/session`. The public
processing view is `http://localhost:8080/00_websites/backstage/`.

Each completed session is indexed under:

`05_shared_data/exhibition/<ice_crystal_XX>/`

The folder contains the retained formation clip, the four Material Analysis
MP4 files, the Structural Resonance MP4/patch manifest, and `session.json`.
Diffusion remains live by default. Its per-crystal fallback is written to
`03_diffusion_imagination/diffusion_capture.mp4` with the same duration as the
retained formation clip.

This is video-only rehearsal. It does not energise or simulate the Peltier,
pump, stage, Arduino, or temperature.

## Future USB camera capture

Live capture uses the same formation-only boundaries, but its order is
deliberately different from a prerecorded rehearsal:

1. An Arduino report that Peltier cooling has started triggers raw USB-camera
   recording immediately. The Agent observes this signal only; V0 does not
   energise the Peltier.
2. A lightweight online structural tracker stops the raw recording after the
   first stable fully formed state plus a two-second hold. It does not wait for
   melting.
3. The finite raw recording is then reviewed offline with the more precise
   rolling-ROI onset detector. The long cooling lead-in is removed while a
   two-second pre-roll is retained.
4. Material Analysis, Structural Resonance, and Diffusion Imagination all
   receive this same final formation clip.

The raw camera capture is preserved separately. If either detector is
uncertain, the Agent keeps the raw file and reports an error instead of
inventing a trim boundary.
