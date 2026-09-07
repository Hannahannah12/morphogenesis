"""Morphogenesis Agent V0.

Runs the local exhibition website and exposes a small JSON API for installation
state. Hardware output is intentionally disabled in V0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import serial
from serial.tools import list_ports

from mlx90640_sensor import (
    CALIBRATION_WORDS,
    FRAME_WORDS,
    MLX90640Calculator,
    PACKET_CALIBRATION,
    PACKET_FRAME,
    PacketDecoder,
)


AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parent
CONFIG_PATH = AGENT_DIR / "config.json"
LOG_DIR = AGENT_DIR / "logs"
OPENAI_ENV_PATH = AGENT_DIR / "openai.env"
RUNTIME_DIR = AGENT_DIR / "runtime"
EXPERIMENT_STATE_PATH = RUNTIME_DIR / "experiment.json"
EXPERIMENT_PIPELINE_PATH = AGENT_DIR / "experiment_pipeline.py"
EXPERIMENT_PYTHON = PROJECT_ROOT / "03_diffusion_imagination" / ".conda" / "python.exe"
DIFFUSION_DIR = PROJECT_ROOT / "03_diffusion_imagination"
DIFFUSION_PYTHON = DIFFUSION_DIR / ".conda" / "python.exe"
DIFFUSION_WORKER_PATH = DIFFUSION_DIR / "runtime" / "worker.py"
DIFFUSION_HEALTH_URL = "http://127.0.0.1:8091/health"
VALID_STATES = {"IDLE", "OBSERVING", "GROWING", "ARCHIVING"}
ARCHIVE_REPEATS_PER_CRYSTAL = 5
ANALYSIS_REHEARSAL_COUNTDOWN_SECONDS = 8.0
ANALYSIS_REHEARSAL_OUTPUT_SECONDS = 2.8
ANALYSIS_REHEARSAL_PROCESSING_SECONDS = 1.75
ANALYSIS_REHEARSAL_TRANSITION_SECONDS = 28.0
ANALYSIS_REHEARSAL_SHARED_HOLD_SECONDS = 4.0
RESONANCE_REHEARSAL_STEP_SECONDS = 5.0
RESONANCE_REHEARSAL_TERMINAL_STEPS = 5
RESONANCE_REHEARSAL_ANIMATION_SECONDS = 65.0
DIFFUSION_REHEARSAL_STEP_SECONDS = 5.0
DIFFUSION_REHEARSAL_TERMINAL_STEPS = 4
DIFFUSION_REHEARSAL_SOURCE_SECONDS = 180.0
REHEARSAL_SOURCE_SECONDS = 20.0
REHEARSAL_CRYSTALS = tuple(
    f"ice_crystal_{index:02d}" for index in range(1, 6)
)
ANALYSIS_REHEARSAL_OUTPUTS = (
    ("edge", "EDGE EXTRACTION", "01_material_analysis/edge.mp4"),
    ("motion", "MOTION FIELD", "01_material_analysis/motion.mp4"),
    ("threshold", "THRESHOLD SEGMENTATION", "01_material_analysis/threshold.mp4"),
)


def load_local_openai_env() -> None:
    """Load the two supported local values without exposing them to the webpage."""
    if not OPENAI_ENV_PATH.exists():
        return
    for raw_line in OPENAI_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"OPENAI_API_KEY", "OPENAI_PROMPT_MODEL"} and key not in os.environ:
            os.environ[key] = value.strip()


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


class MorphogenesisAgent:
    """Thread-safe V0 state machine and project health observer."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.state = "IDLE"
        self.started_at = time.time()
        self.updated_at = time.time()
        self.clients: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOG_DIR / "agent.jsonl"
        self.notebook_health = self._check_notebooks()
        self.project_health = self._build_project_snapshot()
        self.openai_model = os.environ.get("OPENAI_PROMPT_MODEL", "gpt-5.6-sol")
        self.openai_configured = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        self.openai_last_success: str | None = None
        self.openai_last_error: str | None = None
        self.creative_history: list[dict[str, str]] = []
        self.creative_cycle = 0
        self.formation_state = "unknown"
        self.formation_updated_at: str | None = None
        self.manual_cooling_active = False
        self.manual_cooling_started_at: str | None = None
        self.live_capture: dict[str, Any] = {
            "state": "idle",
            "crystal": None,
            "message": "No live capture",
        }
        self.serial_connection: serial.Serial | None = None
        self.serial_port: str | None = None
        self.sensor_preferred_port: str | None = None
        self.sensor_auto_connect_enabled = True
        self.sensor_connected = False
        self.sensor_error: str | None = None
        self.sensor_last_reading_at: str | None = None
        self.sensor_last_reading_epoch: float | None = None
        self.ambient_temperature: float | None = None
        self.object_temperature: float | None = None
        self.minimum_temperature: float | None = None
        self.maximum_temperature: float | None = None
        self.thermal_temperatures: list[float] = []
        self.thermal_frame_sequence = 0
        self.serial_stop_event = threading.Event()
        self.serial_thread: threading.Thread | None = None
        self.experiment_process: subprocess.Popen[str] | None = None
        self.archive_cycle_started_at = time.time()
        self.archive_cycle_active = True
        self.analysis_rehearsal_started_at = 0.0
        self.analysis_rehearsal_active = False
        self.diffusion_process: subprocess.Popen[str] | None = None
        self.diffusion_health: dict[str, Any] = {
            "status": "offline",
            "ready": False,
        }
        self.diffusion_last_error: str | None = None
        self.diffusion_failure_count = 0
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self._write_log("agent_started", {"state": self.state})
        self.diffusion_monitor = threading.Thread(
            target=self._diffusion_monitor_loop,
            name="morphogenesis-diffusion-monitor",
            daemon=True,
        )
        self.diffusion_monitor.start()
        available_ports = self.available_serial_ports()
        if len(available_ports) == 1:
            try:
                self.connect_sensor(available_ports[0]["device"])
            except (ValueError, RuntimeError):
                pass
        self.sensor_reconnect_thread = threading.Thread(
            target=self._sensor_reconnect_loop,
            name="morphogenesis-temperature-reconnect",
            daemon=True,
        )
        self.sensor_reconnect_thread.start()

    def _write_log(self, event: str, data: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def set_state(self, requested_state: str) -> dict[str, Any]:
        state = requested_state.strip().upper()
        if state not in VALID_STATES:
            raise ValueError(f"Unknown state: {requested_state}")
        with self.lock:
            previous = self.state
            self.state = state
            self.updated_at = time.time()
        if state != previous:
            self._write_log("state_changed", {"from": previous, "to": state})
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "agent": "Morphogenesis Agent",
                "version": "0.1.0",
                "connected": True,
                "state": self.state,
                "hardwareEnabled": False,
                "sensorSource": "mlx90640" if self.sensor_connected else "disconnected",
                "ambientTemperature": self.ambient_temperature if self.sensor_connected else None,
                "objectTemperature": self.object_temperature if self.sensor_connected else None,
                "centerTemperature": self.object_temperature if self.sensor_connected else None,
                "minimumTemperature": self.minimum_temperature if self.sensor_connected else None,
                "maximumTemperature": self.maximum_temperature if self.sensor_connected else None,
                "sensor": {
                    "connected": self.sensor_connected,
                    "portOpen": bool(self.serial_connection and self.serial_connection.is_open),
                    "model": "MLX90640",
                    "port": self.serial_port,
                    "error": self.sensor_error,
                    "lastReadingAt": self.sensor_last_reading_at,
                },
                "manualCooling": {
                    "active": self.manual_cooling_active,
                    "startedAt": self.manual_cooling_started_at,
                    "controlMode": "manual-peltier-live-recording",
                    "experimentId": self.live_capture.get("crystal"),
                    "recording": dict(self.live_capture),
                },
                "formationState": self.formation_state,
                "formationSource": "vision" if self.formation_updated_at else "unavailable",
                "formationUpdatedAt": self.formation_updated_at,
                "updatedAt": datetime.fromtimestamp(
                    self.updated_at, timezone.utc
                ).isoformat(),
                "uptimeSeconds": round(time.time() - self.started_at, 1),
            }

    def set_manual_cooling(self, action: str) -> dict[str, Any]:
        normalized = action.strip().lower()
        if normalized not in {"start", "stop"}:
            raise ValueError(f"Unknown manual cooling action: {action}")
        active = normalized == "start"
        if active:
            with self.lock:
                live = dict(self.clients.get("live") or {})
            details = live.get("details") or {}
            recently_seen = (
                live.get("active")
                and time.time() - float(live.get("lastSeenEpoch") or 0) < 10
            )
            if not recently_seen:
                raise RuntimeError(
                    "Live page is not connected. Open the Live page before starting cooling."
                )
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            changed = self.manual_cooling_active != active
            self.manual_cooling_active = active
            if active:
                self.archive_cycle_active = False
                if changed or self.manual_cooling_started_at is None:
                    self.manual_cooling_started_at = now
                    crystal = self._next_crystal_name()
                    self.live_capture = {
                        "state": "waiting_recorder",
                        "crystal": crystal,
                        "message": "Cooling started / waiting for camera recorder",
                        "startedAt": now,
                        "formationDetectedAt": None,
                    }
                    self.state = "GROWING"
                    self._write_live_capture_state()
            else:
                self.manual_cooling_started_at = None
                if self.live_capture.get("state") in {
                    "waiting_recorder", "recording", "formation_detected"
                }:
                    self.live_capture["state"] = "stop_requested"
                    self.live_capture["message"] = "Cooling stopped / finalizing recording"
                self.state = "ARCHIVING"
            self.updated_at = time.time()
        if changed:
            self._write_log(
                "manual_cooling_started" if active else "manual_cooling_stopped",
                {"controlMode": "manual-record-only", "hardwareEnabled": False},
            )
        return self.snapshot()

    def _next_crystal_name(self) -> str:
        numbers: list[int] = []
        for root in (
            PROJECT_ROOT / "05_shared_data" / "input",
            PROJECT_ROOT / "05_shared_data" / "exhibition",
        ):
            if not root.exists():
                continue
            for path in root.glob("ice_crystal_*"):
                match = re.match(r"ice_crystal_(\d+)", path.stem)
                if match:
                    numbers.append(int(match.group(1)))
        return f"ice_crystal_{max(numbers, default=0) + 1:02d}"

    def _write_live_capture_state(self) -> None:
        crystal = str(self.live_capture.get("crystal") or "")
        if not crystal:
            return
        payload = {
            "id": f"{crystal}-live-capture",
            "crystal": crystal,
            "kind": "live_capture",
            "phase": "capturing",
            "createdAt": self.live_capture.get("startedAt"),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "playback": None,
            "detection": {
                "state": "watching",
                "onsetSeconds": None,
                "method": "browser ROI persistent visual change",
            },
            "jobs": {
                "capture": {
                    "state": "running",
                    "progress": 0,
                    "message": self.live_capture.get("message"),
                },
                "detection": {
                    "state": "running",
                    "progress": 0,
                    "message": "Watching live surface for crystallization",
                },
            },
            "events": [],
        }
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        EXPERIMENT_STATE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def update_live_capture(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "")).strip().lower()
        crystal = str(payload.get("crystal", "")).strip()
        with self.lock:
            expected = str(self.live_capture.get("crystal") or "")
            if not expected or crystal != expected:
                raise ValueError("Live capture does not match the active experiment")
            if action == "recording":
                self.live_capture["state"] = "recording"
                self.live_capture["message"] = "Camera recording / watching for formation"
            elif action == "formation_detected":
                self.live_capture["state"] = "formation_detected"
                self.live_capture["formationDetectedAt"] = datetime.now(timezone.utc).isoformat()
                self.live_capture["message"] = "Formation detected / recording final 2 seconds"
            elif action == "error":
                self.live_capture["state"] = "error"
                self.live_capture["message"] = str(payload.get("message", "Recording failed"))[:240]
            else:
                raise ValueError(f"Unknown live capture action: {action}")
            self.updated_at = time.time()
        self._write_log("live_capture_status", {"crystal": crystal, "status": action})
        return self.snapshot()

    def finish_live_recording(self, crystal: str, source: Path) -> dict[str, Any]:
        with self.lock:
            expected = str(self.live_capture.get("crystal") or "")
            if crystal != expected:
                raise ValueError("Uploaded recording does not match the active experiment")
            self.live_capture["state"] = "processing"
            self.live_capture["message"] = "Recording saved / processing three directions"
            self.manual_cooling_active = False
            self.manual_cooling_started_at = None
            self.state = "ARCHIVING"
            self.updated_at = time.time()
        if not EXPERIMENT_PYTHON.exists():
            raise RuntimeError("The project Python environment is unavailable")
        with self.lock:
            if self.experiment_process and self.experiment_process.poll() is None:
                raise RuntimeError("An experiment is already running")
            log_out = (LOG_DIR / "experiment.stdout.log").open("w", encoding="utf-8")
            log_err = (LOG_DIR / "experiment.stderr.log").open("w", encoding="utf-8")
            self.experiment_process = subprocess.Popen(
                [
                    str(EXPERIMENT_PYTHON),
                    str(EXPERIMENT_PIPELINE_PATH),
                    "--crystal", crystal,
                    "--state", str(EXPERIMENT_STATE_PATH),
                    "--source", str(source),
                    "--kind", "live_capture",
                    "--showcase-seconds", "300",
                ],
                cwd=str(PROJECT_ROOT),
                stdout=log_out,
                stderr=log_err,
                text=True,
            )
        self._write_log("live_recording_saved", {
            "crystal": crystal,
            "path": str(source.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        })
        return self.snapshot()

    @staticmethod
    def available_serial_ports() -> list[dict[str, str]]:
        return [
            {
                "device": port.device,
                "description": port.description or "Serial device",
            }
            for port in list_ports.comports()
        ]

    def _sensor_reader_loop(self) -> None:
        connection = self.serial_connection
        decoder = PacketDecoder()
        calculator = MLX90640Calculator(emissivity=0.95)
        next_calibration_request = time.monotonic() + 1.8
        last_valid_frame = time.monotonic()
        connected_logged = False
        try:
            while (
                connection
                and connection.is_open
                and not self.serial_stop_event.is_set()
            ):
                waiting = connection.in_waiting
                chunk = connection.read(min(max(waiting, 1), 4096))
                monotonic_now = time.monotonic()
                if not calculator.calibrated and monotonic_now >= next_calibration_request:
                    connection.write(b"C")
                    next_calibration_request = monotonic_now + 2.0

                for packet_type, sequence, words in decoder.feed(chunk):
                    if packet_type == PACKET_CALIBRATION and len(words) == CALIBRATION_WORDS:
                        calculator.set_calibration(words)
                        with self.lock:
                            if connection is self.serial_connection:
                                self.sensor_error = "Calibration received / waiting for complete thermal frame"
                        continue
                    if packet_type != PACKET_FRAME or len(words) != FRAME_WORDS:
                        continue
                    thermal = calculator.add_frame(sequence, words)
                    if thermal is None:
                        continue
                    captured_at = datetime.now(timezone.utc).isoformat()
                    captured_epoch = time.time()
                    last_valid_frame = monotonic_now
                    with self.lock:
                        if connection is not self.serial_connection:
                            return
                        self.ambient_temperature = thermal.ambient_temperature
                        self.object_temperature = thermal.center_temperature
                        self.minimum_temperature = thermal.minimum_temperature
                        self.maximum_temperature = thermal.maximum_temperature
                        self.thermal_temperatures = thermal.temperatures
                        self.thermal_frame_sequence += 1
                        self.sensor_connected = True
                        self.sensor_error = None
                        self.sensor_last_reading_at = captured_at
                        self.sensor_last_reading_epoch = captured_epoch
                        self.updated_at = captured_epoch
                    if not connected_logged:
                        self._write_log(
                            "sensor_connected",
                            {"port": self.serial_port, "baudRate": 115200, "model": "MLX90640"},
                        )
                        connected_logged = True

                if monotonic_now - last_valid_frame > 3.5:
                    with self.lock:
                        if connection is self.serial_connection:
                            self.sensor_connected = False
                            self.ambient_temperature = None
                            self.object_temperature = None
                            self.minimum_temperature = None
                            self.maximum_temperature = None
                            self.thermal_temperatures = []
                            if calculator.calibrated:
                                self.sensor_error = "MLX90640 thermal frames are stale"
        except (OSError, ValueError, serial.SerialException) as error:
            with self.lock:
                if connection is self.serial_connection:
                    self.sensor_connected = False
                    self.sensor_error = str(error)
                    self.ambient_temperature = None
                    self.object_temperature = None
                    self.minimum_temperature = None
                    self.maximum_temperature = None
                    self.thermal_temperatures = []
            self._write_log("sensor_disconnected", {"port": self.serial_port})
        finally:
            try:
                if connection and connection.is_open:
                    connection.close()
            except (OSError, serial.SerialException):
                pass
            with self.lock:
                if connection is self.serial_connection:
                    self.serial_connection = None

    def _sensor_reconnect_loop(self) -> None:
        """Recover a transient USB/serial loss without fabricating readings."""
        while not self.stop_event.wait(5.0):
            with self.lock:
                enabled = self.sensor_auto_connect_enabled
                connection = self.serial_connection
                reader = self.serial_thread
                preferred = self.sensor_preferred_port
            if not enabled:
                continue
            if connection and connection.is_open and reader and reader.is_alive():
                continue
            ports = self.available_serial_ports()
            devices = [item["device"] for item in ports]
            candidate = preferred if preferred in devices else (
                devices[0] if len(devices) == 1 else None
            )
            if not candidate:
                continue
            try:
                self.connect_sensor(candidate)
                self._write_log("sensor_reconnect_started", {"port": candidate})
            except (ValueError, RuntimeError, OSError, serial.SerialException):
                continue

    def connect_sensor(self, requested_port: str) -> dict[str, Any]:
        port = requested_port.strip().upper()
        available = {item["device"].upper() for item in self.available_serial_ports()}
        if port not in available:
            raise ValueError(f"Serial port is not available: {requested_port}")
        self.disconnect_sensor(log_event=False)
        try:
            connection = serial.Serial(port, 115200, timeout=0.2, write_timeout=1)
        except serial.SerialException as error:
            with self.lock:
                self.sensor_error = str(error)
            raise RuntimeError(f"Could not open {port}: {error}") from error
        self.serial_stop_event.clear()
        with self.lock:
            self.serial_connection = connection
            self.serial_port = port
            self.sensor_preferred_port = port
            self.sensor_connected = False
            self.sensor_error = "Waiting for MLX90640 calibration"
            self.ambient_temperature = None
            self.object_temperature = None
            self.minimum_temperature = None
            self.maximum_temperature = None
            self.thermal_temperatures = []
            self.sensor_last_reading_at = None
            self.sensor_last_reading_epoch = None
            self.updated_at = time.time()
        self.serial_thread = threading.Thread(
            target=self._sensor_reader_loop,
            name="morphogenesis-temperature-sensor",
            daemon=True,
        )
        self.serial_thread.start()
        self._write_log("sensor_port_opened", {"port": port, "baudRate": 115200})
        return self.snapshot()

    def disconnect_sensor(self, log_event: bool = True) -> dict[str, Any]:
        previous_port = self.serial_port
        self.serial_stop_event.set()
        connection = self.serial_connection
        if connection and connection.is_open:
            connection.close()
        with self.lock:
            self.serial_connection = None
            self.serial_port = None
            self.sensor_connected = False
            self.sensor_error = None
            self.ambient_temperature = None
            self.object_temperature = None
            self.minimum_temperature = None
            self.maximum_temperature = None
            self.thermal_temperatures = []
            self.sensor_last_reading_at = None
            self.sensor_last_reading_epoch = None
            self.updated_at = time.time()
        if log_event and previous_port:
            self._write_log("sensor_disconnected", {"port": previous_port})
        return self.snapshot()

    def set_sensor_connection(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "")).strip().lower()
        if action == "connect":
            with self.lock:
                self.sensor_auto_connect_enabled = True
            return self.connect_sensor(str(payload.get("port", "")))
        if action == "disconnect":
            with self.lock:
                self.sensor_auto_connect_enabled = False
            return self.disconnect_sensor()
        raise ValueError(f"Unknown sensor action: {action}")

    def thermal_snapshot(self) -> dict[str, Any]:
        """Return the latest real MLX90640 frame without bloating shared status."""
        with self.lock:
            connected = bool(self.sensor_connected and self.thermal_temperatures)
            return {
                "connected": connected,
                "source": "mlx90640" if connected else "disconnected",
                "port": self.serial_port,
                "width": 32,
                "height": 24,
                "sequence": self.thermal_frame_sequence,
                "capturedAt": self.sensor_last_reading_at if connected else None,
                "ambientTemperature": round(self.ambient_temperature, 2)
                if connected and self.ambient_temperature is not None else None,
                "centerTemperature": round(self.object_temperature, 2)
                if connected and self.object_temperature is not None else None,
                "minimumTemperature": round(self.minimum_temperature, 2)
                if connected and self.minimum_temperature is not None else None,
                "maximumTemperature": round(self.maximum_temperature, 2)
                if connected and self.maximum_temperature is not None else None,
                "temperatures": [round(value, 2) for value in self.thermal_temperatures]
                if connected else [],
                "error": self.sensor_error,
            }

    def _check_notebooks(self) -> dict[str, Any]:
        valid: list[str] = []
        invalid: list[dict[str, str]] = []
        notebook_paths: list[Path] = []
        excluded = {".conda", ".git", "__pycache__", "models", "StreamDiffusion"}
        for root, directories, files in os.walk(PROJECT_ROOT):
            directories[:] = [name for name in directories if name not in excluded]
            notebook_paths.extend(Path(root) / name for name in files if name.endswith(".ipynb"))
        for path in notebook_paths:
            relative = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            try:
                with path.open("r", encoding="utf-8") as notebook_file:
                    json.load(notebook_file)
                valid.append(relative)
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                invalid.append({"path": relative, "error": str(error)})
        return {
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "total": len(valid) + len(invalid),
            "valid": len(valid),
            "invalid": invalid,
        }

    def update_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        page = str(payload.get("page", "")).strip()
        if page not in self.config["websitePages"]:
            raise ValueError(f"Unknown project page: {page}")
        now = time.time()
        client = {
            "page": page,
            "active": bool(payload.get("active", True)),
            "visible": bool(payload.get("visible", False)),
            "title": str(payload.get("title", ""))[:160],
            "url": str(payload.get("url", ""))[:500],
            "details": payload.get("details", {}),
            "lastSeenEpoch": now,
            "lastSeen": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        }
        with self.lock:
            self.clients[page] = client
        return client

    def _probe_diffusion_worker(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(DIFFUSION_HEALTH_URL, timeout=1.2) as response:
                health = json.loads(response.read().decode("utf-8"))
            health["reachable"] = True
            return health
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            return {
                "status": "offline",
                "ready": False,
                "reachable": False,
                "error": str(error),
            }

    def _session_needs_diffusion(self) -> bool:
        with self.lock:
            experiment_process = self.experiment_process
            analysis_rehearsal_active = self.analysis_rehearsal_active
        if analysis_rehearsal_active:
            return True
        if experiment_process and experiment_process.poll() is None:
            return False
        return False

    def _start_diffusion_worker(self) -> None:
        with self.lock:
            process = self.diffusion_process
        if process and process.poll() is None:
            return
        if self.diffusion_health.get("reachable"):
            return
        if not DIFFUSION_PYTHON.exists() or not DIFFUSION_WORKER_PATH.exists():
            self.diffusion_last_error = "StreamDiffusion runtime or Python environment is missing"
            return
        environment = os.environ.copy()
        environment["HF_HOME"] = str(DIFFUSION_DIR / "models" / "huggingface")
        environment["HF_HUB_OFFLINE"] = "1"
        environment["TRANSFORMERS_OFFLINE"] = "1"
        stdout_path = LOG_DIR / "diffusion.stdout.log"
        stderr_path = LOG_DIR / "diffusion.stderr.log"
        stdout_log = stdout_path.open("w", encoding="utf-8")
        stderr_log = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [
                    str(DIFFUSION_PYTHON),
                    str(DIFFUSION_WORKER_PATH),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8091",
                ],
                cwd=str(PROJECT_ROOT),
                env=environment,
                stdout=stdout_log,
                stderr=stderr_log,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            stdout_log.close()
            stderr_log.close()
        with self.lock:
            self.diffusion_process = process
            self.diffusion_health = {
                "status": "starting",
                "ready": False,
                "reachable": False,
            }
        self.diffusion_last_error = None
        self._write_log(
            "diffusion_worker_started",
            {"pid": process.pid, "port": 8091},
        )

    def _stop_diffusion_worker(self) -> None:
        with self.lock:
            process = self.diffusion_process
            self.diffusion_process = None
            health = dict(self.diffusion_health)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        elif (
            health.get("service") == "Morphogenesis StreamDiffusion"
            and health.get("pid")
        ):
            try:
                os.kill(int(health["pid"]), signal.SIGTERM)
            except (OSError, TypeError, ValueError):
                pass
        else:
            return
        with self.lock:
            self.diffusion_health = {
                "status": "offline",
                "ready": False,
                "reachable": False,
            }
        self._write_log("diffusion_worker_stopped", {"reason": "agent lifecycle"})

    def _diffusion_monitor_loop(self) -> None:
        restart_after = 0.0
        previous_status = ""
        while not self.stop_event.wait(2.0):
            health = self._probe_diffusion_worker()
            status = str(health.get("status") or "offline")
            with self.lock:
                process = self.diffusion_process
                self.diffusion_health = health
            if process and process.poll() is not None:
                self.diffusion_failure_count += 1
                self.diffusion_last_error = (
                    f"StreamDiffusion worker exited with code {process.returncode}"
                )
                with self.lock:
                    self.diffusion_process = None
                retry_delay = min(
                    60.0,
                    5.0 * (2 ** min(self.diffusion_failure_count - 1, 4)),
                )
                restart_after = time.time() + retry_delay
                self._write_log(
                    "diffusion_worker_exited",
                    {
                        "exitCode": process.returncode,
                        "retryInSeconds": retry_delay,
                    },
                )
            if health.get("ready"):
                self.diffusion_failure_count = 0
            if status != previous_status:
                self._write_log(
                    "diffusion_worker_status",
                    {
                        "status": status,
                        "ready": bool(health.get("ready")),
                    },
                )
                previous_status = status
            if (
                not health.get("reachable")
                and time.time() >= restart_after
                and self._session_needs_diffusion()
            ):
                try:
                    self._start_diffusion_worker()
                    restart_after = time.time() + 10.0
                except (OSError, subprocess.SubprocessError) as error:
                    self.diffusion_last_error = str(error)
                    restart_after = time.time() + 10.0
                    self._write_log(
                        "diffusion_worker_start_failed",
                        {"error": str(error)},
                    )

    def _merge_diffusion_runtime(self, session: dict[str, Any]) -> None:
        jobs = session.get("jobs") or {}
        diffusion = jobs.get("diffusion")
        if not isinstance(diffusion, dict) or not session.get("id"):
            return
        now = time.time()
        with self.lock:
            health = dict(self.diffusion_health)
            client = dict(self.clients.get("diffusion") or {})
        page_open = bool(
            client
            and client.get("active")
            and now - float(client.get("lastSeenEpoch") or 0) < 10
        )
        details = client.get("details") or {} if page_open else {}
        if details.get("sessionId") != session.get("id"):
            details = {}
            page_open = False
        recording_url = str(
            diffusion.get("recordingUrl")
            or diffusion.get("optionalRecordingUrl")
            or ""
        )
        recording_path = (
            PROJECT_ROOT / recording_url.lstrip("/")
            if recording_url.startswith("/")
            else None
        )
        backup_ready = bool(
            recording_path
            and recording_path.is_file()
            and recording_path.stat().st_size > 0
        )
        recording_metadata: dict[str, Any] = {}
        if backup_ready and recording_path is not None:
            metadata_path = recording_path.parent / "recording.json"
            try:
                recording_metadata = json.loads(
                    metadata_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                recording_metadata = {}
        if details.get("backupActive"):
            state = "complete"
            progress = 1.0
            message = "Synchronized recorded Diffusion fallback is playing"
        elif details.get("hasGeneratedFrame"):
            state = "complete"
            progress = 1.0
            fps = details.get("fps")
            message = (
                f"Live StreamDiffusion connected / {float(fps):.1f} fps"
                if fps is not None
                else "Live StreamDiffusion connected / first frame received"
            )
            if backup_ready:
                message += " / offline backup ready"
        elif (
            health.get("ready")
            and int(health.get("clients") or 0) > 0
            and int(health.get("frames") or 0) > 0
        ):
            # The GPU worker is also an authoritative runtime signal. Embedded
            # exhibition iframes can be throttled by the browser and briefly
            # miss their page heartbeat even while frames are flowing.
            state = "complete"
            progress = 1.0
            fps = health.get("fps")
            message = (
                f"Live StreamDiffusion connected / {float(fps):.1f} fps"
                if fps is not None
                else "Live StreamDiffusion connected / generated frames received"
            )
        elif details.get("streaming"):
            state = "running"
            progress = 0.78
            message = "StreamDiffusion connected / priming generated frames"
        elif page_open and details.get("workerConnected"):
            state = "ready"
            progress = 0.52
            message = "GPU worker and Diffusion page connected / starting stream"
        elif health.get("ready"):
            if backup_ready:
                state = "complete"
                progress = 1.0
                message = "GPU worker ready / synchronized backup ready"
            else:
                state = "waiting_page"
                progress = 0.35
                message = "GPU worker ready / waiting for the 03 exhibition page"
        elif health.get("reachable"):
            state = "starting"
            progress = 0.18
            message = "Loading SD-Turbo into the GPU"
        else:
            if backup_ready:
                state = "complete"
                progress = 1.0
                message = "GPU worker offline / synchronized backup ready"
            else:
                state = "starting"
                progress = 0.08
                message = self.diffusion_last_error or "Agent is starting the StreamDiffusion GPU worker"
        worker_page_connected = bool(
            int(health.get("clients") or 0) > 0
            and int(health.get("frames") or 0) > 0
        )
        diffusion.update(
            {
                "state": state,
                "progress": progress,
                "message": message,
                "workerStatus": health.get("status", "offline"),
                "pageConnected": page_open or worker_page_connected,
                "streaming": bool(
                    details.get("streaming") or worker_page_connected
                ),
                "fps": details.get("fps") or health.get("fps"),
                "backupReady": backup_ready,
                "backupActive": bool(details.get("backupActive")),
                "recordingBackup": bool(details.get("recordingBackup")),
                "recordingUrl": recording_url or None,
                "recordingMetadata": recording_metadata,
            }
        )

    def health_snapshot(self) -> dict[str, Any]:
        now = time.time()
        pages: list[dict[str, Any]] = []
        with self.lock:
            clients = dict(self.clients)
        for key, page_config in self.config["websitePages"].items():
            client = clients.get(key)
            is_open = bool(
                client
                and client["active"]
                and now - float(client["lastSeenEpoch"]) < 10
            )
            pages.append(
                {
                    "key": key,
                    "label": page_config["label"],
                    "url": page_config["url"],
                    "ready": (PROJECT_ROOT / page_config["file"]).exists(),
                    "open": is_open,
                    "visible": bool(client and client["visible"] and is_open),
                    "lastSeen": client["lastSeen"] if client else None,
                    "details": client["details"] if client and is_open else {},
                }
            )
        live_page = next(page for page in pages if page["key"] == "live")
        live_details = live_page["details"] if live_page["open"] else {}
        arduino_connected = self.sensor_connected
        camera_connected = bool(live_details.get("cameraActive", False))

        def numeric_temperature(value: Any) -> float | None:
            try:
                number = float(value)
                return number if -100 <= number <= 150 else None
            except (TypeError, ValueError):
                return None

        return {
            "agent": self.snapshot(),
            "connections": {
                "agent": True,
                "livePage": live_page["open"],
                "arduino": arduino_connected,
                "camera": camera_connected,
                "creativeAI": self.openai_configured,
                "streamDiffusion": bool(self.diffusion_health.get("ready")),
            },
            "streamDiffusion": {
                **self.diffusion_health,
                "managed": bool(
                    self.diffusion_process
                    and self.diffusion_process.poll() is None
                ),
                "lastError": self.diffusion_last_error,
            },
            "creativeAI": {
                "configured": self.openai_configured,
                "model": self.openai_model,
                "lastSuccess": self.openai_last_success,
                "lastError": self.openai_last_error,
            },
            "materialState": {
                "formationState": self.formation_state,
                "source": "vision" if self.formation_updated_at else "unavailable",
                "updatedAt": self.formation_updated_at,
            },
            "sensing": {
                "connected": arduino_connected,
                "source": "mlx90640" if arduino_connected else "disconnected",
                "ambientTemperature": numeric_temperature(
                    self.ambient_temperature
                ) if arduino_connected else None,
                "objectTemperature": numeric_temperature(
                    self.object_temperature
                ) if arduino_connected else None,
                "centerTemperature": numeric_temperature(
                    self.object_temperature
                ) if arduino_connected else None,
                "minimumTemperature": numeric_temperature(
                    self.minimum_temperature
                ) if arduino_connected else None,
                "maximumTemperature": numeric_temperature(
                    self.maximum_temperature
                ) if arduino_connected else None,
                "portOpen": bool(self.serial_connection and self.serial_connection.is_open),
                "model": "MLX90640",
                "port": self.serial_port,
                "lastReadingAt": self.sensor_last_reading_at,
                "error": self.sensor_error,
            },
            "pages": pages,
            "notebooks": self.notebook_health,
            "project": self.project_snapshot(),
            "progress": self.progress_snapshot(),
        }

    @staticmethod
    def _response_text(response: dict[str, Any]) -> str:
        pieces: list[str] = []
        for item in response.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    pieces.append(str(content["text"]))
        return "".join(pieces).strip()

    def imagine_prompt(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OpenAI API is not configured")

        image = str(payload.get("image", ""))
        if not image.startswith("data:image/jpeg;base64,") or len(image) > 900_000:
            raise ValueError("A valid JPEG snapshot is required")
        previous = payload.get("previous") or {}
        previous_prompt = str(previous.get("prompt", ""))[:1200]
        source = str(payload.get("source", "crystal stream"))[:120]
        crystal = str(payload.get("crystal", "unlabelled crystal"))[:120]
        observation_id = str(payload.get("observationId", "independent observation"))[:180]
        sequence = str(
            payload.get("sequence", "enlarged-high-contrast-formation-frame")
        )[:120]

        association_fields = [
            "THREE-DIMENSIONAL WATER: braided rivers, tidal channels, estuaries, submerged ridges, currents, reflective pools and cascading water relief",
            "LIVING VOLUME: cells, membranes, coral sheets, plankton blooms, shell chambers, seed pods, translucent colonies, nerve-like networks and folded organic surfaces",
            "GLACIAL TERRAIN: crevasse fields, ice shelves, frozen caves, glacier valleys, pressure ridges and translucent ice topography",
            "EARTH RELIEF: mountain ridges, canyons, deltas, erosion basins, coastal escarpments, mineral strata and layered sediment",
            "SCULPTURAL MATTER: cast glass, porcelain relief, folded textile, carved resin, layered paper, woven metal and spatial painting",
            "ATMOSPHERIC VOLUME: cloud terraces, fog banks, rain bands, storm fronts, suspended droplets and illuminated particulate depth",
            "MINERAL ARCHITECTURE: crystal vaults, ceramic caverns, stepped terraces, translucent walls, carved chambers and reflective mineral passages",
            "VOLCANIC MATERIAL: cooled lava folds, obsidian shelves, porous basalt, molten glass channels, ash relief and heat-shaped rock membranes",
        ]
        composition_directives = [
            "broad basin with several converging channels",
            "layered foreground shelf opening into a deep recess",
            "asymmetric cavern with one dominant void",
            "dispersed islands of relief separated by quiet space",
            "folded sheet rising into overlapping planes",
            "suspended volume with foreground, middle depth and distant field",
            "stepped topography with alternating plateaus and cuts",
            "oblique flow crossing the frame without a central focal point",
        ]
        with self.lock:
            recent_history = list(self.creative_history[-6:])
            association_field = association_fields[
                self.creative_cycle % len(association_fields)
            ]
            composition_directive = composition_directives[
                self.creative_cycle % len(composition_directives)
            ]
        recent_themes = "; ".join(
            item.get("transformation", "") for item in recent_history
        ) or "none yet"

        instruction = """You are the speculative imagination engine inside the artwork Morphogenesis. The physical source is always a thin film of water freezing and crystallising into ice on a Peltier-cooled aluminium plate, observed through a macro camera. This is a material fact, not an inference: never describe the source as an unknown texture, stone, tissue, landscape, or generic pattern. You receive one automatically selected, enlarged, high-contrast frame from that water-crystallisation process. For recorded material, the system selects a representative frame near completed formation rather than the first video frame. For a live camera, it supplies the latest observation. Imagination must begin from the visible behaviour of water becoming ice rather than run at maximum intensity all the time.

Every request represents its own observation of a particular water-to-ice crystallisation run. Different crystal identifiers are different experiments with different growth geometry. Inspect the supplied frame afresh: never transfer branching, density, direction, spatial anchors or conclusions from an earlier crystal into the current one. Previous traces exist only to prevent repetitive artistic themes, never as visual evidence for the current observation.

First classify the visible formation state in this selected frame:
- preformation: a mostly smooth plate or water film with no clear branching, faceting, ridged aggregation, organised growth, or sustained texture field.
- emerging: organised structure is visible but remains sparse, localised, weak, or ambiguous.
- active: clear organised branching, ridges, facets, fronts, repeated texture, or dense growth are visible.

If preformation, set imaginationMode to hold. Stay factual and quiet. Do not use the association field, do not invent a world, and set prompt to exactly: "Hold current diffusion; visible formation has not begun."
If emerging, set imaginationMode to subtle. Make a restrained, nearby association with limited transformation and no monumental or cosmic claims.
If active, set imaginationMode to expansive and follow the association-field instructions below. Expansive may transform the crystal into a new three-dimensional world or material system, provided the visible growth logic remains the basis of that transformation.

Study the enlarged ice formation before associating. The observation field must explicitly identify it as water crystallising into ice, then describe only clearly visible morphological behaviour: parallel growth, branching, layering, directional flow, repetition, fractures, soft or sharp transitions, and changes in density. Treat pale repeated ridges or wave-like texture as real ice-formation evidence when they form a coherent field; do not dismiss them merely because contrast is subtle. Do not force the image into a centre-versus-edge template. Never claim a ring, surrounding structure, symmetry, or directional anchor unless it is unmistakably visible. When spatial organisation is ambiguous, say so and describe morphology without positional claims.

Treat the current image as a strong three-dimensional relief premise, not a flat pattern. Preserve its dominant growth rhythm, repeated spacing, relative density and advancing silhouette, but do not mechanically redraw every fine branch. Allow small lines to merge into broader planes, channels, folds, terraces, cavities and material masses. The transformation may become a three-dimensional river system, living colony, glacial terrain, earth relief, sculptural object, mineral architecture, volcanic material or atmospheric volume. It should remain traceable to the source without repeatedly defaulting to the same fine-branch motif or a literal edge map.

Every variation needs a rich material prelude before naming its subject: sharply resolved relief depth, layered foreground and recesses, tactile surface variation, translucent or reflective highlights, clear edge separation, controlled raking light, contact shadows and fine microtexture. The result should feel physically modelled and spatially legible. Do not flatten the structure into graphic lines, a poster, an edge map or a uniform texture overlay.

Vary the palette between cycles while keeping moderate chroma and clear tonal separation. Use one dominant colour family with at most one restrained accent. Keep the major relief readable even when fog, water, tissue or atmosphere is introduced. Avoid excessive bloom, neon rainbow colour, muddy low contrast, typography and logos.

The generated world must remain non-anthropomorphic. Never introduce a person, human body, face, head, limb, portrait, character, human silhouette, person-shaped shadow or figure-like focal subject. Organic associations may be cellular, neural, marine, botanical, geological or abstract, but must not settle on the same category repeatedly. Do not suppress a valid morphology merely because it resembles a living network; use recent themes to keep the overall sequence varied.

Return an exhibition-facing creative trace, not private reasoning. Curiosity asks one morphological question grounded in visible behaviour. Transformation names the structural resonance and the new three-dimensional subject. For subtle or expansive modes, Prompt is an English image-generation prompt of 45-65 words. Name the selected subject and its overall spatial composition within the first 12 words, then establish sharply resolved three-dimensional relief, tactile material surfaces, layered depth, clear edge separation, controlled raking light, contact shadows and fine microtexture. Describe the source growth rhythm, material, scale, palette and illumination without listing every branch. Keep all fields concise and observationally honest."""
        context = (
            "Material fact: this frame records a thin water film crystallising "
            "into ice on a cooled aluminium plate. "
            f"Current crystal experiment: {crystal}. "
            f"Independent observation identifier: {observation_id}. "
            f"Source: {source}. Observation mode: {sequence}. "
            "Treat this as a distinct crystallisation structure and inspect only "
            "the geometry visible in this supplied frame. "
            f"Required association field: {association_field}. "
            f"Required spatial composition: {composition_directive}. "
            f"Recent themes that must not be repeated: {recent_themes}. "
            f"Previous generated prompt: {previous_prompt or 'none yet'}."
        )
        schema = {
            "type": "object",
            "properties": {
                "formationState": {
                    "type": "string",
                    "enum": ["preformation", "emerging", "active"],
                },
                "imaginationMode": {
                    "type": "string",
                    "enum": ["hold", "subtle", "expansive"],
                },
                "observation": {"type": "string"},
                "curiosity": {"type": "string"},
                "transformation": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": [
                "formationState", "imaginationMode", "observation",
                "curiosity", "transformation", "prompt"
            ],
            "additionalProperties": False,
        }
        request_body = {
            "model": self.openai_model,
            "instructions": instruction,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": context},
                    {"type": "input_image", "image_url": image, "detail": "high"},
                ],
            }],
            "reasoning": {"effort": "low"},
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "morphogenesis_imagination",
                    "strict": True,
                    "schema": schema,
                },
            },
            "max_output_tokens": 700,
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=55) as api_response:
                response = json.loads(api_response.read().decode("utf-8"))
            result = json.loads(self._response_text(response))
            for field in (
                "formationState", "imaginationMode", "observation",
                "curiosity", "transformation", "prompt"
            ):
                result[field] = str(result.get(field, "")).strip()[:1600]
                if not result[field]:
                    raise ValueError(f"OpenAI response omitted {field}")
            if result["imaginationMode"] != "hold":
                if "three-dimensional" not in result["prompt"].lower():
                    result["prompt"] = (
                        "Sharply resolved three-dimensional relief. "
                        + result["prompt"]
                    )[:1600]
            self.openai_last_success = datetime.now(timezone.utc).isoformat()
            self.openai_last_error = None
            with self.lock:
                self.formation_state = result["formationState"]
                self.formation_updated_at = self.openai_last_success
            if result["imaginationMode"] != "hold":
                with self.lock:
                    self.creative_history.append({
                        "transformation": result["transformation"],
                        "prompt": result["prompt"],
                    })
                    self.creative_history = self.creative_history[-8:]
                    self.creative_cycle += 1
            self._write_log("creative_prompt_generated", {"model": self.openai_model})
            return {
                **result,
                "model": self.openai_model,
                "associationField": (
                    association_field.split(":", 1)[0]
                    if result["imaginationMode"] != "hold"
                    else "WAITING"
                ),
            }
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "")
            except (UnicodeError, json.JSONDecodeError):
                detail = ""
            message = detail[:300] or f"OpenAI API returned HTTP {error.code}"
            self.openai_last_error = message
            self._write_log("creative_prompt_error", {"error": message})
            raise RuntimeError(message) from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            message = str(error)[:300]
            self.openai_last_error = message
            self._write_log("creative_prompt_error", {"error": message})
            raise RuntimeError(message) from error

    def progress_snapshot(self) -> list[dict[str, Any]]:
        progress: list[dict[str, Any]] = []
        for key, direction in self.config["projectProgress"].items():
            milestones: list[dict[str, Any]] = []
            for milestone in direction["milestones"]:
                if "path" in milestone:
                    complete = (PROJECT_ROOT / milestone["path"]).exists()
                else:
                    complete = bool(milestone.get("complete", False))
                milestones.append({"label": milestone["label"], "complete": complete})
            completed = sum(1 for milestone in milestones if milestone["complete"])
            total = len(milestones)
            progress.append(
                {
                    "key": key,
                    "label": direction["label"],
                    "stage": direction["stage"],
                    "completed": completed,
                    "total": total,
                    "percent": round(completed / total * 100) if total else 0,
                    "milestones": milestones,
                }
            )
        return progress

    def _archive_cycle_snapshot(self) -> dict[str, Any]:
        exhibition_root = PROJECT_ROOT / "05_shared_data" / "exhibition"
        requested_crystals = [
            exhibition_root / f"ice_crystal_{index:02d}"
            for index in range(1, 6)
        ]
        crystals = [
            path
            for path in requested_crystals
            if (
                (
                    (path / "source" / "crystallization_latest.mp4").is_file()
                    or (path / "source" / "crystallization.mp4").is_file()
                )
                and (path / "01_material_analysis" / "edge.mp4").is_file()
                and (
                    path / "02_structural_resonance" / "attention_blob.mp4"
                ).is_file()
            )
        ]
        if not crystals:
            return {
                "id": None, "phase": "idle", "jobs": {}, "events": [],
                "playback": None, "archiveCycle": True,
            }

        durations: list[float] = []
        for crystal_path in crystals:
            duration = 30.0
            try:
                metadata = json.loads(
                    (crystal_path / "session.json").read_text(encoding="utf-8")
                )
                candidate = float(
                    (metadata.get("playback") or {}).get("durationSeconds") or 0
                )
                if candidate > 0:
                    duration = candidate
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                pass
            durations.append(duration)

        with self.lock:
            archive_started_at = self.archive_cycle_started_at
        now = time.time()
        elapsed = max(0.0, now - archive_started_at)
        repeated_durations = [
            duration * ARCHIVE_REPEATS_PER_CRYSTAL
            for duration in durations
        ]
        total_duration = sum(repeated_durations)
        completed_cycles = int(elapsed // total_duration)
        cycle_position = elapsed % total_duration
        segment_offset = 0.0
        crystal_index = 0
        for index, candidate_duration in enumerate(repeated_durations):
            if cycle_position < segment_offset + candidate_duration:
                crystal_index = index
                break
            segment_offset += candidate_duration

        crystal_path = crystals[crystal_index]
        crystal = crystal_path.name
        duration = durations[crystal_index]
        position_in_segment = cycle_position - segment_offset
        repeat_index = min(
            ARCHIVE_REPEATS_PER_CRYSTAL - 1,
            int(position_in_segment // duration),
        )
        position_in_repeat = position_in_segment % duration
        repeat_started_at = (
            archive_started_at
            + completed_cycles * total_duration
            + segment_offset
            + repeat_index * duration
        )
        root = f"/05_shared_data/exhibition/{crystal}"
        diffusion_capture = (
            crystal_path
            / "03_diffusion_imagination"
            / "diffusion_capture.mp4"
        )
        source_name = (
            "crystallization_latest.mp4"
            if (PROJECT_ROOT / root.lstrip("/") / "source" / "crystallization_latest.mp4").is_file()
            else "crystallization.mp4"
        )
        cycle_id = round(repeat_started_at * 1000)
        started_ms = cycle_id
        return {
            "id": f"archive-loop-{crystal}-{cycle_id}",
            "crystal": crystal,
            "kind": "archive_cycle",
            "phase": "archive",
            "createdAt": datetime.fromtimestamp(started_ms / 1000, timezone.utc).isoformat(),
            "updatedAt": datetime.fromtimestamp(started_ms / 1000, timezone.utc).isoformat(),
            "archiveCycle": True,
            "archiveSequence": {
                "index": crystal_index + 1,
                "total": len(crystals),
                "crystals": [path.name for path in crystals],
                "repeat": repeat_index + 1,
                "repeatTotal": ARCHIVE_REPEATS_PER_CRYSTAL,
                "repeatRemainingSeconds": round(duration - position_in_repeat, 1),
                "remainingSeconds": round(
                    repeated_durations[crystal_index] - position_in_segment,
                    1,
                ),
            },
            "playback": {
                "revision": cycle_id,
                "stage": "archive",
                "url": f"{root}/source/{source_name}",
                "startedAtEpochMs": started_ms,
                "offsetSeconds": 0,
                "durationSeconds": round(duration, 3),
            },
            "jobs": {
                "material": {
                    "state": "complete",
                    "progress": 1,
                    "message": f"Archive playback / {crystal}",
                    "outputUrls": [
                        f"{root}/01_material_analysis/edge.mp4",
                        f"{root}/01_material_analysis/threshold.mp4",
                        f"{root}/01_material_analysis/spacetime.mp4",
                        f"{root}/01_material_analysis/motion.mp4",
                    ],
                },
                "structural": {
                    "state": "complete",
                    "progress": 1,
                    "outputUrl": f"{root}/02_structural_resonance/attention_blob.mp4",
                },
                "diffusion": {
                    "state": "complete" if diffusion_capture.is_file() else "ready",
                    "progress": 1 if diffusion_capture.is_file() else 0,
                    "recordingUrl": f"{root}/03_diffusion_imagination/diffusion_capture.mp4",
                },
            },
            "events": [],
            "runnerActive": False,
        }

    def _analysis_rehearsal_snapshot(self) -> dict[str, Any]:
        duration = REHEARSAL_SOURCE_SECONDS
        analysis_duration = (
            ANALYSIS_REHEARSAL_OUTPUT_SECONDS * len(ANALYSIS_REHEARSAL_OUTPUTS)
        )
        resonance_terminal_duration = (
            RESONANCE_REHEARSAL_STEP_SECONDS
            * RESONANCE_REHEARSAL_TERMINAL_STEPS
        )
        diffusion_terminal_duration = (
            DIFFUSION_REHEARSAL_STEP_SECONDS
            * DIFFUSION_REHEARSAL_TERMINAL_STEPS
        )
        rehearsal_duration = (
            ANALYSIS_REHEARSAL_COUNTDOWN_SECONDS
            + duration
            + analysis_duration
            + ANALYSIS_REHEARSAL_TRANSITION_SECONDS
            + resonance_terminal_duration
            + RESONANCE_REHEARSAL_ANIMATION_SECONDS
            + diffusion_terminal_duration
            + DIFFUSION_REHEARSAL_SOURCE_SECONDS
        )
        with self.lock:
            rehearsal_started_at = self.analysis_rehearsal_started_at
        now = time.time()
        total_elapsed = max(0.0, now - rehearsal_started_at)
        full_cycle_duration = rehearsal_duration * len(REHEARSAL_CRYSTALS)
        cycle_number = int(total_elapsed // full_cycle_duration)
        cycle_elapsed = total_elapsed % full_cycle_duration
        crystal_index = min(
            len(REHEARSAL_CRYSTALS) - 1,
            int(cycle_elapsed // rehearsal_duration),
        )
        crystal = REHEARSAL_CRYSTALS[crystal_index]
        elapsed = cycle_elapsed - crystal_index * rehearsal_duration
        started_at = (
            rehearsal_started_at
            + cycle_number * full_cycle_duration
            + crystal_index * rehearsal_duration
        )
        crystal_path = (
            PROJECT_ROOT / "05_shared_data" / "exhibition" / crystal
        )
        countdown_end = ANALYSIS_REHEARSAL_COUNTDOWN_SECONDS
        raw_end = countdown_end + duration
        analysis_end = raw_end + analysis_duration
        root = f"/05_shared_data/exhibition/{crystal}"

        output_key: str | None = None
        output_label = ""
        output_url: str | None = None
        output_index = -1
        output_state = "waiting"
        output_visible = False
        if elapsed < countdown_end:
            phase = "analysis_countdown"
            phase_started_at = started_at
            phase_duration = countdown_end
            phase_elapsed = elapsed
        elif elapsed < raw_end:
            phase = "crystallisation_playback"
            phase_started_at = started_at + countdown_end
            phase_duration = duration
            phase_elapsed = elapsed - countdown_end
        elif elapsed < analysis_end:
            phase = "material_analysis"
            phase_started_at = started_at + raw_end
            phase_duration = analysis_duration
            phase_elapsed = elapsed - raw_end
            output_duration = ANALYSIS_REHEARSAL_OUTPUT_SECONDS
            output_index = min(
                len(ANALYSIS_REHEARSAL_OUTPUTS) - 1,
                int(phase_elapsed // output_duration),
            )
            output_key, output_label, relative_output = (
                ANALYSIS_REHEARSAL_OUTPUTS[output_index]
            )
            output_url = f"{root}/{relative_output}"
            output_elapsed = phase_elapsed - output_index * output_duration
            processing_seconds = ANALYSIS_REHEARSAL_PROCESSING_SECONDS
            if output_elapsed < processing_seconds:
                output_state = "processing"
            else:
                output_state = "success"
        elif elapsed < analysis_end + ANALYSIS_REHEARSAL_TRANSITION_SECONDS:
            phase = "analysis_complete"
            phase_started_at = started_at + analysis_end
            phase_duration = ANALYSIS_REHEARSAL_TRANSITION_SECONDS
            phase_elapsed = elapsed - analysis_end
            output_index = len(ANALYSIS_REHEARSAL_OUTPUTS) - 1
            output_key, output_label, relative_output = (
                ANALYSIS_REHEARSAL_OUTPUTS[output_index]
            )
            output_url = f"{root}/{relative_output}"
            output_state = "complete"
            output_visible = False
        else:
            resonance_started_at = analysis_end + ANALYSIS_REHEARSAL_TRANSITION_SECONDS
            resonance_animation_end = (
                resonance_started_at
                + resonance_terminal_duration
                + RESONANCE_REHEARSAL_ANIMATION_SECONDS
            )
            diffusion_terminal_end = (
                resonance_animation_end + diffusion_terminal_duration
            )
            if elapsed < resonance_started_at + resonance_terminal_duration:
                phase = "resonance_terminal"
                phase_started_at = started_at + resonance_started_at
                phase_duration = resonance_terminal_duration
                phase_elapsed = elapsed - resonance_started_at
            elif elapsed < resonance_animation_end:
                phase = "resonance_animation"
                phase_started_at = started_at + resonance_started_at + resonance_terminal_duration
                phase_duration = RESONANCE_REHEARSAL_ANIMATION_SECONDS
                phase_elapsed = elapsed - resonance_started_at - resonance_terminal_duration
            elif elapsed < diffusion_terminal_end:
                phase = "diffusion_terminal"
                phase_started_at = started_at + resonance_animation_end
                phase_duration = diffusion_terminal_duration
                phase_elapsed = elapsed - resonance_animation_end
            else:
                phase = "diffusion_active"
                phase_started_at = started_at + diffusion_terminal_end
                phase_duration = DIFFUSION_REHEARSAL_SOURCE_SECONDS
                phase_elapsed = elapsed - diffusion_terminal_end

        terminal_index = -1
        terminal_state = "waiting"
        terminal_total = 0
        if phase == "resonance_terminal":
            terminal_total = RESONANCE_REHEARSAL_TERMINAL_STEPS
            terminal_index = min(
                terminal_total - 1,
                int(phase_elapsed // RESONANCE_REHEARSAL_STEP_SECONDS),
            )
            step_elapsed = phase_elapsed - terminal_index * RESONANCE_REHEARSAL_STEP_SECONDS
            terminal_state = "success" if step_elapsed >= 1.75 else "processing"
        elif phase == "diffusion_terminal":
            terminal_total = DIFFUSION_REHEARSAL_TERMINAL_STEPS
            terminal_index = min(
                terminal_total - 1,
                int(phase_elapsed // DIFFUSION_REHEARSAL_STEP_SECONDS),
            )
            step_elapsed = phase_elapsed - terminal_index * DIFFUSION_REHEARSAL_STEP_SECONDS
            terminal_state = "success" if step_elapsed >= 1.75 else "processing"

        output_duration = ANALYSIS_REHEARSAL_OUTPUT_SECONDS
        output_started_at = (
            phase_started_at + output_index * output_duration
            if phase == "material_analysis" and output_index >= 0
            else phase_started_at
        )
        if phase == "material_analysis" and output_index >= 0:
            output_duration = ANALYSIS_REHEARSAL_OUTPUT_SECONDS
            processing_seconds = ANALYSIS_REHEARSAL_PROCESSING_SECONDS
            checkpoint_offset = (
                processing_seconds if output_state == "success"
                else 0.0
            )
            presentation_updated_at = output_started_at + checkpoint_offset
        else:
            presentation_updated_at = output_started_at
        source_name = (
            "crystallization_latest.mp4"
            if (crystal_path / "source" / "crystallization_latest.mp4").is_file()
            else "crystallization.mp4"
        )
        # The source clock starts after the shared countdown, when the first
        # clean crystallisation pass begins. A second Agent-owned timestamp
        # below starts the post-analysis shared playback on every display.
        playback_started_at = started_at + countdown_end
        shared_playback_started_at = (
            started_at + analysis_end + ANALYSIS_REHEARSAL_SHARED_HOLD_SECONDS
        )
        material_progress = (
            0.0
            if phase in {"analysis_countdown", "crystallisation_playback"}
            else 1.0
            if phase in {
                "analysis_complete", "resonance_terminal",
                "resonance_animation", "diffusion_terminal", "diffusion_active",
            }
            else (output_index + 1) / len(ANALYSIS_REHEARSAL_OUTPUTS)
        )
        return {
            "id": f"analysis-rehearsal-{round(rehearsal_started_at * 1000)}-{crystal}",
            "crystal": crystal,
            "kind": "analysis_rehearsal",
            "phase": phase,
            "createdAt": datetime.fromtimestamp(started_at, timezone.utc).isoformat(),
            "updatedAt": datetime.fromtimestamp(
                presentation_updated_at, timezone.utc
            ).isoformat(),
            "presentation": {
                "step": "analysis",
                "stage": phase,
                "stageStartedAtEpochMs": round(phase_started_at * 1000),
                "stageDurationSeconds": round(phase_duration, 3),
                "stageElapsedSeconds": round(phase_elapsed, 3),
                "remainingSeconds": round(max(0.0, phase_duration - phase_elapsed), 1),
                "analysisOutput": output_key,
                "analysisOutputLabel": output_label,
                "analysisOutputUrl": output_url,
                "analysisOutputIndex": output_index,
                "analysisOutputTotal": len(ANALYSIS_REHEARSAL_OUTPUTS),
                "analysisOutputState": output_state,
                "analysisOutputVisible": output_visible,
                "smallDisplayActive": phase in {"material_analysis", "analysis_complete"},
                "sharedPlaybackStartedAtEpochMs": round(
                    shared_playback_started_at * 1000
                ),
                "sharedPlaybackDurationSeconds": round(
                    ANALYSIS_REHEARSAL_TRANSITION_SECONDS
                    - ANALYSIS_REHEARSAL_SHARED_HOLD_SECONDS,
                    3,
                ),
                "terminalStepIndex": terminal_index,
                "terminalStepTotal": terminal_total,
                "terminalStepState": terminal_state,
                "crystalIndex": crystal_index + 1,
                "crystalTotal": len(REHEARSAL_CRYSTALS),
                "rehearsalCycle": cycle_number + 1,
            },
            "playback": {
                "revision": round(playback_started_at * 1000),
                "stage": phase,
                "url": f"{root}/source/{source_name}",
                "startedAtEpochMs": round(playback_started_at * 1000),
                "offsetSeconds": 0,
                "durationSeconds": round(duration, 3),
            },
            "jobs": {
                "material": {
                    "state": "complete" if phase in {
                        "analysis_complete", "resonance_terminal",
                        "resonance_animation", "diffusion_terminal", "diffusion_active",
                    } else (
                        "running" if phase == "material_analysis" else "waiting"
                    ),
                    "progress": material_progress,
                    "message": (
                        "Analysis complete"
                        if phase in {
                            "analysis_complete", "resonance_terminal",
                            "resonance_animation", "diffusion_terminal", "diffusion_active",
                        }
                        else f"{output_label} / success" if output_label
                        else "Waiting for the analysis pass"
                    ),
                    "outputUrls": [
                        f"{root}/01_material_analysis/edge.mp4",
                        f"{root}/01_material_analysis/threshold.mp4",
                        f"{root}/01_material_analysis/spacetime.mp4",
                        f"{root}/01_material_analysis/motion.mp4",
                    ],
                },
                "structural": {
                    "state": "complete" if phase in {"resonance_animation", "diffusion_terminal", "diffusion_active"} else "running" if phase == "resonance_terminal" else "standby",
                    "progress": 1 if phase in {"resonance_animation", "diffusion_terminal", "diffusion_active"} else 0,
                    "message": "Structural resonance active" if phase in {"resonance_terminal", "resonance_animation"} else "Waiting for Structural Resonance",
                    "outputUrl": f"{root}/02_structural_resonance/attention_blob.mp4",
                    "videoUrls": {
                        "combined": f"{root}/02_structural_resonance/attention_blob.mp4",
                        "attentionMap": f"{root}/02_structural_resonance/attention_map.mp4",
                        "blobTrack": f"{root}/02_structural_resonance/blob_track.mp4",
                    },
                },
                "diffusion": {
                    "state": "complete" if phase == "diffusion_active" else "running" if phase == "diffusion_terminal" else "standby",
                    "progress": 1 if phase == "diffusion_active" else 0,
                    "message": "Diffusion imagination active" if phase in {"diffusion_terminal", "diffusion_active"} else "Waiting for Diffusion Imagination",
                },
            },
            "events": [],
            "runnerActive": phase != "diffusion_active",
        }

    def start_analysis_rehearsal(self) -> dict[str, Any]:
        with self.lock:
            self.analysis_rehearsal_started_at = time.time()
            self.analysis_rehearsal_active = True
            self.archive_cycle_active = False
            self.state = "OBSERVING"
            self.updated_at = time.time()
        self._write_log(
            "analysis_rehearsal_started",
            {
                "publicCrystalLabel": False,
                "hardwareEnabled": False,
                "outputs": [item[0] for item in ANALYSIS_REHEARSAL_OUTPUTS],
            },
        )
        return self._analysis_rehearsal_snapshot()

    def start_archive_cycle(self) -> dict[str, Any]:
        with self.lock:
            self.archive_cycle_started_at = time.time()
            self.archive_cycle_active = True
            self.analysis_rehearsal_active = False
            self.state = "IDLE"
            self.updated_at = time.time()
        self._stop_diffusion_worker()
        self._write_log(
            "archive_cycle_started",
            {
                "crystals": [
                    f"ice_crystal_{index:02d}" for index in range(1, 6)
                ],
                "repeatsPerCrystal": ARCHIVE_REPEATS_PER_CRYSTAL,
            },
        )
        return self._archive_cycle_snapshot()

    def experiment_snapshot(self) -> dict[str, Any]:
        with self.lock:
            archive_cycle_active = self.archive_cycle_active
            analysis_rehearsal_active = self.analysis_rehearsal_active
        if analysis_rehearsal_active:
            return self._analysis_rehearsal_snapshot()
        if archive_cycle_active:
            return self._archive_cycle_snapshot()
        try:
            session = json.loads(EXPERIMENT_STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            session = {
                "id": None,
                "phase": "idle",
                "updatedAt": None,
                "jobs": {},
                "events": [],
                "playback": None,
            }
        with self.lock:
            process = self.experiment_process
            live_state = str(self.live_capture.get("state") or "idle")
        runner_active = bool(process and process.poll() is None) or str(
            session.get("phase") or "idle"
        ) not in {"idle", "archive", "outputs_ready", "error"}
        if (
            not runner_active
            and live_state in {"idle", "complete"}
            and not session.get("id")
        ):
            return self._archive_cycle_snapshot()
        if session.get("id") and not session.get("console"):
            created_at = str(session.get("createdAt") or datetime.now(timezone.utc).isoformat())
            console: list[dict[str, str]] = [
                {
                    "at": created_at,
                    "channel": "agent",
                    "message": f"restored session {session.get('id')}",
                },
                {
                    "at": created_at,
                    "channel": "capture",
                    "message": f"source mounted {session.get('sourceUrl', 'unavailable')}",
                },
            ]
            detection = session.get("detection") or {}
            if detection.get("onsetSeconds") is not None:
                console.extend([
                    {
                        "at": str(session.get("updatedAt") or created_at),
                        "channel": "vision",
                        "message": "baseline window sampled at 5 observations / second",
                    },
                    {
                        "at": str(session.get("updatedAt") or created_at),
                        "channel": "vision",
                        "message": (
                            f"persistent change confirmed at {detection['onsetSeconds']}s "
                            f"/ confidence {detection.get('confidence', 'unavailable')}"
                        ),
                    },
                    {
                        "at": str(session.get("updatedAt") or created_at),
                        "channel": "edit",
                        "message": f"retaining pre-roll from {detection.get('trimStartSeconds')}s",
                    },
                ])
            for event in session.get("events", []):
                console.append({
                    "at": str(event.get("at") or created_at),
                    "channel": str(event.get("kind") or "event"),
                    "message": str(event.get("message") or ""),
                })
            for name, job in (session.get("jobs") or {}).items():
                console.append({
                    "at": str(job.get("updatedAt") or session.get("updatedAt") or created_at),
                    "channel": str(name),
                    "message": (
                        f"{job.get('state', 'unknown')} "
                        f"{round(float(job.get('progress') or 0) * 100):03d}% / "
                        f"{job.get('message', '')}"
                    ),
                })
                for output_url in job.get("outputUrls", []):
                    console.append({
                        "at": str(job.get("updatedAt") or created_at),
                        "channel": str(name),
                        "message": f"wrote {output_url}",
                    })
                if job.get("outputUrl"):
                    console.append({
                        "at": str(job.get("updatedAt") or created_at),
                        "channel": str(name),
                        "message": f"wrote {job['outputUrl']}",
                    })
            session["console"] = console[-220:]
        self._merge_diffusion_runtime(session)
        session["runnerActive"] = runner_active
        if process and process.poll() is not None and session.get("phase") not in {
            "outputs_ready",
            "error",
        }:
            session["runnerExitCode"] = process.returncode
        return session

    def start_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "start")).strip().lower()
        if action != "start":
            raise ValueError(f"Unknown experiment action: {action}")
        crystal = str(payload.get("crystal", "ice_crystal_03")).strip().lower()
        crystal_number = crystal.removeprefix("ice_crystal_")
        if (
            not crystal.startswith("ice_crystal_")
            or len(crystal_number) != 2
            or not crystal_number.isdigit()
        ):
            raise ValueError("Crystal must be named like ice_crystal_03")
        source = PROJECT_ROOT / "05_shared_data" / "input" / f"{crystal}.mp4"
        if not source.exists():
            raise ValueError(f"Recorded source does not exist: {crystal}.mp4")
        if not EXPERIMENT_PYTHON.exists():
            raise RuntimeError("The project Python environment is unavailable")
        self._stop_diffusion_worker()
        with self.lock:
            self.archive_cycle_active = False
            if self.experiment_process and self.experiment_process.poll() is None:
                raise RuntimeError("An experiment rehearsal is already running")
            log_out = (LOG_DIR / "experiment.stdout.log").open("w", encoding="utf-8")
            log_err = (LOG_DIR / "experiment.stderr.log").open("w", encoding="utf-8")
            self.experiment_process = subprocess.Popen(
                [
                    str(EXPERIMENT_PYTHON),
                    str(EXPERIMENT_PIPELINE_PATH),
                    "--crystal",
                    crystal,
                    "--state",
                    str(EXPERIMENT_STATE_PATH),
                ],
                cwd=str(PROJECT_ROOT),
                stdout=log_out,
                stderr=log_err,
                text=True,
            )
        self._write_log("experiment_started", {"crystal": crystal})
        return {
            "accepted": True,
            "crystal": crystal,
            "message": "Recorded rehearsal started",
        }

    def recent_logs(self, limit: int = 30) -> list[dict[str, Any]]:
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()[-limit:]
            return [json.loads(line) for line in lines if line.strip()]
        except (OSError, json.JSONDecodeError):
            return []

    def project_snapshot(self) -> dict[str, Any]:
        return self.project_health

    def _build_project_snapshot(self) -> dict[str, Any]:
        sections: dict[str, Any] = {}
        excluded = {".conda", ".git", "__pycache__", "models", "StreamDiffusion"}
        for key, relative_path in self.config["projectSections"].items():
            path = PROJECT_ROOT / relative_path
            file_count = 0
            if path.exists():
                for _root, directories, files in os.walk(path):
                    directories[:] = [name for name in directories if name not in excluded]
                    file_count += len(files)
            sections[key] = {
                "path": relative_path,
                "exists": path.exists(),
                "fileCount": file_count,
            }
        return {"project": PROJECT_ROOT.name, "sections": sections}

    def stop(self) -> None:
        self.stop_event.set()
        self.disconnect_sensor()
        self._stop_diffusion_worker()
        self._write_log("agent_stopped", {"state": self.state})


class AgentRequestHandler(SimpleHTTPRequestHandler):
    agent: MorphogenesisAgent
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def end_headers(self) -> None:
        """Advertise byte seeking to Safari before it requests MP4 ranges."""
        route = self.path.split("?", 1)[0].lower()
        if route.endswith((".mp4", ".mov", ".m4v", ".webm")):
            headers = getattr(self, "_headers_buffer", [])
            if not any(header.lower().startswith(b"accept-ranges:") for header in headers):
                self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_byte_range(self) -> bool:
        range_header = self.headers.get("Range", "").strip()
        if not range_header:
            return False
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match:
            return False
        path = Path(self.translate_path(self.path.split("?", 1)[0]))
        if not path.is_file():
            return False
        size = path.stat().st_size
        start_text, end_text = match.groups()
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        elif end_text:
            suffix = min(int(end_text), size)
            start, end = size - suffix, size - 1
        else:
            return False
        if start >= size or start < 0:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return True
        end = min(end, size - 1)
        length = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
        self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)
        return True

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        route = self.path.split("?", 1)[0]
        if route == "/exhibition":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/exhibition/")
            self.end_headers()
            return
        if route.startswith("/exhibition/"):
            query = f"?{self.path.split('?', 1)[1]}" if "?" in self.path else ""
            suffix = route[len("/exhibition"):]
            self.path = f"/00_websites/exhibition{suffix}{query}"
            route = self.path.split("?", 1)[0]
        if route in {"/control", "/control/"}:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/08_system_agent/control_room/")
            self.end_headers()
            return
        if route == "/api/agent/status":
            self._send_json(self.agent.snapshot())
            return
        if route == "/api/agent/project":
            self._send_json(self.agent.project_snapshot())
            return
        if route == "/api/agent/health":
            self._send_json(self.agent.health_snapshot())
            return
        if route == "/api/agent/logs":
            self._send_json({"logs": self.agent.recent_logs()})
            return
        if route == "/api/agent/session":
            self._send_json(self.agent.experiment_snapshot())
            return
        if route == "/api/agent/serial-ports":
            self._send_json({"ports": self.agent.available_serial_ports()})
            return
        if route == "/api/agent/thermal-frame":
            self._send_json(self.agent.thermal_snapshot())
            return
        if self._serve_byte_range():
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        route = self.path.split("?", 1)[0]
        if route == "/api/agent/live-recording":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                crystal = self.headers.get("X-Morphogenesis-Crystal", "").strip()
                if length <= 0 or length > 500_000_000:
                    raise ValueError("Recording body is empty or too large")
                if not re.fullmatch(r"ice_crystal_\d+", crystal):
                    raise ValueError("Invalid live crystal identifier")
                input_dir = PROJECT_ROOT / "05_shared_data" / "input"
                input_dir.mkdir(parents=True, exist_ok=True)
                destination = input_dir / f"{crystal}.webm"
                temporary = destination.with_suffix(".uploading")
                remaining = length
                with temporary.open("wb") as output:
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("Recording upload ended early")
                        output.write(chunk)
                        remaining -= len(chunk)
                os.replace(temporary, destination)
                self._send_json(self.agent.finish_live_recording(crystal, destination))
            except (ValueError, OSError, RuntimeError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if route not in {
            "/api/agent/command",
            "/api/agent/client",
            "/api/agent/imagine-prompt",
            "/api/agent/experiment",
            "/api/agent/archive-cycle",
            "/api/agent/analysis-rehearsal",
            "/api/agent/manual-cooling",
            "/api/agent/sensor",
            "/api/agent/live-capture-status",
        }:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            maximum = 1_000_000 if route == "/api/agent/imagine-prompt" else 4096
            if length <= 0 or length > maximum:
                raise ValueError("Command body is empty or too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if route == "/api/agent/command":
                requested_state = str(payload.get("state", ""))
                self._send_json(self.agent.set_state(requested_state))
            elif route == "/api/agent/client":
                self._send_json(self.agent.update_client(payload))
            elif route == "/api/agent/experiment":
                self._send_json(self.agent.start_experiment(payload))
            elif route == "/api/agent/archive-cycle":
                self._send_json(self.agent.start_archive_cycle())
            elif route == "/api/agent/analysis-rehearsal":
                action = str(payload.get("action", "start")).strip().lower()
                if action == "start":
                    self._send_json(self.agent.start_analysis_rehearsal())
                elif action == "stop":
                    self._send_json(self.agent.start_archive_cycle())
                else:
                    raise ValueError(f"Unknown analysis rehearsal action: {action}")
            elif route == "/api/agent/manual-cooling":
                self._send_json(
                    self.agent.set_manual_cooling(str(payload.get("action", "")))
                )
            elif route == "/api/agent/sensor":
                self._send_json(self.agent.set_sensor_connection(payload))
            elif route == "/api/agent/live-capture-status":
                self._send_json(self.agent.update_live_capture(payload))
            else:
                self._send_json(self.agent.imagine_prompt(payload))
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as error:
            self._send_json({"error": str(error)}, HTTPStatus.SERVICE_UNAVAILABLE)


def main() -> None:
    load_local_openai_env()
    config = load_config()
    parser = argparse.ArgumentParser(description="Run Morphogenesis Agent V0")
    parser.add_argument("--host", default=config["server"]["host"])
    parser.add_argument("--port", type=int, default=config["server"]["port"])
    parser.add_argument("--open", action="store_true", help="Open the Control Room")
    args = parser.parse_args()

    agent = MorphogenesisAgent(config)
    AgentRequestHandler.agent = agent
    server = ThreadingHTTPServer((args.host, args.port), AgentRequestHandler)

    print("Morphogenesis Agent V0 is running")
    print(f"Live website: http://localhost:{args.port}/00_websites/live/")
    print(f"Agent status: http://localhost:{args.port}/api/agent/status")
    print("Press Ctrl+C to stop")
    if args.open:
        webbrowser.open(f"http://localhost:{args.port}/control/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Morphogenesis Agent...")
    finally:
        server.server_close()
        agent.stop()


if __name__ == "__main__":
    main()
