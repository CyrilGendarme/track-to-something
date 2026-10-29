"""Multiple independent BPM/tempo detection algorithms, run in parallel.

The single onset-timestamp BPM estimator used elsewhere in this project
(``SlowAnalyzer``/``BeatPredictor``) is very sensitive to missed or spurious
onset detections, which causes large BPM jitter even on tracks with a very
stable beat. This module implements three *independent* algorithms that
each estimate BPM directly from a raw audio window, so a single bad onset
detection can no longer swing the result.

Methods implemented:
    - ``dynamic_kick_band``: find the dominant low-frequency peak per
      window (adaptive kick frequency) and narrow-band around it before
      autocorrelating - handles tracks whose kick isn't at a fixed pitch.
    - ``comb_filter_bank``: classic Scheirer-style comb filter bank scored
      directly against BPM candidates in-range (robust to octave errors).
    - ``librosa_beat_track``: librosa's dynamic-programming beat tracker.

All detectors share the same signature
``(waveform: np.ndarray, sample_rate: int, min_bpm: float, max_bpm: float) -> BPMEstimate``
so :class:`MultiMethodBPMAnalyzer` can fan them out to a thread pool.
Threads (not processes) are used because the underlying numpy/scipy/librosa
calls release the GIL for the bulk of their computation, giving real
wall-clock parallelism without the overhead of copying audio across
process boundaries.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Mapping

import librosa
import numpy as np
from scipy import signal as scipy_signal

logger = logging.getLogger(__name__)

DEFAULT_MIN_BPM: float = 60.0
DEFAULT_MAX_BPM: float = 200.0


@dataclass(frozen=True)
class BPMEstimate:
    """Result of a single BPM detection method."""

    method: str
    bpm: float | None
    confidence: float  # 0-1, method-specific but roughly comparable
    available: bool = True  # False when the required library isn't installed
    error: str | None = None
    extra: Mapping[str, float] = field(default_factory=dict)


DetectorFn = Callable[[np.ndarray, int, float, float], BPMEstimate]


# ────────────────────────────────────────────────────────────────────────────
# Shared DSP helpers
# ────────────────────────────────────────────────────────────────────────────
def _bandpass(y: np.ndarray, sr: int, low_hz: float, high_hz: float, order: int = 4) -> np.ndarray:
    """Zero-phase Butterworth band-pass filter.

    Uses second-order sections (not the ``b, a`` transfer-function form):
    narrow bands relative to the Nyquist frequency (as used by
    ``detect_dynamic_kick_band``) make ``b, a`` coefficients numerically
    unstable, silently producing NaN/Inf output from ``filtfilt``.
    """
    nyquist = sr / 2.0
    low = max(1e-4, low_hz / nyquist)
    high = min(0.999, high_hz / nyquist)
    if low >= high:
        raise ValueError(f"invalid band [{low_hz}, {high_hz}] Hz for sr={sr}")
    sos = scipy_signal.butter(order, [low, high], btype="band", output="sos")
    return scipy_signal.sosfiltfilt(sos, y)


def _onset_envelope(x: np.ndarray, sr: int, envelope_rate_hz: float = 200.0) -> tuple[np.ndarray, float]:
    """Half-wave rectified energy-flux envelope (emphasizes attacks/transients)."""
    hop = max(1, int(round(sr / envelope_rate_hz)))
    frame_len = max(hop * 2, 32)
    rms = librosa.feature.rms(y=x.astype(np.float32), frame_length=frame_len, hop_length=hop, center=True)[0]
    flux = np.diff(rms.astype(np.float64), prepend=rms[0])
    onset_strength = np.maximum(flux, 0.0)
    actual_rate = sr / hop
    return onset_strength, float(actual_rate)


def _energy_envelope(x: np.ndarray, sr: int, envelope_rate_hz: float = 200.0) -> tuple[np.ndarray, float]:
    """Raw (non-differentiated) RMS energy contour - captures loudness pulsing."""
    hop = max(1, int(round(sr / envelope_rate_hz)))
    frame_len = max(hop * 2, 32)
    rms = librosa.feature.rms(y=x.astype(np.float32), frame_length=frame_len, hop_length=hop, center=True)[0]
    actual_rate = sr / hop
    return rms.astype(np.float64), float(actual_rate)


def _autocorrelation_bpm(
    envelope: np.ndarray, envelope_rate_hz: float, min_bpm: float, max_bpm: float
) -> tuple[float | None, float]:
    """Find the best periodicity in ``envelope`` within a BPM range via autocorrelation.

    Returns ``(bpm, confidence)`` where confidence is the normalized
    autocorrelation coefficient (0-1) at the chosen lag.
    """
    envelope = envelope - np.mean(envelope)
    energy = float(np.dot(envelope, envelope))
    if energy <= 1e-12:
        return None, 0.0

    autocorr = np.correlate(envelope, envelope, mode="full")
    autocorr = autocorr[len(autocorr) // 2 :]  # keep lags >= 0

    min_lag = int(envelope_rate_hz * 60.0 / max_bpm)
    max_lag = min(int(envelope_rate_hz * 60.0 / min_bpm), len(autocorr) - 2)
    min_lag = max(1, min_lag)
    if min_lag >= max_lag:
        return None, 0.0

    segment = autocorr[min_lag : max_lag + 1]
    if segment.size < 3:
        return None, 0.0

    # Only genuine local maxima count as candidate periods. Without this,
    # a monotonically decaying autocorrelation (no real periodicity in this
    # band) always "wins" at the nearest search-range boundary, which looks
    # like a confident detection but is pure noise.
    local_max = np.zeros(segment.shape, dtype=bool)
    local_max[1:-1] = (segment[1:-1] > segment[:-2]) & (segment[1:-1] > segment[2:])
    candidate_indices = np.flatnonzero(local_max)
    if candidate_indices.size == 0:
        return None, 0.0

    best_idx = int(candidate_indices[np.argmax(segment[candidate_indices])])
    peak_val = float(segment[best_idx])
    if peak_val <= 0:
        return None, 0.0
    best_lag = min_lag + best_idx

    # Parabolic interpolation for sub-sample lag precision (best_idx always
    # has both neighbors available since it came from the interior mask).
    y0, y1, y2 = segment[best_idx - 1], segment[best_idx], segment[best_idx + 1]
    denom = y0 - 2 * y1 + y2
    delta = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0

    refined_lag = best_lag + delta
    if refined_lag <= 0:
        return None, 0.0

    bpm = 60.0 * envelope_rate_hz / refined_lag
    confidence = float(max(0.0, min(1.0, peak_val / energy)))
    return float(bpm), confidence


# ────────────────────────────────────────────────────────────────────────────
# Dynamically find the regular low-frequency peak (adaptive kick band)
# ────────────────────────────────────────────────────────────────────────────
def detect_dynamic_kick_band(
    y: np.ndarray,
    sr: int,
    min_bpm: float = DEFAULT_MIN_BPM,
    max_bpm: float = DEFAULT_MAX_BPM,
    search_low_hz: float = 30.0,
    search_high_hz: float = 180.0,
) -> BPMEstimate:
    """Detect the dominant low-frequency peak (the actual kick pitch) per
    window, band-pass a narrow range around it, then autocorrelate.

    Unlike :func:`detect_kick_band_autocorrelation`, the frequency range is
    not fixed - it adapts to whatever the loudest low-end fundamental is,
    which is more precise for kicks tuned outside the generic 40-120 Hz box.
    """
    method = "dynamic_kick_band"
    try:
        if y.size < sr * 2:
            return BPMEstimate(method, None, 0.0, error="need >= 2s of audio")

        nperseg = min(len(y), 8192)
        freqs, psd = scipy_signal.welch(y, fs=sr, nperseg=nperseg)
        mask = (freqs >= search_low_hz) & (freqs <= search_high_hz)
        if not np.any(mask):
            return BPMEstimate(method, None, 0.0, error="no low-frequency content in range")

        band_freqs = freqs[mask]
        band_psd = psd[mask]
        peak_idx = int(np.argmax(band_psd))
        peak_freq = float(band_freqs[peak_idx])

        bandwidth = max(10.0, peak_freq * 0.35)
        low = max(20.0, peak_freq - bandwidth)
        high = min(sr / 2.0 - 1.0, peak_freq + bandwidth)

        filtered = _bandpass(y, sr, low, high)
        envelope, envelope_rate = _onset_envelope(filtered, sr)
        bpm, confidence = _autocorrelation_bpm(envelope, envelope_rate, min_bpm, max_bpm)
        return BPMEstimate(
            method,
            bpm,
            confidence,
            extra={"kick_frequency_hz": peak_freq, "band_low_hz": low, "band_high_hz": high},
        )
    except Exception as exc:  # noqa: BLE001
        return BPMEstimate(method, None, 0.0, error=str(exc))


# ────────────────────────────────────────────────────────────────────────────
# Scheirer-style comb filter bank, scored directly against candidates
# ────────────────────────────────────────────────────────────────────────────
def detect_comb_filter_bank(
    y: np.ndarray,
    sr: int,
    min_bpm: float = DEFAULT_MIN_BPM,
    max_bpm: float = DEFAULT_MAX_BPM,
    step_bpm: float = 0.5,
) -> BPMEstimate:
    """Score a fine-grained grid of BPM candidates directly (normalized
    lagged autocorrelation on the raw loudness envelope). Because every
    candidate is evaluated explicitly within ``[min_bpm, max_bpm]``, this is
    naturally robust to the octave (half/double tempo) errors that plague
    unconstrained autocorrelation peak-picking.
    """
    method = "comb_filter_bank"
    try:
        if y.size < sr * 2:
            return BPMEstimate(method, None, 0.0, error="need >= 2s of audio")

        envelope, envelope_rate = _energy_envelope(y, sr)
        envelope = envelope - np.mean(envelope)
        n = len(envelope)
        if n < 10:
            return BPMEstimate(method, None, 0.0, error="envelope too short")

        candidates = np.arange(min_bpm, max_bpm + step_bpm / 2, step_bpm)
        scores = np.full(candidates.shape, -1.0, dtype=np.float64)

        for i, bpm in enumerate(candidates):
            lag = int(round(envelope_rate * 60.0 / bpm))
            if lag <= 0 or lag >= n - 1:
                continue
            a = envelope[: n - lag]
            b = envelope[lag:]
            denom = np.linalg.norm(a) * np.linalg.norm(b)
            if denom <= 1e-12:
                continue
            scores[i] = float(np.dot(a, b) / denom)

        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])
        if best_score <= 0:
            return BPMEstimate(method, None, 0.0, error="no periodic candidate found")

        return BPMEstimate(method, float(candidates[best_idx]), max(0.0, min(1.0, best_score)))
    except Exception as exc:  # noqa: BLE001
        return BPMEstimate(method, None, 0.0, error=str(exc))


# ────────────────────────────────────────────────────────────────────────────
# Librosa dynamic-programming beat tracker
# ────────────────────────────────────────────────────────────────────────────
def detect_librosa_beat_track(
    y: np.ndarray,
    sr: int,
    min_bpm: float = DEFAULT_MIN_BPM,
    max_bpm: float = DEFAULT_MAX_BPM,
) -> BPMEstimate:
    """Librosa's ``beat.beat_track`` (onset envelope + dynamic programming)."""
    method = "librosa_beat_track"
    try:
        if y.size < sr * 2:
            return BPMEstimate(method, None, 0.0, error="need >= 2s of audio")
        start_bpm = float(np.clip(120.0, min_bpm, max_bpm))
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=start_bpm, tightness=100)
        tempo_val = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else None
        if tempo_val is None or tempo_val <= 0:
            return BPMEstimate(method, None, 0.0, error="beat_track returned no tempo")

        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        if len(beat_times) >= 3:
            intervals = np.diff(beat_times)
            mean_interval = float(np.mean(intervals))
            cv = float(np.std(intervals) / mean_interval) if mean_interval > 0 else 1.0
            confidence = max(0.0, min(1.0, 1.0 - cv))
        else:
            confidence = 0.25
        return BPMEstimate(method, tempo_val, confidence, extra={"n_beats": float(len(beat_times))})
    except Exception as exc:  # noqa: BLE001
        return BPMEstimate(method, None, 0.0, error=str(exc))


# ────────────────────────────────────────────────────────────────────────────
# Registry + parallel runner
# ────────────────────────────────────────────────────────────────────────────
_ALL_DETECTORS: dict[str, DetectorFn] = {
    "dynamic_kick_band": detect_dynamic_kick_band,
    "comb_filter_bank": detect_comb_filter_bank,
    "librosa_beat_track": detect_librosa_beat_track,
}


class MultiMethodBPMAnalyzer:
    """Runs every registered BPM detector on the same audio window in parallel."""

    def __init__(
        self,
        min_bpm: float = DEFAULT_MIN_BPM,
        max_bpm: float = DEFAULT_MAX_BPM,
        detectors: Mapping[str, DetectorFn] | None = None,
        max_workers: int | None = None,
        timeout_s: float = 8.0,
    ):
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self.detectors = dict(detectors) if detectors is not None else dict(_ALL_DETECTORS)
        self.timeout_s = timeout_s
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers or max(1, len(self.detectors)), thread_name_prefix="bpm-detect"
        )

    def analyze(self, waveform: np.ndarray, sample_rate: int) -> dict[str, BPMEstimate]:
        """Run all detectors on ``waveform`` and return one estimate per method."""
        futures = {
            name: self._executor.submit(fn, waveform, sample_rate, self.min_bpm, self.max_bpm)
            for name, fn in self.detectors.items()
        }
        results: dict[str, BPMEstimate] = {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=self.timeout_s)
            except Exception as exc:  # noqa: BLE001 - isolate per-method failures
                logger.debug("[MultiMethodBPMAnalyzer] %s failed: %s", name, exc)
                results[name] = BPMEstimate(name, None, 0.0, error=str(exc))
        return results

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)


def consensus_bpm(
    estimates: Mapping[str, BPMEstimate],
    start_threshold: float = 0.95,
    step: float = 0.05,
) -> tuple[float | None, float]:
    """Combine per-method estimates into one consensus BPM.

    Starts by requiring near-unanimous agreement (confidence >= 0.95): if
    exactly one method clears the bar, its estimate wins outright; if
    several do, their BPMs are averaged. If none clear the bar, the
    threshold is relaxed by ``step`` (0.90, then 0.85, ...) and the same
    check is repeated, so consensus only ever comes from the highest
    confidence tier that actually has agreement.
    """
    valid = [e for e in estimates.values() if e.available and e.bpm is not None and e.confidence > 0]
    if not valid:
        return None, 0.0

    steps = int(round(start_threshold / step)) + 1
    for i in range(steps):
        threshold = start_threshold - i * step
        matches = [e for e in valid if e.confidence >= threshold]
        if matches:
            bpm = float(np.mean([e.bpm for e in matches]))
            confidence = float(np.mean([e.confidence for e in matches]))
            return bpm, confidence

    # Every estimate had confidence > 0, so the threshold=0 pass above
    # always matches; this is unreachable but kept as a safe fallback.
    weights = np.array([e.confidence for e in valid], dtype=np.float64)
    bpms = np.array([e.bpm for e in valid], dtype=np.float64)
    combined_bpm = float(np.average(bpms, weights=weights))
    combined_confidence = float(min(1.0, np.mean(weights)))
    return combined_bpm, combined_confidence
