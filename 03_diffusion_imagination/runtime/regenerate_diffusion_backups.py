"""Regenerate one synchronized Diffusion backup for every exhibition crystal."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
import time
import urllib.request

import cv2
import numpy as np
import websockets


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXHIBITION_ROOT = PROJECT_ROOT / "05_shared_data" / "exhibition"
WORKER_WS = "ws://127.0.0.1:8091/ws"
AGENT_PROMPT_URL = "http://127.0.0.1:8080/api/agent/imagine-prompt"
FRAME_SIZE = 640


def source_path(crystal: str) -> Path:
    source_dir = EXHIBITION_ROOT / crystal / "source"
    latest = source_dir / "crystallization_latest.mp4"
    return latest if latest.is_file() else source_dir / "crystallization.mp4"


def session_duration(crystal: str, video_duration: float) -> float:
    try:
        session = json.loads(
            (EXHIBITION_ROOT / crystal / "session.json").read_text(encoding="utf-8")
        )
        duration = float((session.get("playback") or {}).get("durationSeconds") or 0)
        if duration > 0:
            return duration
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return video_duration


def prepare_frame(frame: np.ndarray, *, ai_reading: bool = False) -> bytes:
    height, width = frame.shape[:2]
    side_fraction = 0.07 if ai_reading else 0.03
    top_fraction = 0.10 if ai_reading else 0.06
    bottom_fraction = 0.04 if ai_reading else 0.0
    side = int(width * side_fraction)
    top = int(height * top_fraction)
    bottom = int(height * bottom_fraction)
    roi = frame[top : height - bottom, side : width - side]
    roi_height, roi_width = roi.shape[:2]
    crop_size = min(roi_width, roi_height)
    x = max(0, (roi_width - crop_size) // 2)
    y = max(0, (roi_height - crop_size) // 2)
    roi = roi[y : y + crop_size, x : x + crop_size]
    roi = cv2.resize(roi, (FRAME_SIZE, FRAME_SIZE), interpolation=cv2.INTER_AREA)

    contrast = 1.9 if ai_reading else 1.42
    brightness = 0.72 if ai_reading else 0.88
    saturation = 0.68 if ai_reading else 0.38
    adjusted = np.clip((roi.astype(np.float32) - 127.5) * contrast + 127.5, 0, 255)
    adjusted = np.clip(adjusted * brightness, 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(adjusted, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] *= saturation
    adjusted = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    ok, encoded = cv2.imencode(".jpg", adjusted, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise RuntimeError("Could not encode source frame")
    return encoded.tobytes()


def request_ai_prompt(crystal: str, frame_bytes: bytes) -> str:
    payload = {
        "image": "data:image/jpeg;base64," + base64.b64encode(frame_bytes).decode("ascii"),
        "source": f"recorded macro video of water crystallising into ice / {crystal}",
        "sequence": "enlarged-high-contrast-formation-frame",
        "previous": {},
    }
    request = urllib.request.Request(
        AGENT_PROMPT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=70) as response:
        result = json.loads(response.read().decode("utf-8"))
    prompt = str(result.get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError(f"Agent returned no prompt for {crystal}")
    return prompt


def video_frames(path: Path, target_fps: float) -> tuple[list[bytes], bytes, float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {path}")
    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if source_fps <= 0 or frame_count < 2:
        capture.release()
        raise RuntimeError(f"Invalid video metadata for {path}")
    duration = frame_count / source_fps
    requested_count = max(2, round(duration * target_fps))
    requested_indices = set(
        int(index) for index in np.linspace(0, frame_count - 1, requested_count)
    )
    representative_index = int((frame_count - 1) * 0.78)
    frames: list[bytes] = []
    representative: bytes | None = None
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index == representative_index:
                representative = prepare_frame(frame, ai_reading=True)
            if index in requested_indices:
                frames.append(prepare_frame(frame))
            index += 1
    finally:
        capture.release()
    if representative is None:
        representative = frames[max(0, int(len(frames) * 0.78) - 1)]
    return frames, representative, duration


async def receive_json(websocket, expected: set[str]) -> dict:
    while True:
        message = await websocket.recv()
        if isinstance(message, bytes):
            continue
        payload = json.loads(message)
        if payload.get("type") == "error":
            raise RuntimeError(str(payload.get("message") or "Worker error"))
        if payload.get("type") in expected:
            return payload


async def regenerate(crystal: str, target_fps: float) -> dict:
    path = source_path(crystal)
    if not path.is_file():
        raise FileNotFoundError(path)
    frames, representative, video_duration = await asyncio.to_thread(
        video_frames, path, target_fps
    )
    duration = session_duration(crystal, video_duration)
    prompt = await asyncio.to_thread(request_ai_prompt, crystal, representative)
    started = time.perf_counter()

    async with websockets.connect(WORKER_WS, max_size=None, ping_timeout=60) as websocket:
        await receive_json(websocket, {"status"})
        await websocket.send(json.dumps({"type": "prompt", "value": prompt}))
        await receive_json(websocket, {"prompt"})
        await websocket.send(
            json.dumps(
                {
                    "type": "recording_start",
                    "crystal": crystal,
                    "durationSeconds": duration,
                }
            )
        )
        recording = await receive_json(
            websocket, {"recording_started", "recording_ready", "recording_busy"}
        )
        if recording["type"] == "recording_ready":
            return recording
        if recording["type"] == "recording_busy":
            raise RuntimeError(f"Recording slot is busy for {crystal}")

        for index, frame in enumerate(frames, 1):
            await websocket.send(frame)
            await receive_json(websocket, {"frame"})
            while True:
                generated = await websocket.recv()
                if isinstance(generated, bytes):
                    break
                message = json.loads(generated)
                if message.get("type") == "error":
                    raise RuntimeError(str(message.get("message") or "Worker error"))
            if index == 1 or index % 25 == 0 or index == len(frames):
                print(
                    f"{crystal} frame {index}/{len(frames)}",
                    flush=True,
                )

        await websocket.send(json.dumps({"type": "recording_stop"}))
        result = await receive_json(websocket, {"recording_ready"})

    result["elapsedSeconds"] = round(time.perf_counter() - started, 1)
    result["prompt"] = prompt
    return result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-fps", type=float, default=2.5)
    parser.add_argument(
        "--crystals",
        nargs="*",
        default=[f"ice_crystal_{index:02d}" for index in range(1, 7)],
    )
    args = parser.parse_args()
    summary: list[dict] = []
    for crystal in args.crystals:
        print(f"START {crystal}", flush=True)
        result = await regenerate(crystal, args.target_fps)
        summary.append(result)
        print(json.dumps(result), flush=True)
    print("SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
