"""MLX90640 packet decoding and temperature calculation for Morphogenesis.

The Arduino Mega streams factory calibration and raw sensor frames using the
binary ``MLX4`` protocol implemented by ``MLX90640_Mega_Stream.ino``.  This
module deliberately contains no serial-port or actuator control; it turns an
arbitrary byte stream into validated thermal readings for the System Agent.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


MAGIC = b"MLX4"
PACKET_CALIBRATION = 1
PACKET_FRAME = 2
CALIBRATION_WORDS = 832
FRAME_WORDS = 834
PIXEL_COUNT = 768


def crc16_ccitt(data: bytes | bytearray | memoryview) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def signed(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    sign_bit = 1 << (bits - 1)
    return value - (1 << bits) if value & sign_bit else value


def s8(value: int) -> int:
    return signed(value, 8)


def s16(value: int) -> int:
    return signed(value, 16)


def nibble(value: int, index: int) -> int:
    return (value >> (index * 4)) & 0x0F


class PacketDecoder:
    """Incrementally recover CRC-checked MLX4 packets from serial bytes."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.bad_crc_count = 0

    def feed(self, chunk: bytes) -> list[tuple[int, int, list[int]]]:
        if chunk:
            self.buffer.extend(chunk)
        packets: list[tuple[int, int, list[int]]] = []
        while len(self.buffer) >= 10:
            magic_index = self.buffer.find(MAGIC)
            if magic_index < 0:
                del self.buffer[:-3]
                break
            if magic_index:
                del self.buffer[:magic_index]
            if len(self.buffer) < 10:
                break

            packet_type = self.buffer[4]
            sequence = self.buffer[5]
            word_count = self.buffer[6] | (self.buffer[7] << 8)
            if word_count < 1 or word_count > 900:
                del self.buffer[0]
                continue
            packet_length = 10 + word_count * 2
            if len(self.buffer) < packet_length:
                break

            expected_crc = self.buffer[packet_length - 2] | (
                self.buffer[packet_length - 1] << 8
            )
            actual_crc = crc16_ccitt(memoryview(self.buffer)[4 : packet_length - 2])
            if expected_crc != actual_crc:
                self.bad_crc_count += 1
                del self.buffer[0]
                continue

            words = [
                (self.buffer[8 + index * 2] << 8) | self.buffer[9 + index * 2]
                for index in range(word_count)
            ]
            del self.buffer[:packet_length]
            packets.append((packet_type, sequence, words))
        return packets


@dataclass(slots=True)
class ThermalFrame:
    sequence: int
    temperatures: list[float]
    ambient_temperature: float
    center_temperature: float
    minimum_temperature: float
    maximum_temperature: float


class MLX90640Calculator:
    """Decode EEPROM calibration and combine two sensor subpages."""

    def __init__(self, emissivity: float = 0.95) -> None:
        self.emissivity = max(0.1, min(1.0, float(emissivity)))
        self.params: dict[str, object] | None = None
        self.temperatures = [math.nan] * PIXEL_COUNT
        self.subpages_seen = 0

    @property
    def calibrated(self) -> bool:
        return self.params is not None

    def set_calibration(self, ee: list[int]) -> None:
        if len(ee) != CALIBRATION_WORDS:
            raise ValueError("MLX90640 calibration packet has the wrong length")
        p: dict[str, object] = {}

        p["kVdd"] = s8(ee[51] >> 8) * 32
        p["vdd25"] = ((ee[51] & 0xFF) - 256) * 32 - 8192
        p["KvPTAT"] = signed((ee[50] >> 10) & 0x3F, 6) / 4096
        p["KtPTAT"] = signed(ee[50] & 0x3FF, 10) / 8
        p["vPTAT25"] = ee[49]
        p["alphaPTAT"] = (ee[16] & 0xF000) / 16384 + 8
        p["gainEE"] = s16(ee[48])
        p["tgc"] = s8(ee[60]) / 32
        p["resolutionEE"] = (ee[56] >> 12) & 3
        p["KsTa"] = s8(ee[60] >> 8) / 8192

        step = ((ee[63] >> 12) & 3) * 10
        ct = [-40.0, 0.0, float(nibble(ee[63], 1) * step), 0.0]
        ct[3] = ct[2] + nibble(ee[63], 2) * step
        p["ct"] = ct
        ks_to_scale = 2 ** (nibble(ee[63], 0) + 8)
        p["ksTo"] = [
            s8(ee[61]) / ks_to_scale,
            s8(ee[61] >> 8) / ks_to_scale,
            s8(ee[62]) / ks_to_scale,
            s8(ee[62] >> 8) / ks_to_scale,
        ]

        cp_alpha_scale = nibble(ee[32], 3) + 27
        cp_offset = [float(signed(ee[58] & 0x3FF, 10)), 0.0]
        cp_offset[1] = cp_offset[0] + signed((ee[58] >> 10) & 0x3F, 6)
        p["cpOffset"] = cp_offset
        cp_alpha = [signed(ee[57] & 0x3FF, 10) / 2**cp_alpha_scale, 0.0]
        cp_alpha[1] = (1 + signed((ee[57] >> 10) & 0x3F, 6) / 128) * cp_alpha[0]
        p["cpAlpha"] = cp_alpha
        p["cpKta"] = s8(ee[59]) / 2 ** (nibble(ee[56], 1) + 8)
        p["cpKv"] = s8(ee[59] >> 8) / 2 ** nibble(ee[56], 2)

        p["calibrationModeEE"] = (((ee[10] & 0x0800) >> 4) ^ 0x80)
        p["ilChessC"] = [
            signed(ee[53] & 0x3F, 6) / 16,
            signed((ee[53] >> 6) & 0x1F, 5) / 2,
            signed((ee[53] >> 11) & 0x1F, 5) / 8,
        ]

        kta_rc = [s8(ee[54] >> 8), s8(ee[55] >> 8), s8(ee[54]), s8(ee[55])]
        kv_t = [
            signed(nibble(ee[52], 3), 4),
            signed(nibble(ee[52], 1), 4),
            signed(nibble(ee[52], 2), 4),
            signed(nibble(ee[52], 0), 4),
        ]

        alpha = [0.0] * PIXEL_COUNT
        offset = [0] * PIXEL_COUNT
        kta = [0.0] * PIXEL_COUNT
        kv = [0.0] * PIXEL_COUNT
        bad = [False] * PIXEL_COUNT
        for pixel in range(PIXEL_COUNT):
            row = pixel // 32
            col = pixel % 32
            pixel_ee = ee[64 + pixel]
            bad[pixel] = pixel_ee == 0 or bool(pixel_ee & 1)

            alpha_row = signed(nibble(ee[34 + row // 4], row % 4), 4)
            alpha_col = signed(nibble(ee[40 + col // 4], col % 4), 4)
            alpha_rem = signed((pixel_ee >> 4) & 0x3F, 6)
            alpha[pixel] = (
                ee[33]
                + alpha_row * 2 ** nibble(ee[32], 2)
                + alpha_col * 2 ** nibble(ee[32], 1)
                + alpha_rem * 2 ** nibble(ee[32], 0)
            ) / 2 ** (nibble(ee[32], 3) + 30)
            alpha[pixel] -= float(p["tgc"]) * (cp_alpha[0] + cp_alpha[1]) / 2

            offset_row = signed(nibble(ee[18 + row // 4], row % 4), 4)
            offset_col = signed(nibble(ee[24 + col // 4], col % 4), 4)
            offset_rem = signed((pixel_ee >> 10) & 0x3F, 6)
            offset[pixel] = (
                s16(ee[17])
                + offset_row * 2 ** nibble(ee[16], 2)
                + offset_col * 2 ** nibble(ee[16], 1)
                + offset_rem * 2 ** nibble(ee[16], 0)
            )

            split = 2 * (row % 2) + (col % 2)
            kta_rem = signed((pixel_ee >> 1) & 7, 3)
            kta[pixel] = (
                kta_rc[split] + kta_rem * 2 ** nibble(ee[56], 0)
            ) / 2 ** (nibble(ee[56], 1) + 8)
            kv[pixel] = kv_t[split] / 2 ** nibble(ee[56], 2)

        if not p["kVdd"] or not p["KtPTAT"] or not p["gainEE"]:
            raise ValueError("MLX90640 factory calibration is invalid")
        p.update(alpha=alpha, offset=offset, kta=kta, kv=kv, bad=bad)
        self.params = p
        self.temperatures = [math.nan] * PIXEL_COUNT
        self.subpages_seen = 0

    @staticmethod
    def _fourth_root(value: float) -> float:
        return math.sqrt(math.sqrt(value)) if value > 0 and math.isfinite(value) else math.nan

    def add_frame(self, sequence: int, frame: list[int]) -> ThermalFrame | None:
        if self.params is None or len(frame) != FRAME_WORDS:
            return None
        p = self.params
        subpage = frame[833] & 1
        control = frame[832]
        resolution_ram = (control >> 10) & 3
        resolution_correction = 2 ** int(p["resolutionEE"]) / 2**resolution_ram
        vdd = (
            resolution_correction * s16(frame[810]) - float(p["vdd25"])
        ) / float(p["kVdd"]) + 3.3

        ptat = s16(frame[800])
        ptat_denominator = ptat * float(p["alphaPTAT"]) + s16(frame[768])
        if not ptat_denominator:
            return None
        ptat_art = ptat / ptat_denominator * 2**18
        ta = (
            ptat_art / (1 + float(p["KvPTAT"]) * (vdd - 3.3))
            - float(p["vPTAT25"])
        ) / float(p["KtPTAT"]) + 25
        if not math.isfinite(ta):
            return None

        # Keep the debug viewer's reflected-temperature assumption for parity.
        # It is display-only and can later be replaced by an installation offset.
        tr = ta - 8
        emissivity = self.emissivity
        ta_tr = (tr + 273.15) ** 4 - (
            ((tr + 273.15) ** 4 - (ta + 273.15) ** 4) / emissivity
        )
        gain_raw = s16(frame[778])
        if not gain_raw or frame[778] == 0x7FFF:
            return None
        gain = float(p["gainEE"]) / gain_raw
        mode = (control & 0x1000) >> 5

        cp_common = (1 + float(p["cpKta"]) * (ta - 25)) * (
            1 + float(p["cpKv"]) * (vdd - 3.3)
        )
        cp_offset = p["cpOffset"]
        il_chess = p["ilChessC"]
        ir_data_cp = [s16(frame[776]) * gain, s16(frame[808]) * gain]
        ir_data_cp[0] -= cp_offset[0] * cp_common
        cp1_offset = cp_offset[1] + (
            0 if mode == p["calibrationModeEE"] else il_chess[0]
        )
        ir_data_cp[1] -= cp1_offset * cp_common

        ks_to = p["ksTo"]
        ct = p["ct"]
        alpha_corr_r = [
            1 / (1 + ks_to[0] * 40),
            1.0,
            1 + ks_to[1] * ct[2],
            0.0,
        ]
        alpha_corr_r[3] = alpha_corr_r[2] * (
            1 + ks_to[2] * (ct[3] - ct[2])
        )

        for pixel in range(PIXEL_COUNT):
            row = pixel // 32
            col = pixel % 32
            il_pattern = row % 2
            chess_pattern = il_pattern ^ (col % 2)
            pattern = il_pattern if mode == 0 else chess_pattern
            if pattern != subpage:
                continue
            if p["bad"][pixel] or frame[pixel] == 0x7FFF:
                self.temperatures[pixel] = math.nan
                continue

            conversion_pattern = (
                (pixel + 2) // 4
                - (pixel + 3) // 4
                + (pixel + 1) // 4
                - pixel // 4
            ) * (1 - 2 * il_pattern)
            ir_data = s16(frame[pixel]) * gain
            ir_data -= p["offset"][pixel] * (
                1 + p["kta"][pixel] * (ta - 25)
            ) * (1 + p["kv"][pixel] * (vdd - 3.3))
            if mode != p["calibrationModeEE"]:
                ir_data += il_chess[2] * (2 * il_pattern - 1) - il_chess[1] * conversion_pattern
            ir_data = (ir_data - float(p["tgc"]) * ir_data_cp[subpage]) / emissivity

            alpha_compensated = p["alpha"][pixel] * (
                1 + float(p["KsTa"]) * (ta - 25)
            )
            sx = self._fourth_root(
                alpha_compensated**3 * (ir_data + alpha_compensated * ta_tr)
            ) * ks_to[1]
            first_denominator = alpha_compensated * (1 - ks_to[1] * 273.15) + sx
            if not first_denominator:
                self.temperatures[pixel] = math.nan
                continue
            object_temperature = self._fourth_root(
                ir_data / first_denominator + ta_tr
            ) - 273.15
            if object_temperature < ct[1]:
                temperature_range = 0
            elif object_temperature < ct[2]:
                temperature_range = 1
            elif object_temperature < ct[3]:
                temperature_range = 2
            else:
                temperature_range = 3
            final_denominator = alpha_compensated * alpha_corr_r[temperature_range] * (
                1 + ks_to[temperature_range] * (object_temperature - ct[temperature_range])
            )
            calculated = self._fourth_root(ir_data / final_denominator + ta_tr) - 273.15 if final_denominator else math.nan
            self.temperatures[pixel] = calculated if math.isfinite(calculated) else math.nan

        self.subpages_seen |= 1 << subpage
        if self.subpages_seen != 3:
            return None
        self.subpages_seen = 0
        temperatures = self._replace_bad_pixels(self.temperatures)
        finite = [value for value in temperatures if math.isfinite(value)]
        if not finite:
            return None
        center_indices = [11 * 32 + 15, 11 * 32 + 16, 12 * 32 + 15, 12 * 32 + 16]
        center_values = [temperatures[index] for index in center_indices if math.isfinite(temperatures[index])]
        center = statistics.fmean(center_values) if center_values else math.nan
        return ThermalFrame(
            sequence=sequence,
            temperatures=temperatures,
            ambient_temperature=ta,
            center_temperature=center,
            minimum_temperature=min(finite),
            maximum_temperature=max(finite),
        )

    @staticmethod
    def _replace_bad_pixels(values: list[float]) -> list[float]:
        result = list(values)
        for pixel, value in enumerate(values):
            if math.isfinite(value):
                continue
            row, col = divmod(pixel, 32)
            neighbours: list[float] = []
            for row_offset, col_offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                next_row, next_col = row + row_offset, col + col_offset
                if 0 <= next_row < 24 and 0 <= next_col < 32:
                    candidate = values[next_row * 32 + next_col]
                    if math.isfinite(candidate):
                        neighbours.append(candidate)
            if neighbours:
                result[pixel] = statistics.median(neighbours)
        return result
