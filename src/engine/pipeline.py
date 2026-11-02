"""Audio analysis pipeline: one ring buffer, a real-time path, scheduled jobs.

::

    source ──► AudioCaptureWorker ──► RingBuffer (mono, absolute sample index)
                                        │
                ┌───────────────────────┴────────────────────────┐
                ▼                                                ▼
        RealtimeWorker (every hop)                     JobScheduler
        onsets, kicks, band levels,                    dynamics  (thread,  0.25s / 2s)
        beat tracker ◄── tempo prior ───────────────── BPM x2    (process, 1s / 8s)
                │                                      key       (process, 2s / 8s)
                ▼                                                │
                └──────────────► FeatureCache ◄──────────────────┘
                                     │
                              GUI (polls) / local API (push)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

from src.analysis.bpm_detectors import (
    BPMEstimate,
    analyze_librosa_methods,
    analyze_signal_methods,
    consensus_bpm,
)
from src.analysis.dynamics import DynamicsResult, analyze_dynamics
from src.analysis.key_detection import KeyEstimate, KeySmoother, detect_key
from src.analysis.tiers.features import FastFeatures, MediumFeatures, SlowFeatures
from src.config import (
    BPM_INTERVAL_S,
    BPM_WINDOW_S,
    BUFFER_CAPACITY_SECONDS,
    DEFAULT_SAMPLE_RATE,
    DYNAMICS_INTERVAL_S,
    DYNAMICS_WINDOW_S,
    JOBS_USE_PROCESSES,
    KEY_HISTORY_SIZE,
    KEY_INTERVAL_S,
    KEY_WINDOW_S,
    LATENCY_PROFILE,
)
from .buffer import RingBuffer
from .capture_worker import AudioCaptureWorker
from .realtime import RealtimeWorker
from .scheduler import AnalysisJob, JobResult, JobScheduler, ProcessPoolSpec, shared_process_pool

logger = logging.getLogger(__name__)

# The beat tracker only follows the consensus tempo above this confidence.
TEMPO_PRIOR_MIN_CONFIDENCE = 0.3
# Extra ring buffer capacity beyond the longest job window.
BUFFER_HEADROOM_S = 2.0


def _warm_up_noise() -> np.ndarray:
    return np.random.default_rng(0).normal(0.0, 0.1, 3 * DEFAULT_SAMPLE_RATE).astype(np.float32)


def warm_up_signal_worker() -> None:
    """Initializer for the fast pool: load the numpy/scipy code paths."""
    analyze_signal_methods(_warm_up_noise(), DEFAULT_SAMPLE_RATE)
    detect_key(_warm_up_noise(), DEFAULT_SAMPLE_RATE)


def warm_up_librosa_worker() -> None:
    """Initializer for the librosa pool: pay librosa's import cost (seconds)."""
    analyze_librosa_methods(_warm_up_noise(), DEFAULT_SAMPLE_RATE)


# Fast numpy/scipy jobs (key, signal BPM methods) and the librosa job get
# separate pools, so librosa's slow first import never blocks the others.
SIGNAL_POOL = ProcessPoolSpec("signal", max_workers=2, initializer=warm_up_signal_worker)
LIBROSA_POOL = ProcessPoolSpec("librosa", max_workers=1, initializer=warm_up_librosa_worker)


def prewarm_job_processes() -> None:
    """Spawn and warm up the shared job processes ahead of the first pipeline.

    Call this when the application starts (the GUI does) so BPM and key
    estimates arrive within seconds of starting analysis.
    """
    shared_process_pool(SIGNAL_POOL)
    shared_process_pool(LIBROSA_POOL)


class FeatureCache:
    """Thread-safe store of the latest features (the only thing consumers read).

    Supports event-driven broadcasting: when anything is updated, the
    registered callback is invoked (from the producing thread). The callback
    must be cheap - the real-time path calls it on every hop.
    """

    def __init__(self):
        """Initialize feature cache."""
        self.fast: Optional[FastFeatures] = None
        self.medium: Optional[MediumFeatures] = None
        self.slow: Optional[SlowFeatures] = None
        self.bpm_estimates: dict[str, BPMEstimate] = {}
        self.version = 0
        self.lock = threading.Lock()
        self._on_update_callback: Callable[[], None] | None = None

    def set_update_callback(self, callback: Callable[[], None] | None) -> None:
        """Register a callback to be invoked when features are updated.

        Args:
            callback: Callable with no arguments, or None to unregister
        """
        with self.lock:
            self._on_update_callback = callback

    def _notify(self, callback: Callable[[], None] | None) -> None:
        # Invoked outside the lock to avoid blocking producers
        if callback is not None:
            try:
                callback()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[FeatureCache] Callback error: {type(exc).__name__}: {exc}", exc_info=True)

    def update(self, fast: Optional[FastFeatures] = None, medium: Optional[MediumFeatures] = None, slow: Optional[SlowFeatures] = None) -> None:
        """Update cached features and notify the registered callback.

        Args:
            fast: FastFeatures or None
            medium: MediumFeatures or None
            slow: SlowFeatures or None
        """
        with self.lock:
            if fast is not None:
                self.fast = fast
            if medium is not None:
                self.medium = medium
            if slow is not None:
                self.slow = slow
            self.version += 1
            callback = self._on_update_callback
        self._notify(callback)

    def get_all(self) -> tuple[Optional[FastFeatures], Optional[MediumFeatures], Optional[SlowFeatures]]:
        """Get all cached features.

        Returns:
            Tuple of (fast, medium, slow) features
        """
        with self.lock:
            return self.fast, self.medium, self.slow

    def update_bpm_estimates(self, estimates: dict[str, BPMEstimate]) -> None:
        """Update the latest per-method BPM estimates."""
        with self.lock:
            self.bpm_estimates = dict(estimates)
            self.version += 1
            callback = self._on_update_callback
        self._notify(callback)

    def get_bpm_estimates(self) -> dict[str, BPMEstimate]:
        """Get the latest per-method BPM estimates."""
        with self.lock:
            return dict(self.bpm_estimates)


class AudioPipeline:
    """Orchestrates capture, the real-time path and the background jobs."""

    def __init__(
        self,
        audio_source: Callable,
        buffer_capacity_s: float = BUFFER_CAPACITY_SECONDS,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        event_callback: Callable[[str, dict], None] | None = None,
        feature_cache: "FeatureCache | None" = None,
        use_processes: bool = JOBS_USE_PROCESSES,
        beat_lead_s: float | None = None,
        custom_band_hz: tuple[float, float] | None = None,
    ):
        """Initialize audio pipeline.

        Args:
            audio_source: Callable that returns an iterable of AudioChunk
                (the returned object may have a ``close()`` method, which
                is called on stop to unblock a waiting device read)
            buffer_capacity_s: Minimum ring buffer capacity in seconds (it is
                enlarged to fit the longest job window)
            sample_rate: Audio sample rate in Hz; the source must match it
            event_callback: Called from the real-time thread for "onset" and
                "beat" events as ``(event_type, data)``. Must be cheap and
                thread-safe (GUI code must marshal to its own thread).
            feature_cache: Optional externally-owned FeatureCache (e.g. so a
                local API server can keep serving the latest data across
                repeated pipeline start/stop cycles). A new one is created
                if omitted.
            use_processes: Run the BPM and key jobs in worker processes.
            beat_lead_s: Extra beat lead for latency outside the engine's
                view (default: the ``MOSHPRO_BEAT_LEAD_S`` setting).
            custom_band_hz: Optional (low, high) band reported as
                ``MediumFeatures.custom_energy``; see :meth:`set_custom_band`.
        """
        self.sample_rate = sample_rate
        self.feature_cache = feature_cache if feature_cache is not None else FeatureCache()

        longest_window_s = max(DYNAMICS_WINDOW_S, BPM_WINDOW_S, KEY_WINDOW_S)
        capacity_s = max(buffer_capacity_s, longest_window_s + BUFFER_HEADROOM_S)
        self.audio_buffer = RingBuffer(int(capacity_s * sample_rate), sample_rate)

        # Latest background results, combined into SlowFeatures on each update
        self._slow_lock = threading.Lock()
        self._dynamics: DynamicsResult | None = None
        self._dynamics_window: tuple[float, float] = (0.0, 0.0)
        self._key: tuple[str | None, float] = (None, 0.0)
        self._key_smoother = KeySmoother(KEY_HISTORY_SIZE)
        self._tempo: tuple[float | None, float] = (None, 0.0)
        self._bpm_estimates: dict[str, BPMEstimate] = {}

        self.capture_worker = AudioCaptureWorker(
            "Capture",
            audio_source=audio_source,
            buffer=self.audio_buffer,
            daemon=True,
        )
        self.realtime_worker = RealtimeWorker(
            buffer=self.audio_buffer,
            on_hop=lambda fast, medium: self.feature_cache.update(fast=fast, medium=medium),
            tempo_prior=self._tempo_prior,
            event_callback=event_callback,
            **({} if beat_lead_s is None else {"beat_lead_s": beat_lead_s}),
        )
        if custom_band_hz is not None:
            self.set_custom_band(*custom_band_hz)
        signal_pool = SIGNAL_POOL if use_processes else None
        librosa_pool = LIBROSA_POOL if use_processes else None
        self.jobs = [
            AnalysisJob("dynamics", analyze_dynamics, DYNAMICS_INTERVAL_S, DYNAMICS_WINDOW_S,
                        self._on_dynamics, min_window_s=0.5),
            AnalysisJob("bpm", analyze_signal_methods, BPM_INTERVAL_S, BPM_WINDOW_S,
                        self._on_bpm, process_pool=signal_pool, min_window_s=2.0),
            AnalysisJob("bpm_librosa", analyze_librosa_methods, BPM_INTERVAL_S, BPM_WINDOW_S,
                        self._on_bpm, process_pool=librosa_pool, min_window_s=2.0),
            AnalysisJob("key", detect_key, KEY_INTERVAL_S, KEY_WINDOW_S,
                        self._on_key, process_pool=signal_pool, min_window_s=2.0),
        ]
        self.scheduler = JobScheduler(self.audio_buffer, self.jobs)
        self._running = False
        self._started_at: float | None = None

    def set_custom_band(self, low_hz: float | None, high_hz: float | None = None) -> None:
        """Track an extra band, e.g. one instrument's range (any thread, any time).

        Reported every hop as ``MediumFeatures.custom_energy`` (0-1, like the
        fixed bands). ``None`` turns it off.
        """
        self.realtime_worker.analyzer.set_custom_band(low_hz, high_hz)

    def stats(self) -> dict:
        """Health figures for monitoring (cheap; any thread).

        ``load`` is the real-time path's analysis time per hop as a fraction
        of the hop duration; ``input_dbfs`` the input level over about the
        last second; ``overflows`` counts blocks the audio driver reported as
        dropped (live devices only).
        """
        rt = self.realtime_worker
        source = self.capture_worker._source
        return {
            "running": self.is_running(),
            "uptime_s": 0.0 if self._started_at is None else time.monotonic() - self._started_at,
            "audio_s": self.audio_buffer.total_written / self.sample_rate,
            "hops_processed": rt.hops_processed,
            "hops_skipped": rt.hops_skipped,
            "load": rt.load,
            "backlog_s": rt.backlog_s,
            "max_backlog_s": rt.max_backlog_s,
            "audio_age_s": rt.audio_age_s,
            "input_dbfs": rt.input_dbfs,
            "overflows": getattr(source, "overflows", None),
            "latency_profile": LATENCY_PROFILE,
            "block_size": getattr(source, "block_size", None),
            "hop_size": rt.hop_size,
            "wasapi_exclusive": getattr(source, "exclusive", None),
            "jobs": {
                job.name: {"runs": job.runs, "skipped": job.skipped, "last_compute_s": job.last_compute_s}
                for job in self.jobs
            },
        }

    # ── job results ───────────────────────────────────────────────────────

    def _tempo_prior(self) -> float | None:
        bpm, confidence = self._tempo
        return bpm if confidence >= TEMPO_PRIOR_MIN_CONFIDENCE else None

    def _on_dynamics(self, result: JobResult) -> None:
        with self._slow_lock:
            self._dynamics = result.value
            self._dynamics_window = (result.window_start_s, result.window_end_s)
        self._publish_slow()

    def _on_bpm(self, result: JobResult) -> None:
        # Both BPM jobs report a subset of the methods; merge them
        with self._slow_lock:
            self._bpm_estimates.update(result.value)
            estimates = dict(self._bpm_estimates)
        self._tempo = consensus_bpm(estimates)
        self.feature_cache.update_bpm_estimates(estimates)
        self._publish_slow()

    def _on_key(self, result: JobResult) -> None:
        estimate: KeyEstimate = result.value
        with self._slow_lock:
            self._key = self._key_smoother.update(estimate)
        self._publish_slow()

    def _publish_slow(self) -> None:
        """Combine the latest job results into SlowFeatures."""
        with self._slow_lock:
            dyn = self._dynamics
            start_s, end_s = self._dynamics_window
            key, key_confidence = self._key
        if dyn is None:
            return
        bpm, bpm_confidence = self._tempo

        events = self.realtime_worker.recent_events(start_s)
        beat_confidences = [e.confidence for e in events if e.kind == "beat"]

        slow = SlowFeatures(
            timestamp_s=end_s,
            overall_amplitude=dyn.overall_amplitude,
            rms=dyn.rms,
            peak=dyn.peak,
            bass_energy=float(np.mean(dyn.band_bass_envelope)),
            mid_energy=float(np.mean(dyn.band_mid_envelope)),
            high_energy=float(np.mean(dyn.band_high_envelope)),
            spectral_density_low=dyn.spectral_density_low,
            spectral_density_mid=dyn.spectral_density_mid,
            spectral_density_high=dyn.spectral_density_high,
            detected_key=key,
            key_confidence=key_confidence,
            onset_detected=any(e.kind == "onset" for e in events),
            beat_detected=bool(beat_confidences),
            beat_confidence=float(np.mean(beat_confidences)) if beat_confidences else 0.0,
            estimated_bpm=bpm,
            beat_stability=bpm_confidence,
            average_energy=dyn.rms,
            energy_variance=dyn.energy_variance,
            energy_trend=dyn.energy_trend,
            band_bass_envelope=dyn.band_bass_envelope,
            band_mid_envelope=dyn.band_mid_envelope,
            band_high_envelope=dyn.band_high_envelope,
        )
        self.feature_cache.update(slow=slow)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> "AudioPipeline":
        """Start all worker threads."""
        if self._running:
            logger.warning("Pipeline already running")
            return self
        logger.info("Starting audio pipeline (ring buffer %.1fs @ %d Hz)",
                    self.audio_buffer.capacity / self.sample_rate, self.sample_rate)
        self._running = True
        self._started_at = time.monotonic()
        self.capture_worker.start()
        self.realtime_worker.start()
        self.scheduler.start()
        return self

    def stop(self) -> None:
        """Stop all workers and close the audio source."""
        if not self._running:
            return
        logger.info("Stopping audio pipeline")
        self._running = False
        self.capture_worker.stop()
        self.realtime_worker.stop()
        self.scheduler.stop()

    def wait(self, timeout: float | None = None) -> None:
        """Wait until the source is exhausted and fully analyzed (or stopped).

        Re-raises an error from the capture thread (e.g. a device failure).

        Args:
            timeout: Maximum time to wait per worker in seconds
        """
        self.capture_worker.join(timeout=timeout)
        self.realtime_worker.join(timeout=timeout)
        if not self.realtime_worker.is_alive():
            # Source finished: let in-flight jobs publish, then (unless the
            # user stopped us) run every job once on the final window.
            self.scheduler.finish(timeout=timeout, final_pass=self._running)
            self._running = False
        else:
            self.scheduler.join(timeout=timeout)

    def is_running(self) -> bool:
        """True while audio is being captured or analyzed."""
        return self._running and (self.capture_worker.is_alive() or self.realtime_worker.is_alive())

    def get_events(self) -> list[tuple[float, str]]:
        """Recent (timestamp_s, kind) onset and beat events."""
        return [(e.timestamp_s, e.kind) for e in self.realtime_worker.recent_events(0.0) if e.kind != "kick"]

    def get_latest_audio(self, duration_s: float = 2.0) -> np.ndarray:
        """Get the latest mono audio from the ring buffer.

        Args:
            duration_s: Duration to retrieve in seconds

        Returns:
            Mono float32 samples
        """
        samples, _ = self.audio_buffer.read_latest(int(duration_s * self.sample_rate))
        return samples
