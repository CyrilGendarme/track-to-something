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
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import signal as scipy_signal

from src.analysis.tiers.features import FastFeatures, MediumFeatures
from src.config import (
    BEAT_LEAD_S,
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_BASS_MIN,
    FREQ_BAND_HIGH_MAX,
    FREQ_BAND_HIGH_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_MID_MIN,
    KICK_MIN_INTERVAL_S,
    ONSET_MIN_INTERVAL_S,
    KICK_THRESHOLD_K,
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
# Beats are emitted early by the measured age of the analyzed audio (device
# buffering + block + analysis) so they arrive on time in the real world;
# capped to stay sane if the clock mapping is off.
MAX_LATENCY_COMPENSATION_S = 0.3
# Kick attack localization: search the bass envelope of the last few hops
# (and at least ATTACK_SEARCH_S) for where it first rises this fraction of
# the way to its peak.
ATTACK_SEARCH_HOPS = 3
ATTACK_SEARCH_S = 0.016
ATTACK_FRACTION = 0.25
# Spectral flux compares each frame with the one about this long before it,
# whatever the hop size: with smaller hops, comparing consecutive frames would
# spread an attack's flux over several hops and drown it in noise.
FLUX_LAG_S = 0.0055
# EMA rate of the real-time load figure (per hop).
LOAD_SMOOTHING = 0.01
# Kick strength jumps on each kick, then decays (seconds to fall by ~63%), so
# consumers sampling at display rates still see it.
KICK_STRENGTH_DECAY_S = 0.1
# Time constant of the input level meter (seconds).
INPUT_LEVEL_S = 1.0


@dataclass(frozen=True)
class HopResult:
    """Everything the real-time path computed for one hop."""

    fast: FastFeatures
    medium: MediumFeatures
    onset: bool
    kick: bool
    kick_time_s: float | None = None  # estimated attack time (sub-hop), when kick


class _AdaptiveThreshold:
    """mean + k * std over a sliding window of recent values.

    Keeps running sums, so each hop costs O(1) instead of a pass over the
    whole history.
    """

    RESUM_EVERY = 4096  # recompute the sums from scratch now and then (float drift)

    def __init__(self, size: int, k: float):
        self._values = np.zeros(size)
        self._size = size
        self._pushed = 0
        self._sum = 0.0
        self._sum_sq = 0.0
        self.k = k

    def threshold(self) -> float | None:
        n = min(self._pushed, self._size)
        if n < self._size // 3:
            return None  # still warming up
        mean = self._sum / n
        variance = max(self._sum_sq / n - mean * mean, 0.0)
        return mean + self.k * math.sqrt(variance)

    def push(self, value: float) -> None:
        i = self._pushed % self._size
        if self._pushed >= self._size:
            old = self._values[i]
            self._sum -= old
            self._sum_sq -= old * old
        self._values[i] = value
        self._sum += value
        self._sum_sq += value * value
        self._pushed += 1
        if self._pushed % self.RESUM_EVERY == 0:
            filled = self._values[:min(self._pushed, self._size)]
            self._sum = float(filled.sum())
            self._sum_sq = float(filled @ filled)


def _bin_range(mask: np.ndarray) -> slice:
    """The contiguous FFT bins selected by ``mask``, as a slice (faster than masking)."""
    bins = np.flatnonzero(mask)
    return slice(int(bins[0]), int(bins[-1]) + 1) if bins.size else slice(0, 0)


def _rms(x: np.ndarray) -> float:
    return math.sqrt(float(x @ x) / x.size) if x.size else 0.0


class _BandLevel:
    """Level of one band: RMS magnitude normalized by a decaying peak, then
    attack/release smoothed."""

    def __init__(self, bins: slice, peak_decay: float, attack: float, release: float):
        self.bins = bins
        self._peak_decay = peak_decay
        self._attack = attack
        self._release = release
        self._peak = LEVEL_FLOOR
        self.level = 0.0

    def update(self, mag: np.ndarray) -> float:
        raw = _rms(mag[self.bins])
        self._peak = max(raw, self._peak * self._peak_decay, LEVEL_FLOOR)
        target = raw / self._peak
        coeff = self._attack if target > self.level else self._release
        self.level += coeff * (target - self.level)
        return self.level


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
        self._freqs = freqs
        nyquist = sample_rate / 2.0
        self.band_bins = {
            "bass": _bin_range((freqs >= FREQ_BAND_BASS_MIN) & (freqs < FREQ_BAND_BASS_MAX)),
            "mid": _bin_range((freqs >= FREQ_BAND_MID_MIN) & (freqs < FREQ_BAND_MID_MAX)),
            "high": _bin_range((freqs >= FREQ_BAND_HIGH_MIN) & (freqs < min(FREQ_BAND_HIGH_MAX, nyquist))),
        }

        history = max(8, int(FLUX_HISTORY_S / self.hop_s))
        self._flux = _AdaptiveThreshold(history, ONSET_THRESHOLD_K)
        self._bass_flux = _AdaptiveThreshold(history, KICK_THRESHOLD_K)
        # Previous log spectra, oldest first; the flux reference is the oldest
        self._past_log_mags: deque[np.ndarray] = deque(maxlen=max(1, round(FLUX_LAG_S / self.hop_s)))
        self._last_onset_s = -math.inf
        self._last_kick_s = -math.inf

        self._peak_decay = math.exp(-self.hop_s / LEVEL_PEAK_DECAY_S)
        self._attack = 1.0 - math.exp(-self.hop_s / LEVEL_ATTACK_S)
        self._release = 1.0 - math.exp(-self.hop_s / LEVEL_RELEASE_S)
        self._bands = {name: self._band_level(bins) for name, bins in self.band_bins.items()}
        self._prev_overall = 0.0
        self._kick_decay = math.exp(-self.hop_s / KICK_STRENGTH_DECAY_S)
        self._kick_strength = 0.0
        # User-selected band: (level tracker, (low_hz, high_hz)), swapped as a
        # whole so another thread can change it between hops
        self._custom: tuple[_BandLevel, tuple[float, float]] | None = None

        # Low-pass for kick attack localization (only run on kick hops)
        self._kick_lowpass = scipy_signal.butter(2, FREQ_BAND_BASS_MAX, btype="low", fs=sample_rate, output="sos")
        self._attack_span = min(fft_size, max(ATTACK_SEARCH_HOPS * hop_size, round(ATTACK_SEARCH_S * sample_rate)))

    def _band_level(self, bins: slice) -> _BandLevel:
        return _BandLevel(bins, self._peak_decay, self._attack, self._release)

    def set_custom_band(self, low_hz: float | None, high_hz: float | None = None) -> None:
        """Track the level of ``low_hz``-``high_hz`` as ``custom_energy``.

        Safe to call from any thread; ``None`` turns the custom band off. A
        band narrower than one FFT bin uses the nearest bin.
        """
        if low_hz is None or high_hz is None:
            self._custom = None
            return
        low_hz, high_hz = sorted((float(low_hz), float(high_hz)))
        mask = (self._freqs >= low_hz) & (self._freqs < high_hz)
        if not mask.any():
            mask = np.zeros_like(mask)
            mask[int(np.argmin(np.abs(self._freqs - (low_hz + high_hz) / 2)))] = True
        self._custom = (self._band_level(_bin_range(mask)), (low_hz, high_hz))

    @property
    def custom_band_hz(self) -> tuple[float, float] | None:
        custom = self._custom
        return None if custom is None else custom[1]

    def _locate_kick_attack(self, frame: np.ndarray, timestamp_s: float) -> float:
        """Estimate when the kick started within the last few hops.

        A kick is only *detected* at the end of a hop, several ms after its
        attack (window overlap + hop quantization). Its start is taken as the
        point where the bass amplitude envelope first climbs a fraction of the
        way from its pre-kick level to its peak.
        """
        bass = scipy_signal.sosfilt(self._kick_lowpass, frame.astype(np.float64))
        env = np.abs(scipy_signal.hilbert(bass))[-self._attack_span:]
        peak_idx = int(np.argmax(env))
        if peak_idx == 0:
            return timestamp_s
        baseline = float(env[:peak_idx].min())
        level = baseline + ATTACK_FRACTION * (float(env[peak_idx]) - baseline)
        last_low = np.flatnonzero(env[:peak_idx] < level)
        start_idx = int(last_low[-1]) + 1 if last_low.size else 0
        return timestamp_s - (self._attack_span - start_idx) / self.sample_rate

    def process(self, frame: np.ndarray, timestamp_s: float) -> HopResult:
        """Analyze one frame (``fft_size`` samples ending at ``timestamp_s``)."""
        hop = frame[-self.hop_size:]
        raw_energy = min(1.0, _rms(hop.astype(np.float64)))

        mag = np.abs(np.fft.rfft(frame * self.window)) * self._mag_scale
        log_mag = np.log1p(1000.0 * mag)

        # Half-wave rectified spectral flux (only energy *increases* count).
        past = self._past_log_mags
        if past:
            diff = np.maximum(log_mag - past[0], 0.0)
        else:
            diff = np.zeros_like(log_mag)
        past.append(log_mag)
        flux = float(diff.sum()) / diff.size
        bass = diff[self.band_bins["bass"]]
        bass_flux = float(bass.sum()) / bass.size

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
        self._kick_strength *= self._kick_decay
        if kick:
            self._kick_strength = max(self._kick_strength, min(1.0, bass_flux / (2.0 * kick_thr)))

        prev_bass = self._bands["bass"].level
        levels = {name: band.update(mag) for name, band in self._bands.items()}
        overall = max(levels.values())
        custom = self._custom
        custom_level = custom[0].update(mag) if custom is not None else 0.0

        fast = FastFeatures(
            timestamp_s=timestamp_s,
            onset_detected=onset,
            onset_strength=onset_strength,
            is_percussive_peak=kick,
            percussive_peak_strength=self._kick_strength,
            raw_energy=raw_energy,
        )
        medium = MediumFeatures(
            timestamp_s=timestamp_s,
            bass_energy=levels["bass"],
            mid_energy=levels["mid"],
            high_energy=levels["high"],
            bass_energy_delta=levels["bass"] - prev_bass,
            overall_energy_delta=overall - self._prev_overall,
            custom_energy=custom_level,
            custom_band_hz=custom[1] if custom is not None else None,
        )
        self._prev_overall = overall
        kick_time_s = self._locate_kick_attack(frame, timestamp_s) if kick else None
        return HopResult(fast=fast, medium=medium, onset=onset, kick=kick, kick_time_s=kick_time_s)


@dataclass(frozen=True)
class BeatState:
    """Beat tracker output for one hop."""

    beat: bool
    phase: float
    confidence: float
    tempo_bpm: float | None
    next_beat_s: float | None
    beat_time_s: float | None = None  # exact predicted time of the emitted beat


class BeatTracker:
    """Phase-locked loop: a flywheel at the tempo prior, nudged by kicks.

    Each on-beat kick corrects both the phase (``PHASE_GAIN``) and a small
    tempo offset on top of the prior (``TEMPO_GAIN``, an alpha-beta / type-2
    loop), so a prior that is slightly off (e.g. 127.5 vs 128 BPM) does not
    leave a constant lag behind the kicks.

    Beats are emitted from the predicted beat times, not when a kick is
    detected, so consumers get beats on time (no detection latency) as long
    as the tracker is locked. A beat is emitted on the update whose time is
    within ``lookahead_s`` of it (use half a hop so hop quantization
    averages out), and carries its exact predicted time.
    """

    MIN_BPM = 60.0
    MAX_BPM = 200.0
    PHASE_GAIN = 0.3        # fraction of the timing error corrected per matching kick
    TEMPO_GAIN = 0.05       # fraction of the timing error added to the period per matching kick
    MAX_TEMPO_CORRECTION = 0.02  # the learned period offset stays within +-2% of the prior
    PRIOR_RESET_CHANGE = 0.02    # a prior moving more than 2% discards the learned offset
    MATCH_WINDOW = 0.2      # kick within +-20% of a period counts as on-beat
    LOCK_GAIN = 0.15        # EMA rate of the lock quality
    LOST_AFTER_S = 8.0      # no matching kicks for this long -> stop emitting beats
    MISS_DECAY = 0.9        # lock multiplier for each predicted beat without a kick

    def __init__(self, lookahead_s: float = 0.0):
        self.lookahead_s = lookahead_s
        self._base_period: float | None = None  # from the tempo prior / kick intervals
        self._period_offset = 0.0               # learned correction on top of it
        self._period: float | None = None
        self._last_beat: float | None = None
        self._next_beat: float | None = None
        self._lock = 0.0
        self._last_match_s = -math.inf
        self._kick_times: deque[float] = deque(maxlen=12)

    def _set_base_period(self, base: float) -> None:
        if self._base_period is None or abs(base - self._base_period) > self.PRIOR_RESET_CHANGE * self._base_period:
            self._period_offset = 0.0
        self._base_period = base
        self._apply_period()

    def _apply_period(self) -> None:
        limit = self.MAX_TEMPO_CORRECTION * self._base_period
        self._period_offset = min(max(self._period_offset, -limit), limit)
        self._period = self._base_period + self._period_offset
        if self._last_beat is not None:
            self._next_beat = self._last_beat + self._period

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

    def update(self, t: float, kick_time: float | None, tempo_prior: float | None) -> BeatState:
        """Advance to stream time ``t`` (end of the current hop).

        Args:
            t: Current stream time
            kick_time: Attack time of a kick detected in this hop, or None
            tempo_prior: Consensus tempo to follow (BPM), or None
        """
        if kick_time is not None:
            self._kick_times.append(kick_time)

        if tempo_prior is not None and self.MIN_BPM <= tempo_prior <= self.MAX_BPM:
            base = 60.0 / tempo_prior
            if self._base_period is None or abs(base - self._base_period) > 1e-9:
                self._set_base_period(base)
        elif self._base_period is None:
            base = self._fallback_period()
            if base is not None:
                self._set_base_period(base)

        if kick_time is not None and self._period is not None:
            if self._last_beat is None:
                self._last_beat = kick_time
                self._next_beat = kick_time + self._period
                self._last_match_s = kick_time
            else:
                # Timing error vs. the nearest predicted beat (previous or next).
                candidates = (self._last_beat, self._next_beat)
                nearest = min(candidates, key=lambda b: abs(kick_time - b))
                error = kick_time - nearest
                if abs(error) <= self.MATCH_WINDOW * self._period:
                    shift = self.PHASE_GAIN * error
                    self._last_beat += shift
                    self._next_beat += shift
                    # A kick after its predicted beat means our period is too short
                    self._period_offset += self.TEMPO_GAIN * error
                    self._apply_period()
                    self._lock += self.LOCK_GAIN * (1.0 - self._lock)
                    self._last_match_s = kick_time
                else:
                    self._lock -= self.LOCK_GAIN * self._lock

        beat_time: float | None = None
        if self._next_beat is not None and self._period is not None:
            if t - self._last_match_s > self.LOST_AFTER_S:
                # Lost lock: drop the phase and wait for the next kick.
                self._last_beat = self._next_beat = None
                self._lock = 0.0
            else:
                while self._next_beat <= t + self.lookahead_s:
                    beat_time = self._next_beat
                    self._last_beat = self._next_beat
                    self._next_beat += self._period
                    # Flywheel keeps running through breakdowns, losing confidence.
                    if t - self._last_match_s > 1.5 * self._period:
                        self._lock *= self.MISS_DECAY

        if self._last_beat is None or self._period is None:
            return BeatState(False, 0.0, 0.0, self.tempo_bpm, None)
        phase = min(max((t - self._last_beat) / self._period, 0.0), 1.0)
        return BeatState(beat_time is not None, phase, self._lock, self.tempo_bpm, self._next_beat, beat_time)

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
        beat_lead_s: float = BEAT_LEAD_S,
        daemon: bool = True,
    ):
        super().__init__(name="Realtime", daemon=daemon)
        self.beat_lead_s = beat_lead_s
        self.buffer = buffer
        self.on_hop = on_hop
        self.tempo_prior = tempo_prior
        self.event_callback = event_callback
        self.analyzer = RealtimeAnalyzer(buffer.sample_rate, fft_size, hop_size)
        self._half_hop_s = hop_size / buffer.sample_rate / 2
        self.beat_tracker = BeatTracker(lookahead_s=self._half_hop_s)
        self.hop_size = hop_size
        self.fft_size = fft_size
        self.hops_processed = 0
        self.hops_skipped = 0
        # How far analysis trails the newest captured audio (seconds)
        self.backlog_s = 0.0
        self.max_backlog_s = 0.0
        # Wall-clock age of the audio when analyzed (needs capture timestamps)
        self.audio_age_s = 0.0
        # Smoothed analysis time per hop, as a fraction of the hop's duration
        # (1.0 = the real-time path can only just keep up)
        self.load = 0.0
        # Input level over the last ~second, dBFS (mean square, smoothed)
        self._input_ms = 0.0
        self._input_coeff = 1.0 - math.exp(-(hop_size / buffer.sample_rate) / INPUT_LEVEL_S)
        self._onset_count = 0
        self._kick_count = 0
        self._beat_count = 0
        self._events: deque[TransientEvent] = deque(maxlen=512)
        self._events_lock = threading.Lock()

    @property
    def input_dbfs(self) -> float:
        """Input RMS over about the last second, in dBFS (-120 for silence)."""
        return 10.0 * math.log10(max(self._input_ms, 1e-12))

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
                self.backlog_s = (available - position) / sr
                self.max_backlog_s = max(self.max_backlog_s, self.backlog_s)
                started = time.perf_counter()
                self._process(frame, position / sr)
                load = (time.perf_counter() - started) / self.analyzer.hop_s
                self.load += LOAD_SMOOTHING * (load - self.load)

    def _process(self, frame: np.ndarray, t: float) -> None:
        hop = self.analyzer.process(frame, t)

        # Stream time lags real time by the age of the audio; predicting
        # that far ahead makes beat events land on the real beat.
        captured = self.buffer.unix_time_of(t)
        age = 0.0 if captured is None else min(max(time.time() - captured, 0.0), MAX_LATENCY_COMPENSATION_S)
        self.audio_age_s = age
        self.beat_tracker.lookahead_s = self._half_hop_s + age + self.beat_lead_s

        beat = self.beat_tracker.update(t, hop.kick_time_s, self.tempo_prior())
        fast = hop.fast
        fast.beat_detected = beat.beat
        fast.beat_phase = beat.phase
        fast.beat_confidence = beat.confidence
        fast.tempo_bpm = beat.tempo_bpm
        fast.predicted_next_beat_s = beat.next_beat_s
        fast.audio_age_s = age
        if beat.next_beat_s is not None:
            fast.predicted_next_beat_unix_s = self.buffer.unix_time_of(beat.next_beat_s)
        self._onset_count += hop.onset
        self._kick_count += hop.kick
        self._beat_count += beat.beat
        fast.onset_count = self._onset_count
        fast.kick_count = self._kick_count
        fast.beat_count = self._beat_count

        if hop.onset:
            self._record(TransientEvent(t, "onset", fast.onset_strength), {"timestamp": t, "strength": fast.onset_strength})
        if hop.kick:
            self._record(TransientEvent(hop.kick_time_s, "kick", fast.percussive_peak_strength),
                         {"timestamp": hop.kick_time_s})
        if beat.beat:
            # Timestamped with the exact predicted beat time; emitted up to the
            # audio age + half a hop ahead of it
            self._record(
                TransientEvent(beat.beat_time_s, "beat", beat.confidence),
                {
                    "timestamp": beat.beat_time_s,
                    "time_unix": self.buffer.unix_time_of(beat.beat_time_s),
                    "confidence": beat.confidence,
                    "bpm": beat.tempo_bpm,
                },
            )

        self._input_ms += self._input_coeff * (fast.raw_energy ** 2 - self._input_ms)
        self.hops_processed += 1
        self.on_hop(fast, hop.medium)
