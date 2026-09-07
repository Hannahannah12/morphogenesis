"""Local GPU worker for the Morphogenesis StreamDiffusion exhibition page."""

from __future__ import annotations

import argparse
import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
from PIL import Image
import torch
import uvicorn


RUNTIME_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RUNTIME_DIR.parents[1]
STREAMDIFFUSION_ROOT = RUNTIME_DIR / "StreamDiffusion"
# The repository uses a src-layout. Keep the local exhibition runtime
# self-contained even when the editable package registration is unavailable.
sys.path.insert(0, str(STREAMDIFFUSION_ROOT / "src"))
sys.path.insert(0, str(STREAMDIFFUSION_ROOT))

# Exhibition playback must keep working without an internet connection. The
# model and TinyVAE are installed in the local Hugging Face cache already.
os.environ.setdefault("HF_HOME", str(RUNTIME_DIR.parent / "models" / "huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("DIFFUSERS_OFFLINE", "1")

from utils.wrapper import StreamDiffusionWrapper  # noqa: E402


DEFAULT_PROMPT = (
    "preserve the exact branching topology, growth front and local density of "
    "the source; reinterpret it as non-representational translucent ice crystal "
    "membranes and fine dendritic frost filaments, pale silver-blue and clear "
    "glass tones, dark neutral depth, soft raking light and delicate microtexture; "
    "entirely non-anthropomorphic, with no people or human silhouettes"
)

TRANSFORMATION_PROFILE = "structure-led-varied-material-worlds"
NEGATIVE_PROMPT = (
    "centered composition, radial symmetry, circular framing, halo, vortex, "
    "unrelated composition, loss of source branching, structure drift, random objects, "
    "literal photographic colour copying, neon rainbow, psychedelic palette, "
    "competing saturated hues, oversaturated cyan, oversaturated orange, "
    "tree, forest, branches as trees, recognizable objects, characters, "
    "person, people, human, humanoid, "
    "human anatomy, body, face, portrait, head, arms, legs, limbs, standing figure, "
    "human silhouette, person-shaped shadow, figure-like focal subject, text, logo"
)
INFERENCE_STEPS = 50
GUIDANCE_SCALE = 1.45
DELTA = 0.5
FRAME_SIZE = 640
CRYSTAL_NAME = re.compile(r"^ice_crystal_\d{2}$")
SAFETY_PREFIX = "people-free, non-anthropomorphic scene; "
recording_slots: set[Path] = set()
recording_slots_lock = threading.Lock()


def enforce_visual_safety(prompt: str) -> str:
    """Keep exhibition prompts structural and prevent accidental human figures."""
    compact = " ".join(prompt.split()).strip() or DEFAULT_PROMPT
    if "non-anthropomorphic" not in compact.lower():
        compact = f"{SAFETY_PREFIX}{compact}"
    return compact[:600]


class DiffusionRecording:
    """Buffer one generated loop and encode it to the source clip duration."""

    def __init__(self, crystal: str, duration_seconds: float) -> None:
        if not CRYSTAL_NAME.fullmatch(crystal):
            raise ValueError("Crystal must be named like ice_crystal_05")
        if not 1 <= duration_seconds <= 600:
            raise ValueError("Recording duration must be between 1 and 600 seconds")
        self.crystal = crystal
        self.duration_seconds = float(duration_seconds)
        self.frames: list[bytes] = []
        self.destination = (
            PROJECT_ROOT
            / "05_shared_data"
            / "exhibition"
            / crystal
            / "03_diffusion_imagination"
            / "diffusion_capture.mp4"
        )
        self.url = "/" + self.destination.relative_to(PROJECT_ROOT).as_posix()

    def add(self, image_bytes: bytes) -> None:
        self.frames.append(bytes(image_bytes))

    def finish(self) -> dict[str, Any]:
        if len(self.frames) < 2:
            raise RuntimeError("Not enough generated frames were recorded")
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.destination.with_name("diffusion_capture.pending.mp4")
        temporary.unlink(missing_ok=True)
        first = cv2.imdecode(
            np.frombuffer(self.frames[0], dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if first is None:
            raise RuntimeError("The first generated recording frame is invalid")
        height, width = first.shape[:2]
        output_fps = len(self.frames) / self.duration_seconds
        writer = cv2.VideoWriter(
            str(temporary),
            cv2.VideoWriter_fourcc(*"avc1"),
            output_fps,
            (width, height),
        )
        if not writer.isOpened():
            writer.release()
            raise RuntimeError("Could not open the H.264 Diffusion backup writer")
        try:
            for encoded in self.frames:
                frame = cv2.imdecode(
                    np.frombuffer(encoded, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if frame is None:
                    continue
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(
                        frame,
                        (width, height),
                        interpolation=cv2.INTER_AREA,
                    )
                writer.write(frame)
        finally:
            writer.release()
        os.replace(temporary, self.destination)
        metadata = {
            "crystal": self.crystal,
            "video": self.destination.name,
            "url": self.url,
            "durationSeconds": round(self.duration_seconds, 3),
            "frames": len(self.frames),
            "fps": round(output_fps, 4),
            "resolution": f"{width}x{height}",
            "codec": "H.264",
            "createdAtEpoch": round(time.time(), 3),
        }
        (
            self.destination.parent / "recording.json"
        ).write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        self.frames.clear()
        return metadata


def claim_recording(
    crystal: str,
    duration_seconds: float,
) -> tuple[DiffusionRecording | None, str]:
    recording = DiffusionRecording(crystal, duration_seconds)
    if recording.destination.exists():
        return None, "exists"
    with recording_slots_lock:
        if recording.destination in recording_slots:
            return None, "busy"
        recording_slots.add(recording.destination)
    return recording, "started"


def release_recording(recording: DiffusionRecording | None) -> None:
    if recording is None:
        return
    with recording_slots_lock:
        recording_slots.discard(recording.destination)


class RuntimeState:
    def __init__(self) -> None:
        self.status = "starting"
        self.error: str | None = None
        self.pipeline: StreamDiffusionWrapper | None = None
        self.gpu = "detecting"
        self.clients = 0
        self.frames = 0
        self.average_ms: float | None = None
        self.prompt_resets = 0
        self.current_prompt = DEFAULT_PROMPT
        self.started_at = time.time()
        self.lock = threading.Lock()
        self.inference_lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            fps = 1000 / self.average_ms if self.average_ms else None
            return {
                "service": "Morphogenesis StreamDiffusion",
                "pid": os.getpid(),
                "status": self.status,
                "ready": self.status == "ready",
                "model": "stabilityai/sd-turbo",
                "acceleration": "xformers",
                "transformationProfile": TRANSFORMATION_PROFILE,
                "denoisingIndices": [22, 35, 45],
                "structureGuide": "contour-only-no-source-composite",
                "growthContourGuide": "temporal-formation-front-masked-v4",
                "resolution": f"{FRAME_SIZE}x{FRAME_SIZE}",
                "gpu": self.gpu,
                "clients": self.clients,
                "frames": self.frames,
                "averageFrameMs": round(self.average_ms, 1) if self.average_ms else None,
                "fps": round(fps, 1) if fps else None,
                "visualMemory": "reset-on-prompt",
                "promptResets": self.prompt_resets,
                "error": self.error,
                "uptimeSeconds": round(time.time() - self.started_at, 1),
            }


state = RuntimeState()
app = FastAPI(title="Morphogenesis StreamDiffusion", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_origin_regex=r"http://(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}):8080",
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def load_pipeline() -> None:
    try:
        with state.lock:
            state.status = "loading_model"
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. Check NVIDIA driver and CUDA PyTorch.")
        state.gpu = torch.cuda.get_device_name(0)
        pipeline = StreamDiffusionWrapper(
            model_id_or_path="stabilityai/sd-turbo",
            use_tiny_vae=True,
            device="cuda",
            dtype=torch.float16,
            # Leave enough room for material imagination without allowing the
            # generated palette to detach completely from the observed frame.
            t_index_list=[22, 35, 45],
            frame_buffer_size=1,
            width=FRAME_SIZE,
            height=FRAME_SIZE,
            use_lcm_lora=False,
            output_type="pil",
            warmup=10,
            acceleration="xformers",
            mode="img2img",
            use_denoising_batch=True,
            cfg_type="self",
            use_safety_checker=False,
        )
        pipeline.prepare(
            prompt=DEFAULT_PROMPT,
            negative_prompt=NEGATIVE_PROMPT,
            num_inference_steps=INFERENCE_STEPS,
            guidance_scale=GUIDANCE_SCALE,
            delta=DELTA,
        )
        with state.lock:
            state.pipeline = pipeline
            state.status = "ready"
            state.error = None
    except Exception as error:  # The health endpoint must remain available on failure.
        with state.lock:
            state.status = "error"
            state.error = f"{type(error).__name__}: {error}"


class GrowthContourGuide:
    """Track the formation front so imagination appears only as crystal grows."""

    def __init__(self) -> None:
        self.baseline: np.ndarray | None = None
        self.accumulated: np.ndarray | None = None

    def composite(
        self,
        generated_rgb: np.ndarray,
        source_rgb: np.ndarray,
    ) -> np.ndarray:
        source_gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY)
        current = cv2.GaussianBlur(source_gray, (0, 0), 3.0)
        if self.baseline is None:
            self.baseline = current.copy()
            self.accumulated = np.zeros_like(current, dtype=np.float32)

        difference = np.maximum(
            current.astype(np.float32) - self.baseline.astype(np.float32),
            0,
        )
        raw_mask = (difference > 8).astype(np.uint8) * 255
        raw_mask = cv2.morphologyEx(
            raw_mask,
            cv2.MORPH_OPEN,
            np.ones((3, 3), dtype=np.uint8),
        )
        raw_mask = cv2.morphologyEx(
            raw_mask,
            cv2.MORPH_CLOSE,
            np.ones((11, 11), dtype=np.uint8),
        )

        component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            raw_mask
        )
        formation = np.zeros_like(raw_mask)
        minimum_area = max(240, int(raw_mask.size * 0.0012))
        for component in range(1, component_count):
            if stats[component, cv2.CC_STAT_AREA] >= minimum_area:
                formation[labels == component] = 255

        # A return to the baseline marks an archive-loop restart. Clearing here
        # lets the imagined material grow again instead of remaining full-frame.
        baseline_distance = float(
            np.mean(
                np.abs(
                    current.astype(np.float32)
                    - self.baseline.astype(np.float32)
                )
            )
        )
        current_formation_area = float(formation.mean()) / 255
        assert self.accumulated is not None
        if (
            (
                baseline_distance < 6.5
                or current_formation_area < 0.018
            )
            and float(self.accumulated.mean()) > 0.06
        ):
            self.accumulated.fill(0)
        self.accumulated = np.maximum(
            self.accumulated * 0.997,
            formation.astype(np.float32) / 255,
        )

        binary = (self.accumulated > 0.22).astype(np.uint8) * 255
        soft_mask = cv2.GaussianBlur(
            self.accumulated,
            (0, 0),
            2.2,
        )
        soft_mask = np.clip(soft_mask, 0, 1) ** 0.90
        mask_rgb = soft_mask[:, :, None]

        # The source determines only where growth is occurring. Never composite
        # its pixels or colour into the exhibition result: outside the advancing
        # front, show a slightly quieter version of the generated image itself.
        generated_float = generated_rgb.astype(np.float32)
        outside = generated_float * 0.94
        composited = (
            outside * (1 - mask_rgb)
            + generated_float * mask_rgb
        )

        # Reinforce the actual outer growth boundary as a narrow luminance
        # contour without imposing a new colour on the model's material.
        front = cv2.morphologyEx(
            binary,
            cv2.MORPH_GRADIENT,
            np.ones((13, 13), dtype=np.uint8),
        ).astype(np.float32) / 255
        front = cv2.GaussianBlur(front, (0, 0), 1.4)[:, :, None]
        generated_gray = cv2.cvtColor(generated_rgb, cv2.COLOR_RGB2GRAY)
        front_luminance = np.repeat(
            np.clip(
                generated_gray.astype(np.float32) * 1.18 + 6,
                0,
                255,
            )[:, :, None],
            3,
            axis=2,
        )
        front_strength = np.clip(front * 0.20, 0, 0.20)
        composited = (
            composited * (1 - front_strength)
            + front_luminance * front_strength
        )
        return np.clip(composited, 0, 255).astype(np.uint8)


def apply_source_structure_guide(
    output: Image.Image,
    source: Image.Image,
    growth_guide: GrowthContourGuide,
) -> Image.Image:
    """Carry source morphology while keeping generated colour deliberately calm."""
    source_rgb = np.asarray(source, dtype=np.uint8)
    output_rgb = np.asarray(output.convert("RGB"), dtype=np.uint8)
    if output_rgb.shape[:2] != source_rgb.shape[:2]:
        output_rgb = cv2.resize(
            output_rgb,
            (source_rgb.shape[1], source_rgb.shape[0]),
            interpolation=cv2.INTER_CUBIC,
        )

    source_gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY)
    source_structure = cv2.createCLAHE(
        clipLimit=1.35,
        tileGridSize=(8, 8),
    ).apply(source_gray)
    source_blur = cv2.GaussianBlur(source_structure, (0, 0), 2.2)
    source_detail = (
        source_structure.astype(np.float32)
        - source_blur.astype(np.float32)
    )
    gradient_x = cv2.Sobel(
        source_structure,
        cv2.CV_32F,
        1,
        0,
        ksize=3,
    )
    gradient_y = cv2.Sobel(
        source_structure,
        cv2.CV_32F,
        0,
        1,
        ksize=3,
    )
    source_edges = cv2.magnitude(gradient_x, gradient_y)
    edge_scale = float(np.percentile(source_edges, 98)) or 1.0
    source_edges = np.clip(source_edges / edge_scale * 255, 0, 255)

    output_lab = cv2.cvtColor(output_rgb, cv2.COLOR_RGB2LAB)
    output_l = output_lab[:, :, 0].astype(np.float32)
    guided_l = (
        output_l
        + source_detail * 0.16
        + source_edges * 0.035
    )
    output_lab[:, :, 0] = np.clip(guided_l, 0, 255).astype(np.uint8)
    output_chroma = output_lab[:, :, 1:3].astype(np.float32) - 128
    output_lab[:, :, 1:3] = np.clip(
        128 + output_chroma * 1.06,
        0,
        255,
    ).astype(np.uint8)
    guided_rgb = cv2.cvtColor(output_lab, cv2.COLOR_LAB2RGB)
    soft = cv2.GaussianBlur(guided_rgb, (0, 0), 0.75)
    guided_rgb = cv2.addWeighted(guided_rgb, 1.24, soft, -0.24, 0)
    guided_rgb = growth_guide.composite(guided_rgb, source_rgb)
    return Image.fromarray(guided_rgb)


def generate_frame(
    image_bytes: bytes,
    prompt: str,
    growth_guide: GrowthContourGuide,
) -> tuple[bytes, float]:
    pipeline = state.pipeline
    if pipeline is None:
        raise RuntimeError("Model is not ready")

    source = (
        Image.open(BytesIO(image_bytes))
        .convert("RGB")
        .resize((FRAME_SIZE, FRAME_SIZE), Image.Resampling.LANCZOS)
    )
    tensor = pipeline.preprocess_image(source)
    started = time.perf_counter()
    with state.inference_lock:
        output = pipeline(image=tensor, prompt=prompt)
    output = apply_source_structure_guide(output, source, growth_guide)
    elapsed_ms = (time.perf_counter() - started) * 1000

    buffer = BytesIO()
    output.save(buffer, format="JPEG", quality=88, optimize=False)
    with state.lock:
        state.frames += 1
        state.average_ms = (
            elapsed_ms
            if state.average_ms is None
            else state.average_ms * 0.85 + elapsed_ms * 0.15
        )
    return buffer.getvalue(), elapsed_ms


def reset_visual_memory(prompt: str) -> None:
    """Apply a new prompt without carrying the previous composition forward."""
    pipeline = state.pipeline
    if pipeline is None:
        raise RuntimeError("Model is not ready")

    with state.inference_lock:
        # StreamDiffusion normally keeps latent/noise buffers between frames.
        # Re-preparing on a real prompt change clears those buffers. Rotating the
        # seed also prevents one fixed noise layout from repeatedly suggesting
        # the same central/radial composition.
        with state.lock:
            next_reset = state.prompt_resets + 1
        pipeline.stream.prepare(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            num_inference_steps=INFERENCE_STEPS,
            guidance_scale=GUIDANCE_SCALE,
            delta=DELTA,
            seed=2 + next_reset,
        )
        with state.lock:
            state.prompt_resets = next_reset
            state.current_prompt = prompt


@app.on_event("startup")
async def startup() -> None:
    threading.Thread(target=load_pipeline, name="streamdiffusion-loader", daemon=True).start()


@app.get("/")
@app.get("/health")
async def health() -> dict[str, Any]:
    return state.snapshot()


@app.websocket("/ws")
async def websocket_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    prompt = enforce_visual_safety(DEFAULT_PROMPT)
    primed = False
    growth_guide = GrowthContourGuide()
    recording: DiffusionRecording | None = None
    with state.lock:
        state.clients += 1
    try:
        await websocket.send_json({"type": "status", **state.snapshot()})
        while True:
            message = await websocket.receive()
            if message.get("text") is not None:
                payload = json.loads(message["text"])
                if payload.get("type") == "prompt":
                    candidate = str(payload.get("value", "")).strip()
                    next_prompt = enforce_visual_safety(candidate)
                    changed = next_prompt != prompt
                    prompt = next_prompt
                    if changed and state.status == "ready":
                        await asyncio.to_thread(reset_visual_memory, prompt)
                        primed = False
                    await websocket.send_json(
                        {
                            "type": "prompt",
                            "accepted": True,
                            "visualMemoryReset": changed and state.status == "ready",
                        }
                    )
                elif payload.get("type") == "recording_start":
                    if recording is not None:
                        await websocket.send_json(
                            {"type": "recording_busy", "crystal": recording.crystal}
                        )
                        continue
                    recording, recording_state = claim_recording(
                        str(payload.get("crystal", "")),
                        float(payload.get("durationSeconds", 0)),
                    )
                    if recording_state == "exists":
                        crystal = str(payload.get("crystal", ""))
                        destination = (
                            PROJECT_ROOT
                            / "05_shared_data"
                            / "exhibition"
                            / crystal
                            / "03_diffusion_imagination"
                            / "diffusion_capture.mp4"
                        )
                        await websocket.send_json(
                            {
                                "type": "recording_ready",
                                "crystal": crystal,
                                "url": "/" + destination.relative_to(PROJECT_ROOT).as_posix(),
                                "existing": True,
                            }
                        )
                    elif recording_state == "busy":
                        await websocket.send_json(
                            {
                                "type": "recording_busy",
                                "crystal": str(payload.get("crystal", "")),
                            }
                        )
                    else:
                        await websocket.send_json(
                            {
                                "type": "recording_started",
                                "crystal": recording.crystal,
                                "durationSeconds": recording.duration_seconds,
                            }
                        )
                elif payload.get("type") == "recording_stop":
                    if recording is None:
                        continue
                    completed_recording = recording
                    recording = None
                    try:
                        metadata = await asyncio.to_thread(
                            completed_recording.finish
                        )
                        await websocket.send_json(
                            {"type": "recording_ready", **metadata}
                        )
                    finally:
                        release_recording(completed_recording)
                elif payload.get("type") == "health":
                    await websocket.send_json({"type": "status", **state.snapshot()})
                continue

            image_bytes = message.get("bytes")
            if not image_bytes:
                continue
            if state.status != "ready":
                await websocket.send_json({"type": "status", **state.snapshot()})
                continue

            # Fill the stateful denoising stream before exposing the first result.
            repeats = 4 if not primed else 1
            result = b""
            elapsed_ms = 0.0
            for _ in range(repeats):
                result, elapsed_ms = await asyncio.to_thread(
                    generate_frame,
                    image_bytes,
                    prompt,
                    growth_guide,
                )
            primed = True
            if recording is not None:
                recording.add(result)
            await websocket.send_json(
                {
                    "type": "frame",
                    "frameMs": round(elapsed_ms, 1),
                    "fps": round(1000 / elapsed_ms, 1) if elapsed_ms else None,
                }
            )
            await websocket.send_bytes(result)
    except WebSocketDisconnect:
        pass
    except Exception as error:
        try:
            await websocket.send_json({"type": "error", "message": str(error)})
        except Exception:
            pass
    finally:
        release_recording(recording)
        with state.lock:
            state.clients = max(0, state.clients - 1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Morphogenesis StreamDiffusion worker")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8091)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
