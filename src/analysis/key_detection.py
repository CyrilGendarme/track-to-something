"""Musical key detection (Krumhansl-Kessler profiles over an averaged chromagram).

``detect_key`` is a pure function of an audio window so it can run in a
worker process; ``KeySmoother`` holds the cross-window voting state and
lives in the main process.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Krumhansl-Kessler key profiles, index 0 = tonic.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Frequency range used for the chromagram: below ~60Hz bins are too coarse
# to resolve semitones; above ~2kHz cymbals/noise dominate.
CHROMA_MIN_HZ = 60.0
CHROMA_MAX_HZ = 2100.0
CHROMA_FFT_SIZE = 8192

# Margin between the best and second-best key correlation that counts as
# "fully confident" (relative major/minor typically differ by less).
CONFIDENT_MARGIN = 0.15


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() + 1e-12)


# Row i = profile with its tonic rotated onto pitch class i (z-scored).
# Rows 0-11 major keys C..B, rows 12-23 minor keys Cm..Bm.
_KEY_TEMPLATES = np.stack(
    [_z(np.roll(MAJOR_PROFILE, k)) for k in range(12)] + [_z(np.roll(MINOR_PROFILE, k)) for k in range(12)]
)
KEY_NAMES = tuple(PITCH_CLASSES) + tuple(f"{p}m" for p in PITCH_CLASSES)


@dataclass(frozen=True)
class KeyEstimate:
    """Key detected from one window."""

    key: str | None
    confidence: float
    correlation: float = 0.0
    chroma: tuple[float, ...] = ()


def chromagram(waveform: np.ndarray, sample_rate: int, n_fft: int = CHROMA_FFT_SIZE) -> np.ndarray:
    """Average 12-bin chroma of a mono signal (sums to 1, or all zeros on silence)."""
    y = np.asarray(waveform, dtype=np.float64).reshape(-1)
    if y.size < n_fft:
        y = np.pad(y, (0, n_fft - y.size))
    hop = n_fft // 2
    n_frames = 1 + (y.size - n_fft) // hop
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::hop][:n_frames]
    mag = np.abs(np.fft.rfft(frames * np.hanning(n_fft), axis=1)).mean(axis=0)

    freqs = np.fft.rfftfreq(n_fft, 1.0 / sample_rate)
    band = (freqs >= CHROMA_MIN_HZ) & (freqs <= CHROMA_MAX_HZ)
    midi = 69.0 + 12.0 * np.log2(freqs[band] / 440.0)
    pitch_class = np.mod(np.rint(midi).astype(np.int64), 12)  # 0 = C
    chroma = np.bincount(pitch_class, weights=mag[band], minlength=12)
    total = chroma.sum()
    return chroma / total if total > 1e-12 else np.zeros(12)


def detect_key(waveform: np.ndarray, sample_rate: int) -> KeyEstimate:
    """Detect the key of a mono window (a few seconds works best)."""
    chroma = chromagram(waveform, sample_rate)
    if not chroma.any() or chroma.std() < 1e-9:
        return KeyEstimate(None, 0.0, chroma=tuple(float(c) for c in chroma))

    correlations = _KEY_TEMPLATES @ _z(chroma) / 12.0  # Pearson r per key
    order = np.argsort(correlations)[::-1]
    best, second = float(correlations[order[0]]), float(correlations[order[1]])
    confidence = float(np.clip(best, 0.0, 1.0) * np.clip((best - second) / CONFIDENT_MARGIN, 0.0, 1.0))
    return KeyEstimate(KEY_NAMES[order[0]], confidence, best, tuple(float(c) for c in chroma))


class KeySmoother:
    """Confidence-weighted vote over the last few window estimates."""

    def __init__(self, history_size: int):
        self._history: deque[KeyEstimate] = deque(maxlen=max(1, history_size))

    def update(self, estimate: KeyEstimate) -> tuple[str | None, float]:
        """Add an estimate; return the smoothed (key, confidence)."""
        if estimate.key is not None:
            self._history.append(estimate)
        if not self._history:
            return None, 0.0
        votes: dict[str, float] = {}
        for e in self._history:
            votes[e.key] = votes.get(e.key, 0.0) + max(e.confidence, 1e-3)
        key = max(votes, key=votes.get)
        # Share of the total vote, times the mean confidence of the winner.
        share = votes[key] / sum(votes.values())
        mean_conf = float(np.mean([e.confidence for e in self._history if e.key == key]))
        return key, float(share * mean_conf)

    def reset(self) -> None:
        self._history.clear()
