# Morphogenesis — Ice Crystallizing

This surface owns the crystallization process: USB camera capture, recording,
crystal detection, and the recorded-process fallback. Its internal page key
remains `live` so the existing runtime logic does not change.

The separate `current` page shows the unprocessed physical camera image only.

## Run

Run Morphogenesis Agent V0. It serves the project through localhost, owns the
Arduino serial connection, and gives the page its installation state.

From the project root:

```powershell
python 08_system_agent/agent.py
```

Then open `http://localhost:8080/00_websites/live/` in Chrome or Edge.

Open `http://localhost:8080/control/` to connect or disconnect the Arduino Mega
and to operate the installation. The Live page is output-only: Archive remains
visible beside the live camera and MLX90640 thermal output.

Without Arduino, Ambient, Center, and Minimum remain `--.-` and the sensor is
marked as disconnected. Only physical Arduino readings are displayed.

Use **Connect camera** in the Control Room and grant camera permission on first
use. The page prioritizes devices whose names identify them as USB, UVC, or
external cameras. The integrated camera is only used as a fallback.

The Codex embedded preview may not expose physical camera devices. For the
installation, open `http://localhost:8080/00_websites/live/` directly in desktop
Chrome or Edge.

## Arduino thermal format

The Agent reads the binary `MLX4` stream at **115200 baud** from the
`MLX90640_Mega_Stream` firmware. Calibration and complete subpage pairs are
converted into the 32 x 24 thermal frame. The shared status API carries the
Ambient, Center, and Minimum values; `/api/agent/thermal-frame` carries the
display frame. The browser does not open the serial port directly.
