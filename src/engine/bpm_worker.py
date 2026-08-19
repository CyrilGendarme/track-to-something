"""Background worker that periodically runs every BPM detection method.

Unlike the per-chunk onset-timestamp BPM estimate, this worker pulls a long
(multi-second) audio window from the shared circular buffer at a slow,
fixed cadence and fans it out to :class:`MultiMethodBPMAnalyzer`, so each
method sees the same stable window and results can be compared side by side.
"""

from __future__ import annotations

import logging

import numpy as np

from src.analysis.bpm_detectors import BPMEstimate, MultiMethodBPMAnalyzer
from src.analysis.multi_window_analyzer import MultiWindowAudioAnalyzer
from src.config import DEFAULT_SAMPLE_RATE
from .base import Worker

logger = logging.getLogger(__name__)


class BPMAnalysisWorker(Worker):
    """Periodically computes BPM estimates from every registered method."""

    def __init__(
        self,
        multi_analyzer: MultiWindowAudioAnalyzer,
        on_result: "callable[[dict[str, BPMEstimate]], None]",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        window_s: float = 8.0,
        interval_s: float = 1.0,
        daemon: bool = True,
    ):
        """Initialize BPM analysis worker.

        Args:
            multi_analyzer: Shared analyzer whose circular buffer supplies audio.
            on_result: Callback invoked with the latest {method: BPMEstimate} dict.
            sample_rate: Audio sample rate in Hz.
            window_s: How much recent audio to analyze each pass (needs several
                beats; longer windows give more stable autocorrelation results).
            interval_s: How often to recompute (this is deliberately not
                every-chunk, since every method here is much more expensive
                than the fast onset-based estimator).
            daemon: If True, thread will not prevent program exit.
        """
        super().__init__(name="BPMAnalysis", daemon=daemon)
        self.multi_analyzer = multi_analyzer
        self.on_result = on_result
        self.sample_rate = sample_rate
        self.window_s = window_s
        self.interval_s = interval_s
        self.detector = MultiMethodBPMAnalyzer()

    def _work(self) -> None:
        while not self.is_stopped():
            try:
                audio = self.multi_analyzer.get_recent_audio(self.window_s * 1000)
                mono = audio.mean(axis=1) if audio.ndim == 2 else audio
                if mono.size >= self.sample_rate * 2 and np.any(mono):
                    results = self.detector.analyze(mono.astype(np.float32), self.sample_rate)
                    self.on_result(results)
            except Exception:
                logger.exception("[%s] Error computing BPM estimates", self.name)
            self._stop_event.wait(self.interval_s)

    def stop(self) -> None:
        super().stop()
        self.detector.shutdown(wait=False)
