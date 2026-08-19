"""Tiered rendering format for multi-window audio analysis.

Combines fast, medium, and slow features in a single message with clear
latency guarantees for game/UI integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.analysis import FastFeatures, MediumFeatures, SlowFeatures


@dataclass
class TieredRenderingMessage:
    """Rendering message with three latency tiers.
    
    Use this instead of RenderingMessage when you have multiple analysis windows.
    """
    
    timestamp_s: float
    
    # ──────────────────────────────────────────────────────────────────────────
    # TIER 1: VERY FAST (5-10ms latency)
    # Use for: Kick/snare detection, transient flashes, immediate visual feedback
    # ──────────────────────────────────────────────────────────────────────────
    
    # KICK DETECTION (bass transient)
    kick_detected: bool                   # True when bass kicks
    kick_strength: float                  # 0-1 (amplitude of kick)
    
    # SNARE/PERCUSSION DETECTION (mid/high transient)
    snare_detected: bool                  # True when snare/hi-hat hits
    snare_strength: float                 # 0-1 (amplitude of snare)
    
    # GENERAL TRANSIENT DETECTION
    transient_detected: bool              # Any rapid attack
    transient_strength: float             # 0-1 (how percussive)
    
    # Raw immediate energy (for responsive scaling)
    immediate_energy: float               # 0-1 (current amplitude)
    
    # ──────────────────────────────────────────────────────────────────────────
    # TIER 2: MEDIUM (20-50ms latency)
    # Use for: Energy tracking, smooth object scaling, spectral effects
    # ──────────────────────────────────────────────────────────────────────────
    
    # Frequency bands (for color/scale mapping)
    bass_energy: float                    # 0-1
    mid_energy: float                     # 0-1
    high_energy: float                    # 0-1
    
    # Spectral characteristics
    brightness: float                     # 0-1 (spectral centroid)
    spectral_centroid_hz: float | None   # Hz
    
    # Change rates (for smooth animation interpolation)
    bass_energy_change_per_sec: float    # Acceleration of bass
    overall_energy_change_per_sec: float # Acceleration of overall
    
    # ──────────────────────────────────────────────────────────────────────────
    # TIER 3: SLOW (100-500ms latency)
    # Use for: Scene changes, palette shifts, overall dynamics
    # ──────────────────────────────────────────────────────────────────────────
    
    # Song-level energy metrics
    average_energy: float                 # 0-1 (typical loudness over window)
    energy_variance: float                # 0-1 (how dynamic the section is)
    energy_trend: float                   # -1 to 1 (building or fading)
    
    # Spectral density (for color palette)
    spectral_density_bass: float         # 0-1 (proportion of energy in bass)
    spectral_density_mid: float          # 0-1 (proportion of energy in mid)
    spectral_density_high: float         # 0-1 (proportion of energy in high)
    
    # Tempo tracking (from beat history)
    estimated_bpm: float | None          # Beats per minute
    beat_stability: float                 # 0-1 (how steady the tempo)
    
    # ──────────────────────────────────────────────────────────────────────────
    # PREDICTIVE BEAT SYNC (all tiers)
    # ──────────────────────────────────────────────────────────────────────────
    
    beat_phase_0to1: float               # 0=beat, 1=next beat
    predicted_beat_timestamp_s: float | None  # When next beat arrives
    prediction_confidence: float         # 0-1 (tempo stability)


def combine_features(
    fast: FastFeatures,
    medium: MediumFeatures,
    slow: SlowFeatures,
    beat_phase: float,
    predicted_beat: float | None,
    prediction_confidence: float,
) -> TieredRenderingMessage:
    """Combine tiered features into a single rendering message.
    
    Args:
        fast: Fast analysis result
        medium: Medium analysis result
        slow: Slow analysis result
        beat_phase: Current beat phase (0-1)
        predicted_beat: Predicted next beat timestamp
        prediction_confidence: Confidence in prediction (0-1)
        
    Returns:
        TieredRenderingMessage ready for rendering
    """
    
    # TIER 1: Detect kick vs snare from fast features
    kick_detected = fast.is_percussive_peak and fast.raw_energy > 0.7
    snare_detected = fast.is_percussive_peak and fast.raw_energy <= 0.7
    
    # TIER 2: Scale delta to per-second rate
    # Assuming ~10-20ms windows, scale appropriately
    bass_energy_change_per_sec = medium.bass_energy_delta * 100  # Rough scaling
    overall_energy_change_per_sec = medium.overall_energy_delta * 100
    
    return TieredRenderingMessage(
        timestamp_s=fast.timestamp_s,
        
        # Tier 1: Very fast
        kick_detected=kick_detected,
        kick_strength=fast.percussive_peak_strength if kick_detected else 0.0,
        snare_detected=snare_detected,
        snare_strength=fast.percussive_peak_strength if snare_detected else 0.0,
        transient_detected=fast.onset_detected,
        transient_strength=fast.onset_strength,
        immediate_energy=fast.raw_energy,
        
        # Tier 2: Medium
        bass_energy=medium.bass_energy,
        mid_energy=medium.mid_energy,
        high_energy=medium.high_energy,
        brightness=medium.spectral_brightness,
        spectral_centroid_hz=medium.spectral_centroid_hz,
        bass_energy_change_per_sec=bass_energy_change_per_sec,
        overall_energy_change_per_sec=overall_energy_change_per_sec,
        
        # Tier 3: Slow
        average_energy=slow.average_energy,
        energy_variance=slow.energy_variance,
        energy_trend=slow.energy_trend,
        spectral_density_bass=slow.spectral_density_low,
        spectral_density_mid=slow.spectral_density_mid,
        spectral_density_high=slow.spectral_density_high,
        estimated_bpm=slow.estimated_bpm,
        beat_stability=slow.beat_stability,
        
        # Beat prediction
        beat_phase_0to1=beat_phase,
        predicted_beat_timestamp_s=predicted_beat,
        prediction_confidence=prediction_confidence,
    )
