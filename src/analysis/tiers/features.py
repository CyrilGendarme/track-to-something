"""Feature dataclasses for tiered audio analysis.

These dataclasses are the output contract of the pipeline (GUI + local API):
- Fast / Medium: produced by the real-time path on every hop (~6ms)
- Slow: assembled from background jobs (dynamics, BPM, key) as they complete
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FastFeatures:
    """Real-time transient and beat features (updated every hop).
    
    Designed for immediate visual response: kicks, snares, transients, onsets.
    """
    timestamp_s: float
    
    # Transient detection (onset/attack)
    onset_detected: bool          # Rapid energy rise
    onset_strength: float         # 0-1 (how strong the onset is)
    
    # Percussive peak detection
    is_percussive_peak: bool      # True during kick/snare
    percussive_peak_strength: float  # 0-1 (amplitude of peak)
    
    # RMS of the newest hop
    raw_energy: float             # 0-1 (immediate amplitude)
    
    # Beat tracking (phase-locked to the consensus tempo when available)
    beat_detected: bool = False   # True on the hop where a (predicted) beat falls
    beat_phase: float = 0.0       # 0 at a beat, rising towards 1 just before the next
    beat_confidence: float = 0.0  # 0-1 lock quality of the beat tracker
    tempo_bpm: float | None = None  # Tempo the tracker is currently using
    predicted_next_beat_s: float | None = None  # Stream time of the next beat

@dataclass
class MediumFeatures:
    """Smoothed band levels (updated every hop).
    
    Levels are relative to a slowly decaying recent peak per band, so 1.0
    means "as loud as this band has recently been", not "loudest band".
    """
    timestamp_s: float
    
    # Frequency band energy (attack/release smoothed)
    bass_energy: float            # 0-1 (20-250 Hz)
    mid_energy: float             # 0-1 (250-4000 Hz)
    high_energy: float            # 0-1 (4000-20000 Hz)
    
    # Energy rate of change (for smooth animation)
    bass_energy_delta: float      # Change in bass since last update
    overall_energy_delta: float   # Change in total energy
    

@dataclass
class SlowFeatures:
    """Big-picture features assembled from background jobs.
    
    For scene/palette changes: overall energy shape, tempo, tonality. Levels
    and dynamics come from the dynamics job (a few-second window), tempo
    from the multi-method BPM job, key from the key job; transient fields
    summarize the real-time path over the same window.
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
