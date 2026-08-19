"""Message dataclasses for inter-worker communication."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class AudioChunkMessage:
    """Message containing audio chunk data."""
    samples: np.ndarray  # Shape (n_samples, n_channels) in float32
    sample_rate: int


@dataclass
class AudioFeaturesMessage:
    """Message containing comprehensive computed audio features."""
    timestamp_s: float
    
    # Overall metrics
    overall_amplitude: float  # Peak absolute value (0-1)
    rms: float  # RMS volume (0-1)
    peak: float  # Peak volume (0-1)
    
    # Energy in frequency bands
    bass_energy: float  # Energy in 20-250 Hz (0-1)
    mid_energy: float  # Energy in 250-4000 Hz (0-1)
    high_energy: float  # Energy in 4000-20000 Hz (0-1)
    
    # Spectral features
    spectral_centroid_hz: float | None  # Brightness in Hz
    dominant_frequency_hz: float | None  # Most prominent frequency
    
    # Temporal features
    onset_detected: bool  # Attack/onset (quick energy rise)
    beat_detected: bool  # Beat peak in energy
    beat_confidence: float  # Confidence 0-1
    
    # Tempo
    bpm: float | None  # Beats per minute
    
    # Frequency band envelopes (for visualization)
    band_bass_envelope: tuple[float, ...] | None  # Bass band over time
    band_mid_envelope: tuple[float, ...] | None  # Mid band over time
    band_high_envelope: tuple[float, ...] | None  # High band over time


@dataclass
class RenderingMessage:
    """Simplified message for rendering/visualization.
    
    All values are normalized 0-1 for easy consumption by visualizers/games.
    Includes predictive beat timing for low-latency synchronization.
    """
    timestamp_s: float
    
    # Normalized energy levels
    bass: float  # Bass energy 0-1
    energy: float  # Overall energy 0-1
    brightness: float  # Spectral centroid normalized 0-1
    impact: float  # Transient/onset strength 0-1
    
    # Temporal events
    beat: bool  # Beat detected flag
    beat_confidence: float  # How confident about beat 0-1
    onset: bool  # Onset/attack detected
    
    # Derived metrics
    tempo_bpm: float | None  # Beats per minute
    dynamics: float  # RMS/peak ratio for dynamics
    
    # PREDICTIVE BEAT SYNCHRONIZATION
    beat_phase_0to1: float  # 0.0=just detected beat, 1.0=next beat arriving
    predicted_beat_timestamp_s: float | None  # When next beat is expected
    prediction_confidence: float  # How confident in prediction 0-1
