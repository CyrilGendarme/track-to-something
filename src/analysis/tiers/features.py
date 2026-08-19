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
    
    # Energy rate of change (for smooth animation)
    bass_energy_delta: float      # Change in bass since last update
    overall_energy_delta: float   # Change in total energy
    

@dataclass
class SlowFeatures:
    """Slow features (100-500ms latency).
    
    For scene/palette changes: overall energy shape, tempo tracking, tonality analysis.
    Aggregates all FAST, MEDIUM metrics over longer time window (0.5-2.0s) for big-picture analysis.
    """
    timestamp_s: float
    
    # ════════════════════════════════════════════════════════════════════
    # AMPLITUDE METRICS (aggregated from FAST tier over window)
    # ════════════════════════════════════════════════════════════════════
    overall_amplitude: float      # 0-1 (peak absolute value in window)
    rms: float                    # 0-1 (RMS energy in window)
    peak: float                   # 0-1 (peak volume in window)
    
    # ════════════════════════════════════════════════════════════════════
    # FREQUENCY BAND ENERGY (aggregated from MEDIUM tier over window)
    # ════════════════════════════════════════════════════════════════════
    bass_energy: float            # 0-1 (20-250 Hz average)
    mid_energy: float             # 0-1 (250-4000 Hz average)
    high_energy: float            # 0-1 (4000-20000 Hz average)
    
    # ════════════════════════════════════════════════════════════════════
    # SPECTRAL CHARACTERISTICS (average over window for color palette)
    # ════════════════════════════════════════════════════════════════════
    spectral_density_low: float   # 0-1 (proportion of energy in bass)
    spectral_density_mid: float   # 0-1 (proportion of energy in mids)
    spectral_density_high: float  # 0-1 (proportion of energy in highs)
    
    # ════════════════════════════════════════════════════════════════════
    # TONALITY ANALYSIS (musical key detection)
    # ════════════════════════════════════════════════════════════════════
    detected_key: str | None      # Musical key (e.g., "C", "F#m", "Bm", "Db")
    key_confidence: float         # 0-1 (confidence in key detection)
    
    # ════════════════════════════════════════════════════════════════════
    # TRANSIENT & BEAT DETECTION (aggregated from FAST tier)
    # ════════════════════════════════════════════════════════════════════
    onset_detected: bool          # Any onsets in window
    beat_detected: bool           # Beat peaks detected
    beat_confidence: float        # 0-1 (average beat confidence)
    
    # ════════════════════════════════════════════════════════════════════
    # TEMPO TRACKING (for animation speed)
    # ════════════════════════════════════════════════════════════════════
    estimated_bpm: float | None   # Beats per minute
    beat_stability: float         # 0-1 (how consistent is the tempo)
    
    # ════════════════════════════════════════════════════════════════════
    # DYNAMICS & TREND (overall song energy → scene changes)
    # ════════════════════════════════════════════════════════════════════
    average_energy: float         # Mean energy over window
    energy_variance: float        # Std dev (0-1)
    energy_trend: float           # -1 to 1 (decreasing to increasing)
    
    # ════════════════════════════════════════════════════════════════════
    # FREQUENCY BAND ENVELOPES (for smooth visualization)
    # ════════════════════════════════════════════════════════════════════
    band_bass_envelope: tuple[float, ...] | None      # Bass energy over time
    band_mid_envelope: tuple[float, ...] | None       # Mid energy over time
    band_high_envelope: tuple[float, ...] | None      # High energy over time
