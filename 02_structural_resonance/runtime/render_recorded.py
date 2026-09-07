"""Build exhibition-ready attention + blob-overlay videos from notebook output.

The notebook's original three-panel MP4 is preserved. This renderer crops the
existing activation and marked-blob panels, keeping the source video behind the
detected boxes, and writes a new VP8 WebM.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = (
    PROJECT_ROOT
    / "09_experiments"
    / "previous_tests"
    / "02_structural_resonance"
    / "output"
)


@dataclass
class Track:
    identifier: int
    box: tuple[int, int, int, int]
    center: tuple[int, int]
    history: list[tuple[int, int]] = field(default_factory=list)
    missed: int = 0


class BlobTracker:
    def __init__(self, max_distance: float = 150.0, max_missed: int = 10) -> None:
        self.max_distance = max_distance
        self.max_missed = max_missed
        self.tracks: dict[int, Track] = {}
        self.next_identifier = 1

    def update(self, boxes: list[tuple[int, int, int, int]]) -> list[Track]:
        detections = [
            ((x + width // 2, y + height // 2), (x, y, width, height))
            for x, y, width, height in boxes
        ]
        unmatched_tracks = set(self.tracks)
        unmatched_detections = set(range(len(detections)))
        candidates: list[tuple[float, int, int]] = []

        for identifier, track in self.tracks.items():
            for detection_index, (center, _) in enumerate(detections):
                distance = float(np.hypot(
                    track.center[0] - center[0],
                    track.center[1] - center[1],
                ))
                if distance <= self.max_distance:
                    candidates.append((distance, identifier, detection_index))

        for _, identifier, detection_index in sorted(candidates):
            if identifier not in unmatched_tracks or detection_index not in unmatched_detections:
                continue
            center, box = detections[detection_index]
            track = self.tracks[identifier]
            track.box = box
            track.center = center
            track.history.append(center)
            track.history = track.history[-32:]
            track.missed = 0
            unmatched_tracks.remove(identifier)
            unmatched_detections.remove(detection_index)

        for identifier in unmatched_tracks:
            self.tracks[identifier].missed += 1

        for detection_index in unmatched_detections:
            center, box = detections[detection_index]
            identifier = self.next_identifier
            self.next_identifier += 1
            self.tracks[identifier] = Track(
                identifier=identifier,
                box=box,
                center=center,
                history=[center],
            )

        self.tracks = {
            identifier: track
            for identifier, track in self.tracks.items()
            if track.missed <= self.max_missed
        }
        return [track for track in self.tracks.values() if track.missed == 0]


def extract_blob_boxes(marked_panel: np.ndarray) -> list[tuple[int, int, int, int]]:
    blue, green, red = cv2.split(marked_panel)
    mask = (
        (blue.astype(np.int16) - red.astype(np.int16) > 42)
        & (green.astype(np.int16) - red.astype(np.int16) > 18)
        & (blue > 145)
        & (green > 115)
    ).astype(np.uint8) * 255
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
    )
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < 16 or height < 16:
            continue
        if width * height < 1600:
            continue
        boxes.append((x, y, width, height))
    return boxes


def render_blob_field(
    size: tuple[int, int],
    tracks: list[Track],
    frame_index: int,
) -> np.ndarray:
    width, height = size
    field = np.zeros((height, width, 3), dtype=np.uint8)
    field[:] = (12, 15, 16)

    grid_color = (22, 29, 31)
    for x in range(0, width, max(1, width // 14)):
        cv2.line(field, (x, 0), (x, height), grid_color, 1, cv2.LINE_AA)
    for y in range(0, height, max(1, height // 14)):
        cv2.line(field, (0, y), (width, y), grid_color, 1, cv2.LINE_AA)

    for track in tracks:
        x, y, box_width, box_height = track.box
        color = (238, 204, 132)
        cv2.rectangle(
            field,
            (x, y),
            (x + box_width, y + box_height),
            color,
            2,
            cv2.LINE_AA,
        )
        if len(track.history) > 1:
            points = np.array(track.history, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(field, [points], False, color, 2, cv2.LINE_AA)
        cv2.circle(field, track.center, 4, color, -1, cv2.LINE_AA)
        cv2.putText(
            field,
            f"B{track.identifier:02d}",
            (x + 5, max(16, y - 7)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        field,
        f"FRAME {frame_index:05d}",
        (18, height - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (134, 145, 146),
        1,
        cv2.LINE_AA,
    )
    return field


def render(crystal_id: str, panel_size: int = 720) -> Path:
    source = OUTPUT_ROOT / crystal_id / "attention_maps" / "attention_video.mp4"
    destination_dir = OUTPUT_ROOT / crystal_id / "exhibition"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "attention_blob.webm"

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open {source}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if source_width < 3 or source_height < 1:
        raise RuntimeError(f"Invalid video dimensions: {source_width}x{source_height}")

    panel_width = source_width // 3
    writer = cv2.VideoWriter(
        str(destination),
        cv2.VideoWriter_fourcc(*"VP80"),
        fps,
        (panel_size * 2, panel_size),
    )
    if not writer.isOpened():
        raise RuntimeError("VP8 VideoWriter could not be opened")

    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            activation = frame[:, panel_width:panel_width * 2]
            marked = frame[:, panel_width * 2:panel_width * 3]

            activation = cv2.resize(
                activation,
                (panel_size, panel_size),
                interpolation=cv2.INTER_AREA,
            )
            marked = cv2.resize(
                marked,
                (panel_size, panel_size),
                interpolation=cv2.INTER_AREA,
            )
            combined = np.hstack([activation, marked])
            writer.write(combined)

            frame_index += 1
            if frame_index % 50 == 0 or frame_index == frame_total:
                print(f"{crystal_id}: {frame_index}/{frame_total}", flush=True)
    finally:
        capture.release()
        writer.release()

    print(f"written: {destination}", flush=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "crystal_ids",
        nargs="*",
        default=["ice_crystal_01", "ice_crystal_02"],
    )
    parser.add_argument("--panel-size", type=int, default=720)
    args = parser.parse_args()
    for crystal_id in args.crystal_ids:
        render(crystal_id, args.panel_size)


if __name__ == "__main__":
    main()
