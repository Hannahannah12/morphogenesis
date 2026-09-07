"""Create browser-ready copies of the material-analysis video outputs.

The notebook exports remain untouched. This script writes compact VP8/WebM
exhibition copies into a separate output directory for reliable browser playback.
"""

import argparse
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "09_experiments"
    / "previous_tests"
    / "01_material_analysis"
    / "output"
)

SEQUENCES = {
    "01_edge.webm": ("edge.mp4",),
    "02_threshold.webm": ("threshold.mp4",),
}
TARGET_FPS = 15.0
MAX_EDGE = 720
SPACETIME_WIDTH = 1440


def find_source(source_dir: Path, candidates: tuple[str, ...]) -> Path:
    for name in candidates:
        candidate = source_dir / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing analysis video: {', '.join(candidates)}")


def render_sequence(
    source_dir: Path,
    output_dir: Path,
    output_name: str,
    candidates: tuple[str, ...],
) -> None:
    source_path = find_source(source_dir, candidates)
    output_path = output_dir / output_name
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open {source_path}")

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, MAX_EDGE / max(source_width, source_height))
    width = round(source_width * scale / 2) * 2
    height = round(source_height * scale / 2) * 2
    sample_every = max(1, round(source_fps / TARGET_FPS))
    fps = source_fps / sample_every
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"VP80"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("VP8/WebM output is unavailable in this OpenCV build")

    frame_index = 0
    while True:
        available, frame = capture.read()
        if not available:
            break
        if frame_index % sample_every == 0:
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            writer.write(frame)
        frame_index += 1
        if frame_index % 150 == 0:
            print(f"{output_name}: {frame_index}/{frame_total}")

    capture.release()
    writer.release()
    print(f"Saved {output_path}")


def render_spacetime_rows(source_dir: Path, output_dir: Path) -> None:
    source_path = source_dir / "spacetime_4rows.mp4"
    reference_path = source_dir / "spacetime_4rows.png"
    output_path = output_dir / "03_spacetime.webm"
    reference = cv2.imread(str(reference_path))
    capture = cv2.VideoCapture(str(source_path))
    if reference is None or not capture.isOpened():
        raise RuntimeError("The four-row space-time image and video are required")

    reference_height, reference_width = reference.shape[:2]
    target_height = round(reference_height * SPACETIME_WIDTH / reference_width / 2) * 2
    scale_x = SPACETIME_WIDTH / reference_width
    scale_y = target_height / reference_height
    background = cv2.resize(
        reference,
        (SPACETIME_WIDTH, target_height),
        interpolation=cv2.INTER_AREA,
    )

    gray_reference = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    mask = (gray_reference < 245).astype("uint8") * 255
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    panels = sorted(
        (
            (int(x), int(y), int(width), int(height))
            for x, y, width, height, area in stats[1:]
            if area > 1_000_000
        ),
        key=lambda box: box[1],
    )
    if len(panels) != 4:
        capture.release()
        raise RuntimeError("Unable to locate the four space-time image panels")

    target_panels = []
    for x, y, width, height in panels:
        target_box = (
            round(x * scale_x),
            round(y * scale_y),
            round(width * scale_x),
            round(height * scale_y),
        )
        target_panels.append(target_box)
        tx, ty, tw, th = target_box
        background[ty : ty + th, tx : tx + tw] = 255

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    panel_height = source_height // 4
    sample_every = max(1, round(source_fps / TARGET_FPS))
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"VP80"),
        source_fps / sample_every,
        (SPACETIME_WIDTH, target_height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("VP8/WebM output is unavailable in this OpenCV build")

    frame_index = 0
    while True:
        available, frame = capture.read()
        if not available:
            break
        if frame_index % sample_every == 0:
            canvas = background.copy()
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for panel_index, (tx, ty, tw, th) in enumerate(target_panels):
                start = panel_index * panel_height
                source_panel = 255 - gray_frame[start : start + panel_height]
                rendered_panel = cv2.resize(
                    source_panel,
                    (tw, th),
                    interpolation=cv2.INTER_AREA,
                )
                canvas[ty : ty + th, tx : tx + tw] = cv2.cvtColor(
                    rendered_panel,
                    cv2.COLOR_GRAY2BGR,
                )
            writer.write(canvas)
        frame_index += 1
        if frame_index % 150 == 0:
            print(f"03_spacetime.webm: {frame_index}/{frame_total}")

    capture.release()
    writer.release()
    print(f"Saved {output_path}")


def render_motion_history(crystal: str, output_dir: Path) -> None:
    input_dir = PROJECT_ROOT / "05_shared_data" / "input"
    source_path = input_dir / f"{crystal}_resized.mp4"
    if not source_path.exists():
        source_path = input_dir / f"{crystal}.mp4"
    output_path = output_dir / "04_motion.webm"
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open {source_path}")

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, MAX_EDGE / max(source_width, source_height))
    width = round(source_width * scale / 2) * 2
    height = round(source_height * scale / 2) * 2
    sample_every = max(1, round(source_fps / TARGET_FPS))
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"VP80"),
        source_fps / sample_every,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("VP8/WebM output is unavailable in this OpenCV build")

    available, previous = capture.read()
    if not available:
        capture.release()
        writer.release()
        raise RuntimeError("The source video contains no readable frames")
    previous_gray = cv2.GaussianBlur(
        cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY),
        (5, 5),
        0,
    )
    history = cv2.resize(
        previous_gray,
        (width, height),
        interpolation=cv2.INTER_AREA,
    ).astype("float32") * 0

    frame_index = 1
    while True:
        available, frame = capture.read()
        if not available:
            break
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        difference = cv2.absdiff(previous_gray, gray)
        previous_gray = gray
        difference = cv2.resize(
            difference,
            (width, height),
            interpolation=cv2.INTER_AREA,
        )
        motion = cv2.convertScaleAbs(difference, alpha=9.0)
        motion[motion < 7] = 0
        history *= 0.93
        history = cv2.max(history, motion.astype("float32"))

        if frame_index % sample_every == 0:
            level = (history.clip(0, 255) / 255.0) ** 0.55
            blue = 8 + level * 247
            green = 3 + (level**0.9) * 165
            red = (level**1.25) * 55
            coloured = cv2.merge(
                [
                    blue.astype("uint8"),
                    green.astype("uint8"),
                    red.astype("uint8"),
                ]
            )
            writer.write(coloured)
        frame_index += 1
        if frame_index % 150 == 0:
            print(f"04_motion.webm: {frame_index}/{frame_total}")

    capture.release()
    writer.release()
    print(f"Saved {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crystal", default="ice_crystal_01")
    parser.add_argument(
        "--only",
        choices=("all", "spacetime", "motion"),
        default="all",
        help="Render the complete website set or only the four-row space-time video.",
    )
    args = parser.parse_args()
    crystal = args.crystal.strip()
    crystal_number = crystal.removeprefix("ice_crystal_")
    if (
        not crystal.startswith("ice_crystal_")
        or len(crystal_number) != 2
        or not crystal_number.isdigit()
    ):
        raise ValueError("Crystal must use a name such as ice_crystal_01 or ice_crystal_02")

    crystal_dir = PREVIOUS_OUTPUT_ROOT / crystal
    source_dir = crystal_dir / "analysis"
    output_dir = crystal_dir / "exhibition"
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.only == "all":
        for output_name, candidates in SEQUENCES.items():
            render_sequence(source_dir, output_dir, output_name, candidates)
    if args.only in {"all", "spacetime"}:
        render_spacetime_rows(source_dir, output_dir)
    if args.only in {"all", "motion"}:
        render_motion_history(crystal, output_dir)


if __name__ == "__main__":
    main()
