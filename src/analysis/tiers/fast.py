"""Fast audio analyzer - 5-10ms latency for immediate response."""

from __future__ import annotations

import logging

import numpy as np

from src.config import DEFAULT_SAMPLE_RATE, FAST_WINDOW_MS
from .features import FastFeatures

logger = logging.getLogger(__name__)


class FastAnalyzer:
    """Analyzes audio in 5-10ms windows for immediate response."""
    
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, window_size_ms: float = FAST_WINDOW_MS):
        """Initialize fast analyzer.
        
        Args:
            sample_rate: Audio sample rate in Hz (default from config)
            window_size_ms: Analysis window in milliseconds (default from config)
        """
        self.sample_rate = sample_rate
        self.window_size_ms = window_size_ms
        self.window_size_samples = int(window_size_ms * sample_rate / 1000)
        self.hop_size_samples = self.window_size_samples // 2  # 50% overlap
        
        # Onset detection
        self.prev_energy = 0.0
        self.energy_threshold = 0.1
        
        logger.info(f"[FastAnalyzer] {window_size_ms:.1f}ms windows ({self.window_size_samples} samples)")
    
    def analyze(self, audio_chunk: np.ndarray, timestamp_s: float) -> FastFeatures:
        """Analyze audio chunk for fast features.
        
        Args:
            audio_chunk: Audio samples (n_samples, 2) in float32
            timestamp_s: Timestamp of chunk start
            
        Returns:
            FastFeatures with onset, peak detection, etc.
        """
        # Convert stereo to mono
        if audio_chunk.ndim == 2:
            audio_mono = np.mean(audio_chunk, axis=1)
        else:
            audio_mono = audio_chunk
        
        # Current window energy
        raw_energy = np.sqrt(np.mean(audio_mono ** 2))
        raw_energy = min(1.0, raw_energy)  # Clamp to 0-1
        
        # ONSET DETECTION: sudden energy increase
        energy_delta = raw_energy - self.prev_energy
        onset_detected = energy_delta > self.energy_threshold
        onset_strength = min(1.0, max(0.0, energy_delta / self.energy_threshold))
        
        # PERCUSSIVE PEAK DETECTION: high energy in short burst
        # Peaks over 0.7 with rapid attack = kick/snare-like
        is_percussive_peak = raw_energy > 0.7 and onset_strength > 0.5
        percussive_peak_strength = raw_energy if is_percussive_peak else 0.0
        
        self.prev_energy = raw_energy
        
        return FastFeatures(
            timestamp_s=timestamp_s,
            onset_detected=onset_detected,
            onset_strength=onset_strength,
            is_percussive_peak=is_percussive_peak,
            percussive_peak_strength=percussive_peak_strength,
            raw_energy=raw_energy,
        )
