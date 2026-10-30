"""Synthetic audio for tests: exact, known BPM / key, no files needed."""

from __future__ import annotations

import time
from typing import Callable, Iterator

import numpy as np

from src.diagnostics.signals import kick_track  # noqa: F401 - re-exported for tests
from src.sources import AudioChunk


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
