"""Medium audio analyzer - 20-50ms latency for smooth energy tracking."""

from __future__ import annotations

import logging

import numpy as np
from scipy import signal

from src.config import (
    DEFAULT_SAMPLE_RATE,
    MEDIUM_WINDOW_MS,
    STFT_FFT_SIZE,
    STFT_HOP_LENGTH,
    FREQ_BAND_BASS_MIN,
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_MID_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_HIGH_MIN,
    FREQ_BAND_HIGH_MAX,
)
from .features import MediumFeatures

logger = logging.getLogger(__name__)


class MediumAnalyzer:
    """Analyzes audio in 20-50ms windows for smooth energy tracking."""
    
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, window_size_ms: float = MEDIUM_WINDOW_MS):
        """Initialize medium analyzer.
        
        Args:
            sample_rate: Audio sample rate in Hz (default from config)
            window_size_ms: Analysis window in milliseconds (default from config)
        """
        self.sample_rate = sample_rate
        self.window_size_ms = window_size_ms
        self.window_size_samples = int(window_size_ms * sample_rate / 1000)
        self.hop_size_samples = self.window_size_samples // 4  # 75% overlap = 25% new data
        
        # Frequency band definitions (from config)
        self.fft_size = STFT_FFT_SIZE
        self.hop_length = STFT_HOP_LENGTH
        
        # Previous state for delta calculation
        self.prev_overall_energy = 0.0
        self.prev_bass_energy = 0.0
        
        logger.info(f"[MediumAnalyzer] {window_size_ms:.1f}ms windows ({self.window_size_samples} samples)")
    
    def analyze(self, audio_chunk: np.ndarray, timestamp_s: float) -> MediumFeatures:
        """Analyze audio chunk for medium features.
        
        Args:
            audio_chunk: Audio samples (n_samples, 2) in float32
            timestamp_s: Timestamp of chunk start
            
        Returns:
            MediumFeatures with energy bands, spectral info, etc.
        """
        # Convert stereo to mono
        if audio_chunk.ndim == 2:
            audio_mono = np.mean(audio_chunk, axis=1)
        else:
            audio_mono = audio_chunk
        
        # Compute STFT with smaller window for low latency
        # Use Hann window for spectral analysis
        window = signal.windows.hann(min(len(audio_mono), self.fft_size), sym=False)
        if len(audio_mono) < self.fft_size:
            # Pad if too short
            audio_mono = np.pad(audio_mono, (0, self.fft_size - len(audio_mono)))
        
        stft = np.fft.rfft(audio_mono[:self.fft_size] * window)
        magnitude = np.abs(stft)
        
        # Frequency bins
        freqs = np.fft.rfftfreq(self.fft_size, 1.0 / self.sample_rate)
        
        # Extract frequency bands (from config)
        bass_mask = freqs < FREQ_BAND_BASS_MAX
        mid_mask = (freqs >= FREQ_BAND_MID_MIN) & (freqs < FREQ_BAND_MID_MAX)
        high_mask = freqs >= FREQ_BAND_HIGH_MIN
        
        bass_energy = np.mean(magnitude[bass_mask]) if np.any(bass_mask) else 0.0
        mid_energy = np.mean(magnitude[mid_mask]) if np.any(mid_mask) else 0.0
        high_energy = np.mean(magnitude[high_mask]) if np.any(high_mask) else 0.0
        
        # Normalize to 0-1 (use max magnitude as reference)
        max_mag = np.max(magnitude) if np.max(magnitude) > 0 else 1.0
        bass_energy = min(1.0, bass_energy / max_mag)
        mid_energy = min(1.0, mid_energy / max_mag)
        high_energy = min(1.0, high_energy / max_mag)
        
        # Spectral centroid
        if np.sum(magnitude) > 0:
            spectral_centroid_hz = np.sum(freqs * magnitude) / np.sum(magnitude)
        else:
            spectral_centroid_hz = 0.0
        
        # Normalize to 0-1 (20Hz to 20kHz range)
        spectral_brightness = max(0.0, min(1.0, (spectral_centroid_hz - 20) / (20000 - 20)))
        
        # Energy deltas for smooth animation
        overall_energy = max(bass_energy, mid_energy, high_energy)
        bass_energy_delta = bass_energy - self.prev_bass_energy
        overall_energy_delta = overall_energy - self.prev_overall_energy
        
        self.prev_bass_energy = bass_energy
        self.prev_overall_energy = overall_energy
        
        return MediumFeatures(
            timestamp_s=timestamp_s,
            bass_energy=bass_energy,
            mid_energy=mid_energy,
            high_energy=high_energy,
            spectral_centroid_hz=spectral_centroid_hz,
            spectral_brightness=spectral_brightness,
            bass_energy_delta=bass_energy_delta,
            overall_energy_delta=overall_energy_delta,
        )
