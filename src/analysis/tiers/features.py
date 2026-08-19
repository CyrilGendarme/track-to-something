"""Feature dataclasses for tiered audio analysis.

These dataclasses represent analysis results at three different time scales:
- Fast: 5-10ms (immediate transient detection)
- Medium: 20-50ms (smooth energy tracking)
- Slow: 100-500ms (overall dynamics and tempo)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FastFeatures:
    """Very fast features (5-10ms latency).
    
    Designed for immediate visual response: kicks, snares, transients, onsets.
    """
    timestamp_s: float
    
    # Transient detection (onset/attack)
    onset_detected: bool          # Rapid energy rise
    onset_strength: float         # 0-1 (how strong the onset is)
    
    # Percussive peak detection
    is_percussive_peak: bool      # True during kick/snare
    percussive_peak_strength: float  # 0-1 (amplitude of peak)
    
    # Raw energy in 10ms window
    raw_energy: float             # 0-1 (immediate amplitude)
    

@dataclass
class MediumFeatures:
    """Medium-speed features (20-50ms latency).
    
    For smooth energy tracking: bass energy, mid energy, spectral movement.
    """
    timestamp_s: float
    
    # Frequency band energy (20-50ms window)
    bass_energy: float            # 0-1 (20-250 Hz)
    mid_energy: float             # 0-1 (250-4000 Hz)
    high_energy: float            # 0-1 (4000-20000 Hz)
    
    # Spectral features
    spectral_centroid_hz: float   # Center of energy
    spectral_brightness: float    # 0-1 (normalized centroid)
    
    # Energy rate of change (for smooth animation)
    bass_energy_delta: float      # Change in bass since last update
    overall_energy_delta: float   # Change in total energy
    

@dataclass
class SlowFeatures:
    """Slow features (100-500ms latency).
    
    For scene/palette changes: overall energy shape, tempo tracking.
    """
    timestamp_s: float
    
    # Song-level metrics (over 0.5-2.0 second windows)
    average_energy: float         # Mean energy over window
    energy_variance: float        # Std dev (0-1)
    energy_trend: float           # -1 to 1 (decreasing to increasing)
    
    # Estimated tempo from beat intervals
    estimated_bpm: float | None   # Beats per minute
    beat_stability: float         # 0-1 (how consistent is the tempo)
    
    # Overall spectral shape (for color palette)
    spectral_density_low: float   # 0-1 (proportion of energy in bass)
    spectral_density_mid: float   # 0-1 (proportion of energy in mids)
    spectral_density_high: float  # 0-1 (proportion of energy in highs)
