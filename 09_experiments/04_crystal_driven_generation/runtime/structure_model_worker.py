"""Local DINO structure analysis for Direction 03.

Runs on CPU so it can coexist with the StreamDiffusion GPU worker.
It returns structural measurements only and never stores incoming frames.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import numpy as np
import timm
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms


HOST = "127.0.0.1"
PORT = 8892
MAX_BODY = 600_000
os.environ.setdefault("HF_HUB_OFFLINE", "1")
torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))

MODEL = timm.create_model("vit_base_patch16_224.dino", pretrained=True).eval()
TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])
MODEL_LOCK = threading.Lock()
PREVIOUS_CLS: torch.Tensor | None = None


def connected_components(mask: np.ndarray) -> int:
    visited = np.zeros_like(mask, dtype=bool)
    count = 0
    height, width = mask.shape
    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or visited[start_y, start_x]:
                continue
            count += 1
            stack = [(start_x, start_y)]
            visited[start_y, start_x] = True
            while stack:
                x, y = stack.pop()
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and mask[ny, nx]
                        and not visited[ny, nx]
                    ):
                        visited[ny, nx] = True
                        stack.append((nx, ny))
    return count


def analyse_image(data_url: str) -> dict[str, Any]:
    global PREVIOUS_CLS
    prefix = "data:image/jpeg;base64,"
    if not data_url.startswith(prefix):
        raise ValueError("A JPEG data URL is required")
    raw = base64.b64decode(data_url[len(prefix):], validate=True)
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    tensor = TRANSFORM(image).unsqueeze(0)

    with MODEL_LOCK, torch.inference_mode():
        features = MODEL.forward_features(tensor)
        cls = F.normalize(features[:, 0, :], dim=-1)
        patches = features[:, 1:, :]
        patch_unit = F.normalize(patches, dim=-1).reshape(1, 14, 14, -1)
        activation = patches.norm(dim=-1).reshape(14, 14)
        activation = (activation - activation.min()) / (
            activation.max() - activation.min() + 1e-6
        )

        horizontal = (patch_unit[:, :, 1:, :] * patch_unit[:, :, :-1, :]).sum(-1).mean()
        vertical = (patch_unit[:, 1:, :, :] * patch_unit[:, :-1, :, :]).sum(-1).mean()
        coherence = float(((horizontal + vertical) * 0.5).clamp(0, 1))

        if PREVIOUS_CLS is None:
            drift = 0.0
        else:
            drift = float((1 - (cls * PREVIOUS_CLS).sum()).clamp(0, 1))
        PREVIOUS_CLS = cls.detach()

    weights = activation.cpu().numpy()
    weights = weights + 1e-5
    weights /= weights.sum()
    yy, xx = np.mgrid[0:14, 0:14]
    cx = float((xx * weights).sum() / 13)
    cy = float((yy * weights).sum() / 13)
    dx = xx / 13 - cx
    dy = yy / 13 - cy
    covariance = np.array([
        [(weights * dx * dx).sum(), (weights * dx * dy).sum()],
        [(weights * dx * dy).sum(), (weights * dy * dy).sum()],
    ])
    eigenvalues = np.linalg.eigvalsh(covariance)
    anisotropy = float(
        (eigenvalues[-1] - eigenvalues[0])
        / (eigenvalues[-1] + eigenvalues[0] + 1e-6)
    )
    entropy = float(-(weights * np.log(weights)).sum() / math.log(weights.size))
    threshold = float(np.quantile(weights, 0.72))
    fragments = connected_components(weights >= threshold)

    return {
        "model": "vit_base_patch16_224.dino",
        "drift": round(drift, 5),
        "coherence": round(coherence, 5),
        "entropy": round(entropy, 5),
        "anisotropy": round(anisotropy, 5),
        "fragments": fragments,
        "centroid": {"x": round(cx, 5), "y": round(cy, 5)},
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[DINO] {format_string % args}")

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/health":
            self.send_json({"ready": True, "model": "vit_base_patch16_224.dino", "device": "cpu"})
        else:
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/analyze":
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("Frame body is empty or too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self.send_json(analyse_image(str(payload.get("image", ""))))
        except (ValueError, OSError, json.JSONDecodeError) as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)


if __name__ == "__main__":
    print(f"DINO structure worker ready at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
