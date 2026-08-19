"""Multi-window audio analysis for low-latency, tiered feature extraction.

Instead of one audio capture pipeline with one analysis window, this uses:
- ONE continuous circular audio buffer (very small, 10-50ms)
- MULTIPLE overlapping analysis windows with different rates
- Fast path: 5-10ms windows for immediate transient detection
- Medium path: 20-50ms windows for energy/spectral analysis
- Slow path: 100-500ms windows for overall shape/tempo

This eliminates redundancy and dramatically improves latency for fast features.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from src.config import (
    DEFAULT_SAMPLE_RATE,
    FAST_WINDOW_MS,
    MEDIUM_WINDOW_MS,
    SLOW_WINDOW_MS,
)
from src.analysis.tiers import (
    FastFeatures,
    MediumFeatures,
    SlowFeatures,
    FastAnalyzer,
    MediumAnalyzer,
    SlowAnalyzer,
)

logger = logging.getLogger(__name__)


class MultiWindowAudioAnalyzer:
    """Manages all three analysis windows over a single continuous audio stream.
    
    This is much more efficient than three independent pipelines.
    All three analyzers read from the SAME circular audio buffer.
    """
    
    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        fast_window_ms: float = FAST_WINDOW_MS,
        medium_window_ms: float = MEDIUM_WINDOW_MS,
        slow_window_ms: float = SLOW_WINDOW_MS,
    ):
        """Initialize multi-window analyzer.
        
        Args:
            sample_rate: Audio sample rate (default from config)
            fast_window_ms: Window size for fast analysis (default from config)
            medium_window_ms: Window size for medium analysis (default from config)
            slow_window_ms: Window size for slow analysis (default from config)
        """
        self.sample_rate = sample_rate
        
        self.fast_analyzer = FastAnalyzer(sample_rate, fast_window_ms)
        self.medium_analyzer = MediumAnalyzer(sample_rate, medium_window_ms)
        self.slow_analyzer = SlowAnalyzer(sample_rate, slow_window_ms)
        
        # Shared circular buffer (small, 50-100ms)
        self.buffer_size_ms = 100.0
        self.buffer_size_samples = int(self.buffer_size_ms * sample_rate / 1000)
        self.circular_buffer = np.zeros((self.buffer_size_samples, 2), dtype=np.float32)
        self.write_pos = 0
        self.lock = threading.RLock()
        
        logger.info(f"[MultiWindowAnalyzer] Initialized with shared buffer: {self.buffer_size_ms:.0f}ms")
    
    def add_audio_chunk(self, audio_chunk: np.ndarray) -> None:
        """Add audio chunk to circular buffer.
        
        Args:
            audio_chunk: Audio samples (n_samples, 2) in float32
        """
        with self.lock:
            chunk_len = len(audio_chunk)
            
            # Handle wrap-around
            remaining = self.buffer_size_samples - self.write_pos
            
            if chunk_len <= remaining:
                self.circular_buffer[self.write_pos:self.write_pos + chunk_len] = audio_chunk
            else:
                # Split across wrap-around
                self.circular_buffer[self.write_pos:] = audio_chunk[:remaining]
                self.circular_buffer[:chunk_len - remaining] = audio_chunk[remaining:]
            
            self.write_pos = (self.write_pos + chunk_len) % self.buffer_size_samples
    
    def get_recent_audio(self, duration_ms: float) -> np.ndarray:
        """Get recent audio from circular buffer.
        
        Args:
            duration_ms: How much audio to return (milliseconds)
            
        Returns:
            Audio array of requested length
        """
        num_samples = int(duration_ms * self.sample_rate / 1000)
        num_samples = min(num_samples, self.buffer_size_samples)
        
        with self.lock:
            start_pos = (self.write_pos - num_samples) % self.buffer_size_samples
            
            if start_pos + num_samples <= self.buffer_size_samples:
                return self.circular_buffer[start_pos:start_pos + num_samples].copy()
            else:
                # Wrap-around
                part1 = self.circular_buffer[start_pos:]
                part2 = self.circular_buffer[:num_samples - len(part1)]
                return np.vstack([part1, part2])
    
    def analyze_all(self, timestamp_s: float) -> tuple[FastFeatures, MediumFeatures, SlowFeatures]:
        """Run all three analyzers on current buffer state.
        
        Feeds FAST/MEDIUM features into SlowAnalyzer for better aggregation.
        
        Args:
            timestamp_s: Current timestamp
            
        Returns:
            Tuple of (FastFeatures, MediumFeatures, SlowFeatures)
        """
        # Get appropriate audio windows for each analyzer
        # Request 1.5x window size to ensure we have enough data
        fast_duration_ms = (self.fast_analyzer.window_size_samples / self.sample_rate) * 1000 * 1.5
        medium_duration_ms = (self.medium_analyzer.window_size_samples / self.sample_rate) * 1000 * 1.5
        slow_duration_ms = (self.slow_analyzer.window_size_samples / self.sample_rate) * 1000 * 1.5
        
        fast_audio = self.get_recent_audio(fast_duration_ms)
        medium_audio = self.get_recent_audio(medium_duration_ms)
        slow_audio = self.get_recent_audio(slow_duration_ms)
        
        # Run FAST and MEDIUM analyses
        fast_features = self.fast_analyzer.analyze(fast_audio, timestamp_s)
        medium_features = self.medium_analyzer.analyze(medium_audio, timestamp_s)
        
        # Feed FAST/MEDIUM metrics into SlowAnalyzer for aggregation
        # This allows slow tier to accumulate metrics for better trends
        self.slow_analyzer.update_metrics(
            overall_amplitude=fast_features.raw_energy,
            rms=fast_features.raw_energy,  # Use raw_energy as proxy for RMS
            bass_energy=medium_features.bass_energy,
            mid_energy=medium_features.mid_energy,
            high_energy=medium_features.high_energy,
            onset_detected=fast_features.onset_detected,
            beat_confidence=0.0,  # Will be set by beat detection
        )
        
        # Run SLOW analysis with all metrics aggregated
        slow_features = self.slow_analyzer.analyze(slow_audio, timestamp_s)
        
        return fast_features, medium_features, slow_features
    
    def record_beat_detection(self, timestamp_s: float) -> None:
        """Record beat for tempo tracking.
        
        Args:
            timestamp_s: Timestamp of beat detection
        """
        self.slow_analyzer.record_beat(timestamp_s)
