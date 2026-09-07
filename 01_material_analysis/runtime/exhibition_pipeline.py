"""Notebook-faithful Material Analysis for the Exhibition Pipeline.

The notebook remains the method authority. This module changes only execution:
all four methods advance in one pass and return browser-ready frames. It does
not generate notebook contact sheets or research master files.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np


SQUARE_OUTPUT_SIZE = (720, 720)
LANDSCAPE_OUTPUT_SIZE = (1280, 720)


def exhibition_canvas_size(frame: np.ndarray) -> tuple[int, int]:
    height, width = frame.shape[:2]
    aspect = width / max(1, height)
    if 0.9 <= aspect <= 1.1:
        return SQUARE_OUTPUT_SIZE
    return LANDSCAPE_OUTPUT_SIZE


def fit_frame(
    frame: np.ndarray,
    size: tuple[int, int],
    background: int = 0,
) -> np.ndarray:
    """Fit the complete frame without stretching or centre cropping."""
    target_width, target_height = size
    height, width = frame.shape[:2]
    scale = min(target_width / width, target_height / height)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    interpolation = cv2.INTER_AREA if scale <= 1 else cv2.INTER_CUBIC
    resized = cv2.resize(
        frame,
        (resized_width, resized_height),
        interpolation=interpolation,
    )
    canvas = np.full(
        (target_height, target_width, 3),
        background,
        dtype=np.uint8,
    )
    x = (target_width - resized_width) // 2
    y = (target_height - resized_height) // 2
    canvas[y : y + resized_height, x : x + resized_width] = resized
    return canvas


def black_blue(level: np.ndarray) -> np.ndarray:
    """Deep-blue motion palette applied after Notebook thresholding."""
    normalized = np.clip(level.astype(np.float32), 0, 1)
    lifted = np.power(normalized, 0.48)
    blue = lifted * 255
    green = np.power(lifted, 1.05) * 112
    red = np.power(lifted, 1.35) * 18
    return cv2.merge(
        [
            blue.astype(np.uint8),
            green.astype(np.uint8),
            red.astype(np.uint8),
        ]
    )


@dataclass
class ExhibitionFrames:
    edge: np.ndarray
    threshold: np.ndarray
    spacetime: np.ndarray
    motion: np.ndarray

    def as_dict(self) -> dict[str, np.ndarray]:
        return {
            "edge": self.edge,
            "threshold": self.threshold,
            "spacetime": self.spacetime,
            "motion": self.motion,
        }


@dataclass
class NotebookFrames:
    """Raw grayscale results before the exhibition palette is applied."""

    edge: np.ndarray
    threshold: np.ndarray
    spacetime: np.ndarray
    motion: np.ndarray


class ExhibitionMaterialProcessor:
    """One source frame in, four Notebook-derived exhibition frames out."""

    def __init__(
        self,
        first_frame: np.ndarray,
        total_frames: int,
        output_size: tuple[int, int] | None = None,
    ) -> None:
        self.output_size = output_size or exhibition_canvas_size(first_frame)
        self.width, self.height = self.output_size
        self.analysis_height, self.analysis_width = first_frame.shape[:2]
        self.total_frames = max(1, int(total_frames))
        first_gray = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)

        # Notebook cells 2/3: first source frame is the fixed background.
        self.background = cv2.GaussianBlur(first_gray, (5, 5), 0)
        # Notebook cells 13/14: motion compares strictly adjacent frames.
        self.previous_gray = first_gray
        # Exhibition presentation keeps the Notebook threshold but observes a
        # short 12-frame interval so slow crystal growth remains visible.
        self.motion_observation = deque([first_gray], maxlen=6)
        self.motion_history = np.zeros(
            (self.analysis_height, self.analysis_width),
            dtype=np.float32,
        )
        self.latest_motion_color = np.zeros(
            (self.analysis_height, self.analysis_width, 3),
            dtype=np.uint8,
        )
        self.frame_index = 0

        self.clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(8, 8))
        self.edge_kernel = np.ones((3, 3), np.uint8)
        self.threshold_kernel = np.ones((2, 2), np.uint8)

        # Notebook cells 10/11: rows 200, 400, 600 and 800 in a 1080px frame.
        self.rows = [
            min(
                self.analysis_height - 1,
                round(self.analysis_height * row / 1080),
            )
            for row in (200, 400, 600, 800)
        ]
        self.row_labels = (200, 400, 600, 800)
        self.spacetime_canvas = np.zeros(
            (self.total_frames * 4, self.analysis_width),
            dtype=np.uint8,
        )
        self.spacetime_color_canvas = np.full(
            (self.total_frames * 4, self.analysis_width, 3),
            255,
            dtype=np.uint8,
        )
        self.latest_spacetime_color = np.full(
            (self.height, self.width, 3),
            255,
            dtype=np.uint8,
        )

    def process(self, raw_frame: np.ndarray) -> ExhibitionFrames:
        notebook = self.process_notebook(raw_frame)
        # Preserve the Notebook's white-background binary presentation.
        return ExhibitionFrames(
            edge=fit_frame(
                cv2.cvtColor(notebook.edge, cv2.COLOR_GRAY2BGR),
                self.output_size,
                background=255,
            ),
            threshold=fit_frame(
                cv2.cvtColor(notebook.threshold, cv2.COLOR_GRAY2BGR),
                self.output_size,
                background=255,
            ),
            spacetime=self.latest_spacetime_color,
            motion=fit_frame(self.latest_motion_color, self.output_size),
        )

    def process_notebook(self, raw_frame: np.ndarray) -> NotebookFrames:
        """Return the exact Notebook method outputs for one source frame."""
        frame = raw_frame
        if frame.shape[:2] != (self.analysis_height, self.analysis_width):
            frame = cv2.resize(
                frame,
                (self.analysis_width, self.analysis_height),
                interpolation=cv2.INTER_AREA,
            )
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # EDGE — exact parameters from crystal_analysis.ipynb cells 2/3.
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        difference = cv2.absdiff(self.background, blurred)
        _, changed = cv2.threshold(difference, 25, 255, cv2.THRESH_BINARY)
        changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, self.edge_kernel)
        changed = cv2.morphologyEx(changed, cv2.MORPH_CLOSE, self.edge_kernel)
        edges = cv2.Canny(changed, 10, 50)
        edges_inv = cv2.bitwise_not(edges)

        # THRESHOLD — exact parameters from cells 5/6.
        enhanced = self.clahe.apply(gray)
        threshold_blur = cv2.GaussianBlur(enhanced, (3, 3), 0)
        threshold = cv2.adaptiveThreshold(
            threshold_blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            21,
            5,
        )
        threshold = cv2.morphologyEx(
            threshold,
            cv2.MORPH_OPEN,
            self.threshold_kernel,
        )

        # MOTION — adjacent-frame absdiff and threshold 15, cells 13/14.
        motion_difference = cv2.absdiff(self.previous_gray, gray)
        _, motion_level = cv2.threshold(
            motion_difference,
            15,
            255,
            cv2.THRESH_TOZERO,
        )
        self.previous_gray = gray

        display_difference = cv2.absdiff(self.motion_observation[0], gray)
        _, display_motion = cv2.threshold(
            display_difference,
            15,
            255,
            cv2.THRESH_TOZERO,
        )
        self.motion_history *= 0.93
        self.motion_history = np.maximum(
            self.motion_history,
            display_motion.astype(np.float32),
        )
        self.latest_motion_color = black_blue(self.motion_history / 255)
        self.motion_observation.append(gray)

        # SPACE-TIME — same growing four-row canvas as cells 10/11. Knowing the
        # retained frame count lets us do this in one pass instead of rereading.
        row_position = min(self.frame_index, self.total_frames - 1)
        for panel_index, row in enumerate(self.rows):
            self.spacetime_canvas[
                panel_index * self.total_frames + row_position,
                :,
            ] = gray[row, :]
            self.spacetime_color_canvas[
                panel_index * self.total_frames + row_position,
                :,
            ] = frame[row, :]
        spacetime = cv2.resize(
            self.spacetime_canvas,
            self.output_size,
            interpolation=cv2.INTER_AREA,
        )
        # Exhibition layout: each source-row image remains unobstructed. Row
        # labels live in narrow white separators, never on top of the video.
        label_height = max(14, round(self.height * 0.02))
        content_height = self.height - label_height * 4
        base_panel_height = content_height // 4
        remaining_pixels = content_height % 4
        color_display = np.full(
            (self.height, self.width, 3),
            255,
            dtype=np.uint8,
        )
        destination_y = 0
        for panel_index, source_row in enumerate(self.row_labels):
            label = f"Row {source_row}"
            (label_width, label_text_height), label_baseline = cv2.getTextSize(
                label,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                1,
            )
            label_x = max(0, (self.width - label_width) // 2)
            label_y = (
                destination_y
                + (label_height + label_text_height - label_baseline) // 2
            )
            cv2.putText(
                color_display,
                label,
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )
            destination_y += label_height
            panel_height = base_panel_height + (
                1 if panel_index < remaining_pixels else 0
            )
            source_panel = self.spacetime_color_canvas[
                panel_index * self.total_frames :
                (panel_index + 1) * self.total_frames,
                :,
            ]
            color_display[
                destination_y : destination_y + panel_height,
                :,
            ] = cv2.resize(
                source_panel,
                (self.width, panel_height),
                interpolation=cv2.INTER_AREA,
            )
            destination_y += panel_height
        self.latest_spacetime_color = color_display
        self.frame_index += 1

        return NotebookFrames(
            edge=edges_inv,
            threshold=threshold,
            spacetime=spacetime,
            motion=motion_level,
        )
