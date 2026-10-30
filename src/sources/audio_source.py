"""Common contracts for PCM audio sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol

import numpy as np


@dataclass(frozen=True)
class AudioChunk:
    """A mono or multi-channel float32 block ready for analysis."""

    samples: np.ndarray
    sample_rate: int
    # Wall-clock (Unix) time the first sample was captured, when the source
    # knows it (live devices); None for files and synthetic sources.
    capture_time_s: float | None = None


class AudioSource(Protocol):
    """A pull-based source of audio blocks."""

    def __iter__(self) -> Iterator[AudioChunk]: ...

    def close(self) -> None: ...