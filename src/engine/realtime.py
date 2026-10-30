"""Real-time path: cheap, sequential, per-hop analysis of the ring buffer.

Everything here is stateful (spectral flux needs the previous frame, the
beat tracker needs its phase), so it runs in exactly one thread, hop by hop,
in stream order. Expensive analyses do not belong here - see
:mod:`src.engine.scheduler` - but their results (the consensus tempo) are
read back as priors for the beat tracker.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from src.analysis.tiers.features import FastFeatures, MediumFeatures
from src.config import (
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_BASS_MIN,
    FREQ_BAND_HIGH_MAX,
    FREQ_BAND_HIGH_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_MID_MIN,
    KICK_MIN_INTERVAL_S,
    ONSET_MIN_INTERVAL_S,
    ONSET_THRESHOLD_K,
    REALTIME_FFT_SIZE,
    REALTIME_HOP_SIZE,
    SILENCE_RMS,
)
from src.engine.base import Worker
from src.engine.buffer import RingBuffer

logger = logging.getLogger(__name__)

# Seconds of flux history used for the adaptive thresholds.
FLUX_HISTORY_S = 1.5
# Peak follower decay for band normalization (seconds to fall by ~63%).
LEVEL_PEAK_DECAY_S = 4.0
# Band level smoothing: fast attack, slower release.
LEVEL_ATTACK_S = 0.01
LEVEL_RELEASE_S = 0.15
# Absolute floor for band normalization (avoid amplifying silence to 1.0).
LEVEL_FLOOR = 1e-3


@dataclass(frozen=True)
class HopResult:
    """Everything the real-time path computed for one hop."""

    fast: FastFeatures
    medium: MediumFeatures
    onset: bool
    kick: bool


class _AdaptiveThreshold:
    """mean + k * std over a sliding window of recent values."""

    def __init__(self, size: int, k: float):
        self.values: deque[float] = deque(maxlen=size)
        self.k = k

    def threshold(self) -> float | None:
        if len(self.values) < self.values.maxlen // 3:
            return None  # still warming up
        arr = np.fromiter(self.values, dtype=np.float64, count=len(self.values))
        return float(arr.mean() + self.k * arr.std())

    def push(self, value: float) -> None:
        self.values.append(value)


class RealtimeAnalyzer:
    """Per-hop transient detection and band levels."""

    def __init__(
        self,
        sample_rate: int,
        fft_size: int = REALTIME_FFT_SIZE,
        hop_size: int = REALTIME_HOP_SIZE,
    ):
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.hop_s = hop_size / sample_rate
        self.window = np.hanning(fft_size).astype(np.float32)
        self._mag_scale = 2.0 / float(self.window.sum())  # full-scale sine -> ~1.0

        freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        nyquist = sample_rate / 2.0
        self.band_masks = {
            "bass": (freqs >= FREQ_BAND_BASS_MIN) & (freqs < FREQ_BAND_BASS_MAX),
            "mid": (freqs >= FREQ_BAND_MID_MIN) & (freqs < FREQ_BAND_MID_MAX),
            "high": (freqs >= FREQ_BAND_HIGH_MIN) & (freqs < min(FREQ_BAND_HIGH_MAX, nyquist)),
        }

        history = max(8, int(FLUX_HISTORY_S / self.hop_s))
        self._flux = _AdaptiveThreshold(history, ONSET_THRESHOLD_K)
        self._bass_flux = _AdaptiveThreshold(history, ONSET_THRESHOLD_K)
        self._prev_log_mag: np.ndarray | None = None
        self._last_onset_s = -math.inf
        self._last_kick_s = -math.inf

        self._peak_decay = math.exp(-self.hop_s / LEVEL_PEAK_DECAY_S)
        self._attack = 1.0 - math.exp(-self.hop_s / LEVEL_ATTACK_S)
        self._release = 1.0 - math.exp(-self.hop_s / LEVEL_RELEASE_S)
        self._band_peak = {name: LEVEL_FLOOR for name in self.band_masks}
        self._band_level = {name: 0.0 for name in self.band_masks}
        self._prev_overall = 0.0

    def process(self, frame: np.ndarray, timestamp_s: float) -> HopResult:
        """Analyze one frame (``fft_size`` samples ending at ``timestamp_s``)."""
        hop = frame[-self.hop_size:]
        raw_energy = min(1.0, float(np.sqrt(np.mean(hop.astype(np.float64) ** 2))))

        mag = np.abs(np.fft.rfft(frame * self.window)) * self._mag_scale
        log_mag = np.log1p(1000.0 * mag)

        # Half-wave rectified spectral flux (only energy *increases* count).
        if self._prev_log_mag is None:
            diff = np.zeros_like(log_mag)
        else:
            diff = np.maximum(log_mag - self._prev_log_mag, 0.0)
        self._prev_log_mag = log_mag
        flux = float(diff.mean())
        bass_flux = float(diff[self.band_masks["bass"]].mean())

        audible = raw_energy >= SILENCE_RMS
        onset_thr = self._flux.threshold()
        kick_thr = self._bass_flux.threshold()
        onset = (
            audible and onset_thr is not None and flux > onset_thr
            and timestamp_s - self._last_onset_s >= ONSET_MIN_INTERVAL_S
        )
        kick = (
            audible and kick_thr is not None and bass_flux > kick_thr
            and timestamp_s - self._last_kick_s >= KICK_MIN_INTERVAL_S
        )
        if onset:
            self._last_onset_s = timestamp_s
        if kick:
            self._last_kick_s = timestamp_s
        self._flux.push(flux)
        self._bass_flux.push(bass_flux)

        onset_strength = min(1.0, flux / (2.0 * onset_thr)) if onset_thr else 0.0

        # Band levels: RMS magnitude per band, normalized by a decaying peak,
        # then attack/release smoothed.
        levels: dict[str, float] = {}
        for name, mask in self.band_masks.items():
            level = float(np.sqrt(np.mean(mag[mask] ** 2))) if mask.any() else 0.0
            peak = max(level, self._band_peak[name] * self._peak_decay, LEVEL_FLOOR)
            self._band_peak[name] = peak
            target = level / peak
            prev = self._band_level[name]
            coeff = self._attack if target > prev else self._release
            levels[name] = prev + coeff * (target - prev)
        prev_bass = self._band_level["bass"]
        self._band_level = levels
        overall = max(levels.values())

        fast = FastFeatures(
            timestamp_s=timestamp_s,
            onset_detected=onset,
            onset_strength=onset_strength,
            is_percussive_peak=kick,
            percussive_peak_strength=levels["bass"] if kick else 0.0,
            raw_energy=raw_energy,
        )
        medium = MediumFeatures(
            timestamp_s=timestamp_s,
            bass_energy=levels["bass"],
            mid_energy=levels["mid"],
            high_energy=levels["high"],
            bass_energy_delta=levels["bass"] - prev_bass,
            overall_energy_delta=overall - self._prev_overall,
        )
        self._prev_overall = overall
        return HopResult(fast=fast, medium=medium, onset=onset, kick=kick)


@dataclass(frozen=True)
class BeatState:
    """Beat tracker output for one hop."""

    beat: bool
    phase: float
    confidence: float
    tempo_bpm: float | None
    next_beat_s: float | None


class BeatTracker:
    """Phase-locked loop: a flywheel at the tempo prior, nudged by kicks.

    Beats are emitted when the flywheel crosses the predicted beat time, not
    when a kick is detected, so consumers get beats on time (no detection
    latency) as long as the tracker is locked.
    """

    MIN_BPM = 60.0
    MAX_BPM = 200.0
    PHASE_GAIN = 0.3        # fraction of the timing error corrected per matching kick
    MATCH_WINDOW = 0.2      # kick within +-20% of a period counts as on-beat
    LOCK_GAIN = 0.15        # EMA rate of the lock quality
    LOST_AFTER_S = 8.0      # no matching kicks for this long -> stop emitting beats
    MISS_DECAY = 0.9        # lock multiplier for each predicted beat without a kick

    def __init__(self):
        self._period: float | None = None
        self._last_beat: float | None = None
        self._next_beat: float | None = None
        self._lock = 0.0
        self._last_match_s = -math.inf
        self._kick_times: deque[float] = deque(maxlen=12)

    def _set_period(self, period: float) -> None:
        self._period = period
        if self._last_beat is not None:
            self._next_beat = self._last_beat + period

    def _fallback_period(self) -> float | None:
        """Median kick interval, folded into the allowed tempo range."""
        if len(self._kick_times) < 4:
            return None
        intervals = np.diff(np.fromiter(self._kick_times, dtype=np.float64))
        intervals = intervals[(intervals > 60.0 / self.MAX_BPM / 2) & (intervals < 60.0 / self.MIN_BPM * 2)]
        if intervals.size < 3:
            return None
        period = float(np.median(intervals))
        while period < 60.0 / self.MAX_BPM:
            period *= 2
        while period > 60.0 / self.MIN_BPM:
            period /= 2
        return period

    def update(self, t: float, kick: bool, tempo_prior: float | None) -> BeatState:
        """Advance to stream time ``t`` (end of the current hop)."""
        if kick:
            self._kick_times.append(t)

        if tempo_prior is not None and self.MIN_BPM <= tempo_prior <= self.MAX_BPM:
            period = 60.0 / tempo_prior
            if self._period is None or abs(period - self._period) > 1e-6:
                self._set_period(period)
        elif self._period is None:
            period = self._fallback_period()
            if period is not None:
                self._set_period(period)

        if kick and self._period is not None:
            if self._last_beat is None:
                self._last_beat = t
                self._next_beat = t + self._period
                self._last_match_s = t
            else:
                # Timing error vs. the nearest predicted beat (previous or next).
                candidates = (self._last_beat, self._next_beat)
                nearest = min(candidates, key=lambda b: abs(t - b))
                error = t - nearest
                if abs(error) <= self.MATCH_WINDOW * self._period:
                    shift = self.PHASE_GAIN * error
                    self._last_beat += shift
                    self._next_beat += shift
                    self._lock += self.LOCK_GAIN * (1.0 - self._lock)
                    self._last_match_s = t
                else:
                    self._lock -= self.LOCK_GAIN * self._lock

        beat = False
        if self._next_beat is not None and self._period is not None:
            if t - self._last_match_s > self.LOST_AFTER_S:
                # Lost lock: drop the phase and wait for the next kick.
                self._last_beat = self._next_beat = None
                self._lock = 0.0
            else:
                while t >= self._next_beat:
                    self._last_beat = self._next_beat
                    self._next_beat += self._period
                    beat = True
                    # Flywheel keeps running through breakdowns, losing confidence.
                    if t - self._last_match_s > 1.5 * self._period:
                        self._lock *= self.MISS_DECAY

        if self._last_beat is None or self._period is None:
            return BeatState(False, 0.0, 0.0, self.tempo_bpm, None)
        phase = min(max((t - self._last_beat) / self._period, 0.0), 1.0)
        return BeatState(beat, phase, self._lock, self.tempo_bpm, self._next_beat)

    @property
    def tempo_bpm(self) -> float | None:
        return 60.0 / self._period if self._period else None


@dataclass(frozen=True)
class TransientEvent:
    """An onset, kick or beat, kept for the slow-tier summary."""

    timestamp_s: float
    kind: str  # "onset" | "kick" | "beat"
    confidence: float


class RealtimeWorker(Worker):
    """The single consumer thread of the real-time path."""

    def __init__(
        self,
        buffer: RingBuffer,
        on_hop: Callable[[FastFeatures, MediumFeatures], None],
        tempo_prior: Callable[[], float | None] = lambda: None,
        event_callback: Callable[[str, dict], None] | None = None,
        fft_size: int = REALTIME_FFT_SIZE,
        hop_size: int = REALTIME_HOP_SIZE,
        daemon: bool = True,
    ):
        super().__init__(name="Realtime", daemon=daemon)
        self.buffer = buffer
        self.on_hop = on_hop
        self.tempo_prior = tempo_prior
        self.event_callback = event_callback
        self.analyzer = RealtimeAnalyzer(buffer.sample_rate, fft_size, hop_size)
        self.beat_tracker = BeatTracker()
        self.hop_size = hop_size
        self.fft_size = fft_size
        self.hops_processed = 0
        self.hops_skipped = 0
        self._events: deque[TransientEvent] = deque(maxlen=512)
        self._events_lock = threading.Lock()

    def recent_events(self, since_s: float) -> list[TransientEvent]:
        """Transient events with ``timestamp_s >= since_s`` (thread-safe)."""
        with self._events_lock:
            return [e for e in self._events if e.timestamp_s >= since_s]

    def _record(self, event: TransientEvent, data: dict) -> None:
        with self._events_lock:
            self._events.append(event)
        if self.event_callback is not None and event.kind != "kick":
            try:
                self.event_callback(event.kind, data)
            except Exception:  # noqa: BLE001 - a consumer bug must not stop analysis
                logger.exception("[%s] event callback failed", self.name)

    def _work(self) -> None:
        sr = self.buffer.sample_rate
        position = 0  # absolute end sample of the next hop to analyze
        while not self.is_stopped():
            available = self.buffer.wait_for(position + self.hop_size, timeout=0.1)
            if available < position + self.hop_size:
                if self.buffer.closed:
                    break  # source finished and everything was analyzed
                continue
            while position + self.hop_size <= available and not self.is_stopped():
                position += self.hop_size
                frame = self.buffer.read(position, self.fft_size)
                if frame is None:
                    # Fell behind by more than the ring capacity: jump to the newest hop.
                    latest = self.buffer.total_written
                    skipped = (latest - position) // self.hop_size
                    self.hops_skipped += skipped
                    position += skipped * self.hop_size
                    logger.warning("[%s] Fell behind, skipped %d hops", self.name, skipped)
                    continue
                self._process(frame, position / sr)

    def _process(self, frame: np.ndarray, t: float) -> None:
        hop = self.analyzer.process(frame, t)
        beat = self.beat_tracker.update(t, hop.kick, self.tempo_prior())
        fast = hop.fast
        fast.beat_detected = beat.beat
        fast.beat_phase = beat.phase
        fast.beat_confidence = beat.confidence
        fast.tempo_bpm = beat.tempo_bpm
        fast.predicted_next_beat_s = beat.next_beat_s

        if hop.onset:
            self._record(TransientEvent(t, "onset", fast.onset_strength), {"timestamp": t, "strength": fast.onset_strength})
        if hop.kick:
            self._record(TransientEvent(t, "kick", fast.percussive_peak_strength), {"timestamp": t})
        if beat.beat:
            self._record(
                TransientEvent(t, "beat", beat.confidence),
                {"timestamp": t, "confidence": beat.confidence, "bpm": beat.tempo_bpm},
            )

        self.hops_processed += 1
        self.on_hop(fast, hop.medium)
