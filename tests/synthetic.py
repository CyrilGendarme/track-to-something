"""Synthetic audio for tests: exact, known BPM / key, no files needed."""

from __future__ import annotations

import time
from typing import Callable, Iterator

import numpy as np

from src.sources import AudioChunk


def kick_track(bpm: float, duration_s: float, sr: int, pad_midi: tuple[int, ...] = (60, 64, 67, 72)) -> np.ndarray:
    """Pitch-swept kicks at ``bpm`` over a quiet sustained chord."""
    n = int(duration_s * sr)
    t = np.arange(n) / sr
    y = np.zeros(n)
    burst_len = int(0.12 * sr)
    tb = np.arange(burst_len) / sr
    kick = np.sin(2 * np.pi * (55 + 90 * np.exp(-tb * 30)) * tb) * np.exp(-tb * 25)
    beat = 0.0
    while beat < duration_s:
        start = int(beat * sr)
        end = min(n, start + burst_len)
        y[start:end] += 0.8 * kick[: end - start]
        beat += 60.0 / bpm
    pad = sum(np.sin(2 * np.pi * 440 * 2 ** ((m - 69) / 12) * t) for m in pad_midi) * 0.05
    noise = np.random.default_rng(0).normal(0, 0.003, n)
    return (y + pad + noise).astype(np.float32)


def chunked_source(
    y: np.ndarray, sr: int, block: int = 512, speed: float | None = None
) -> Callable[[], Iterator[AudioChunk]]:
    """Source factory yielding stereo blocks; ``speed`` paces it (1.0 = real time)."""

    def gen() -> Iterator[AudioChunk]:
        for i in range(0, len(y), block):
            yield AudioChunk(np.column_stack([y[i:i + block]] * 2), sr)
            if speed:
                time.sleep(block / sr / speed)

    return gen
