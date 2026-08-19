"""Multi-threaded audio analysis pipeline."""

from __future__ import annotations

import logging
import threading
from queue import Queue
from typing import Callable, Optional

from src.config import (
    DEFAULT_SAMPLE_RATE,
    BUFFER_CAPACITY_SECONDS,
    NUM_PROCESSING_WORKERS,
    OUTPUT_QUEUE_MAXSIZE,
)
from src.analysis.tiers.features import FastFeatures, MediumFeatures, SlowFeatures
from src.analysis.multi_window_analyzer import MultiWindowAudioAnalyzer
from .buffer import CircularAudioBuffer
from .capture_worker import AudioCaptureWorker
from .processing_worker import AudioProcessingWorker
from .analysis_worker import AnalysisWorker
from .rendering_worker import RenderingWorker

logger = logging.getLogger(__name__)


class FeatureCache:
    """Thread-safe cache for latest audio features (all three tiers)."""
    
    def __init__(self):
        """Initialize feature cache."""
        self.fast: Optional[FastFeatures] = None
        self.medium: Optional[MediumFeatures] = None
        self.slow: Optional[SlowFeatures] = None
        self.lock = threading.Lock()
    
    def update(self, fast: Optional[FastFeatures] = None, medium: Optional[MediumFeatures] = None, slow: Optional[SlowFeatures] = None) -> None:
        """Update cached features.
        
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
    
    def get_all(self) -> tuple[Optional[FastFeatures], Optional[MediumFeatures], Optional[SlowFeatures]]:
        """Get all cached features.
        
        Returns:
            Tuple of (fast, medium, slow) features
        """
        with self.lock:
            return self.fast, self.medium, self.slow


class AudioPipeline:
    """Orchestrates multi-threaded audio analysis pipeline.
    
    Architecture:
    - AudioCaptureWorker: Captures audio chunks → CircularAudioBuffer + Capture Queue
    - AudioProcessingWorker(s): Reads Capture Queue → Processes audio features → Features Queue
    - AnalysisWorker: Reads Features Queue → Detects events → Rendering Queue
    - RenderingWorker: Reads Rendering Queue → Updates display/output
    """

    def __init__(
        self,
        audio_source: Callable,
        n_processing_workers: int = NUM_PROCESSING_WORKERS,
        buffer_capacity_s: float = BUFFER_CAPACITY_SECONDS,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        event_callback: Callable[[str, dict], None] | None = None,
    ):
        """Initialize audio pipeline.
        
        Args:
            audio_source: Callable that returns an iterable of AudioChunk
            n_processing_workers: Number of parallel processing workers (default from config)
            buffer_capacity_s: Circular buffer capacity in seconds (default from config)
            sample_rate: Audio sample rate in Hz (default from config)
            event_callback: Callback for detected events (event_type, data)
        """
        self.audio_source = audio_source
        self.buffer_capacity_s = buffer_capacity_s
        self.sample_rate = sample_rate
        
        # Communication queues
        self.capture_queue: Queue = Queue(maxsize=OUTPUT_QUEUE_MAXSIZE)
        self.features_queue: Queue = Queue(maxsize=OUTPUT_QUEUE_MAXSIZE)
        self.rendering_queue: Queue = Queue(maxsize=OUTPUT_QUEUE_MAXSIZE)
        
        # Shared circular buffer
        self.audio_buffer = CircularAudioBuffer(capacity_s=buffer_capacity_s, sample_rate=sample_rate)
        
        # Feature cache for GUI access (thread-safe)
        self.feature_cache = FeatureCache()
        
        # Shared multi-window analyzer (CRITICAL: one instance for all workers!)
        # This ensures all parallel workers feed beats into the SAME tempo tracker
        # so they accumulate for BPM calculation
        self.multi_analyzer = MultiWindowAudioAnalyzer(sample_rate=sample_rate)
        logger.info(f"[Pipeline] Created shared MultiWindowAnalyzer for all {n_processing_workers} workers")
        
        # Worker threads
        self.capture_worker = AudioCaptureWorker(
            "Capture",
            audio_source=self.audio_source,
            output_queue=self.capture_queue,
            buffer=self.audio_buffer,
            daemon=True,
        )
        
        self.processing_workers = [
            AudioProcessingWorker(
                f"Processing-{i}",
                input_queue=self.capture_queue,
                output_queue=self.features_queue,
                feature_cache=self.feature_cache,
                multi_analyzer=self.multi_analyzer,  # SHARED across all workers!
                daemon=True,
            )
            for i in range(n_processing_workers)
        ]
        
        self.analysis_worker = AnalysisWorker(
            "Analysis",
            input_queue=self.features_queue,
            output_queue=self.rendering_queue,
            event_callback=event_callback,
            daemon=True,
        )
        
        self.rendering_worker = RenderingWorker(
            "Rendering",
            input_queue=self.rendering_queue,
            daemon=True,
        )
        
        self._running = False

    def start(self) -> None:
        """Start all worker threads."""
        if self._running:
            logger.warning("Pipeline already running")
            return
        
        logger.info("Starting audio pipeline")
        self._running = True
        
        self.capture_worker.start()
        for worker in self.processing_workers:
            worker.start()
        self.analysis_worker.start()
        self.rendering_worker.start()

    def stop(self) -> None:
        """Stop all worker threads gracefully."""
        if not self._running:
            logger.warning("Pipeline not running")
            return
        
        logger.info("Stopping audio pipeline")
        self._running = False
        
        # Signal all workers to stop
        self.capture_worker.stop()
        for worker in self.processing_workers:
            worker.stop()
        self.analysis_worker.stop()
        self.rendering_worker.stop()

    def wait(self, timeout: float | None = None) -> None:
        """Wait for all workers to complete.
        
        Args:
            timeout: Maximum time to wait in seconds
        """
        self.capture_worker.join(timeout=timeout)
        for worker in self.processing_workers:
            worker.join(timeout=timeout)
        self.analysis_worker.join(timeout=timeout)
        self.rendering_worker.join(timeout=timeout)

    def is_running(self) -> bool:
        """Check if pipeline is running."""
        return self._running and all([
            self.capture_worker.is_alive(),
            all(w.is_alive() for w in self.processing_workers),
            self.analysis_worker.is_alive(),
            self.rendering_worker.is_alive(),
        ])

    def get_events(self) -> list[tuple[float, str]]:
        """Get list of detected events."""
        return list(self.analysis_worker.event_history)

    def get_latest_audio(self, duration_s: float = 2.0) -> bytes:
        """Get latest audio data from circular buffer.
        
        Args:
            duration_s: Duration to retrieve in seconds
            
        Returns:
            Audio samples as numpy array
        """
        return self.audio_buffer.read_latest(duration_s, self.sample_rate)
