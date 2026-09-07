"""Download and verify the Morphogenesis StreamDiffusion baseline."""

from pathlib import Path
import sys
import time

import cv2
from PIL import Image
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STREAMDIFFUSION_ROOT = Path(__file__).resolve().parent / "StreamDiffusion"
sys.path.insert(0, str(STREAMDIFFUSION_ROOT))

from utils.wrapper import StreamDiffusionWrapper  # noqa: E402


def read_crystal_frame(video_path: Path) -> Image.Image:
    capture = cv2.VideoCapture(str(video_path))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count > 1:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 2)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError(f"Could not read a frame from {video_path}")

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width = frame.shape[:2]
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    square = frame[top : top + side, left : left + side]
    return Image.fromarray(square).resize((512, 512), Image.Resampling.LANCZOS)


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; refusing to run the GPU smoke test.")

    source_path = PROJECT_ROOT / "05_shared_data" / "input" / "ice_crystal_01.mp4"
    output_dir = (
        PROJECT_ROOT
        / "09_experiments"
        / "previous_tests"
        / "03_diffusion_imagination"
        / "output"
        / "smoke_test"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    input_image = read_crystal_frame(source_path)
    input_image.save(output_dir / "source_frame.jpg", quality=92)

    stream = StreamDiffusionWrapper(
        model_id_or_path="stabilityai/sd-turbo",
        use_tiny_vae=True,
        device="cuda",
        dtype=torch.float16,
        t_index_list=[35, 45],
        frame_buffer_size=1,
        width=512,
        height=512,
        use_lcm_lora=False,
        output_type="pil",
        warmup=10,
        acceleration="xformers",
        mode="img2img",
        use_denoising_batch=True,
        cfg_type="none",
        use_safety_checker=False,
    )
    prompt = (
        "macro crystalline surface, branching ice structures, translucent mineral "
        "growth, subtle blue-white light, material study, high detail"
    )
    stream.prepare(prompt=prompt, num_inference_steps=50, guidance_scale=1.2)
    image_tensor = stream.preprocess_image(input_image)
    generated = None
    frame_times = []
    # StreamDiffusion is stateful: the first calls fill its denoising stream.
    # Verify a short sequence instead of treating it like a one-shot pipeline.
    for _ in range(6):
        started = time.perf_counter()
        generated = stream(image=image_tensor, prompt=prompt)
        frame_times.append(time.perf_counter() - started)
    assert generated is not None
    generated.save(output_dir / "streamdiffusion_result.jpg", quality=92)

    print(f"python={sys.executable}")
    print(f"gpu={torch.cuda.get_device_name(0)}")
    print(f"source={source_path}")
    print(f"result={output_dir / 'streamdiffusion_result.jpg'}")
    print(f"steady_frame_seconds={sum(frame_times[-3:]) / 3:.4f}")


if __name__ == "__main__":
    main()
