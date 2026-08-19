"""Slow audio analyzer - 100-500ms latency for overall dynamics and tempo."""

from __future__ import annotations

import logging

import numpy as np
from scipy import signal

from src.config import (
    DEFAULT_SAMPLE_RATE,
    SLOW_WINDOW_MS,
    BEAT_HISTORY_SIZE,
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_MID_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_HIGH_MIN,
)
from .features import SlowFeatures

logger = logging.getLogger(__name__)


class SlowAnalyzer:
    """Analyzes audio in 100-500ms windows for overall shape and tempo."""
    
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, window_size_ms: float = SLOW_WINDOW_MS, max_beat_history: int = BEAT_HISTORY_SIZE):
        """Initialize slow analyzer.
        
        Args:
            sample_rate: Audio sample rate in Hz (default from config)
            window_size_ms: Analysis window in milliseconds (default from config)
            max_beat_history: Number of beats to track for tempo estimation (default from config)
        """
        self.sample_rate = sample_rate
        self.window_size_ms = window_size_ms
        self.window_size_samples = int(window_size_ms * sample_rate / 1000)
        self.hop_size_samples = self.window_size_samples // 2
        
        # Tempo tracking
        self.beat_timestamps = []
        self.max_beat_history = max_beat_history
        
        # Energy history for trend calculation
        self.energy_history = []
        self.max_history = 10
        
        logger.info(f"[SlowAnalyzer] {window_size_ms:.1f}ms windows ({self.window_size_samples} samples)")
    
    def record_beat(self, timestamp_s: float) -> None:
        """Record a beat detection for tempo estimation.
        
        Args:
            timestamp_s: Timestamp of beat
        """
        self.beat_timestamps.append(timestamp_s)
        if len(self.beat_timestamps) > self.max_beat_history:
            self.beat_timestamps.pop(0)
    
    def analyze(self, audio_chunk: np.ndarray, timestamp_s: float) -> SlowFeatures:
        """Analyze audio chunk for slow features.
        
        Args:
            audio_chunk: Audio samples (n_samples, 2) in float32
            timestamp_s: Timestamp of chunk start
            
        Returns:
            SlowFeatures with average energy, trend, tempo, etc.
        """
        # Convert stereo to mono
        if audio_chunk.ndim == 2:
            audio_mono = np.mean(audio_chunk, axis=1)
        else:
            audio_mono = audio_chunk
        
        # Average energy over window
        average_energy = np.sqrt(np.mean(audio_mono ** 2))
        average_energy = min(1.0, average_energy)
        
        # Track energy history for variance and trend
        self.energy_history.append(average_energy)
        if len(self.energy_history) > self.max_history:
            self.energy_history.pop(0)
        
        # Energy statistics
        energy_variance = float(np.var(self.energy_history)) if len(self.energy_history) > 1 else 0.0
        
        # Trend (positive = increasing, negative = decreasing)
        if len(self.energy_history) > 2:
            recent = self.energy_history[-3:]
            trend = float(np.polyfit(range(len(recent)), recent, 1)[0])  # Slope
            trend = max(-1.0, min(1.0, trend))  # Clamp to -1 to 1
        else:
            trend = 0.0
        
        # Tempo estimation from beat history
        estimated_bpm = None
        beat_stability = 0.0
        
        if len(self.beat_timestamps) >= 3:
            intervals = np.diff(self.beat_timestamps)
            avg_interval = np.mean(intervals)
            interval_std = np.std(intervals)
            
            # Convert to BPM
            beats_per_second = 1.0 / avg_interval
            estimated_bpm = beats_per_second * 60.0
            
            # Stability: how consistent are the intervals?
            # Lower std = higher stability
            beat_stability = max(0.0, 1.0 - (interval_std / avg_interval / 0.2))
        
        # STFT for spectral density
        fft_size = 2048
        window = signal.windows.hann(min(len(audio_mono), fft_size), sym=False)
        if len(audio_mono) < fft_size:
            audio_mono = np.pad(audio_mono, (0, fft_size - len(audio_mono)))
        
        stft = np.fft.rfft(audio_mono[:fft_size] * window)
        magnitude = np.abs(stft)
        freqs = np.fft.rfftfreq(fft_size, 1.0 / self.sample_rate)
        
        # Spectral density (proportion of energy in each band)
        bass_mask = freqs < FREQ_BAND_BASS_MAX
        mid_mask = (freqs >= FREQ_BAND_MID_MIN) & (freqs < FREQ_BAND_MID_MAX)
        high_mask = freqs >= FREQ_BAND_HIGH_MIN
        
        total_energy = np.sum(magnitude)
        if total_energy > 0:
            spectral_density_low = np.sum(magnitude[bass_mask]) / total_energy
            spectral_density_mid = np.sum(magnitude[mid_mask]) / total_energy
            spectral_density_high = np.sum(magnitude[high_mask]) / total_energy
        else:
            spectral_density_low = 0.33
            spectral_density_mid = 0.33
            spectral_density_high = 0.34
        
        return SlowFeatures(
            timestamp_s=timestamp_s,
            average_energy=average_energy,
            energy_variance=float(energy_variance),
            energy_trend=trend,
            estimated_bpm=estimated_bpm,
            beat_stability=beat_stability,
            spectral_density_low=float(spectral_density_low),
            spectral_density_mid=float(spectral_density_mid),
            spectral_density_high=float(spectral_density_high),
        )
