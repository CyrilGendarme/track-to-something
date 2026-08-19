"""Clean separation of audio events from continuous signals.

This module defines:
- AudioEvent: Discrete point-in-time occurrences (beat detected, kick, etc.)
- ContinuousSignals: Smooth time-varying values (bass energy, brightness, etc.)

This separation allows different consumption patterns:
- Events: Trigger callbacks, play sound effects, flash lights
- Continuous signals: Interpolate, animate smoothly, update parameters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EventType(Enum):
    """Types of audio events."""
    
    # Temporal events (rhythm/beat)
    BEAT = "beat"                      # Detected beat
    KICK = "kick"                      # Bass transient (kick drum)
    SNARE = "snare"                    # Mid/high transient (snare, clap, hi-hat)
    CYMBAL = "cymbal"                  # High transient (cymbal, shaker)
    PERCUSSION = "percussion"          # Generic percussion hit
    
    # Energy events (sudden changes)
    ONSET = "onset"                    # Attack/onset (any rapid energy rise)
    ENERGY_SPIKE = "energy_spike"      # Sudden increase in overall energy
    ENERGY_DROP = "energy_drop"        # Sudden decrease in overall energy
    TRANSIENT = "transient"            # Generic rapid attack
    
    # Sustained state changes
    SILENCE_STARTED = "silence_started"  # Energy dropped below threshold
    SILENCE_ENDED = "silence_ended"      # Energy rose above threshold
    
    # Spectral events
    BASS_SURGE = "bass_surge"          # Bass energy spike
    TREBLE_SURGE = "treble_surge"      # High frequency energy spike


@dataclass
class AudioEvent:
    """Discrete audio event at a specific timestamp.
    
    Events are point-in-time occurrences that trigger immediate actions.
    Unlike continuous signals, events have no duration (or instantaneous duration).
    
    Examples:
        - Beat detected at 10.5s with confidence 0.95
        - Kick detected at 10.52s with strength 0.8
        - Onset detected at 10.55s with strength 0.6
    """
    
    event_type: EventType          # Type of event
    timestamp_s: float             # When it occurred
    
    # Amplitude/strength of the event (0-1, meaning varies by type)
    strength: float = 1.0          # How strong/prominent
    confidence: float = 1.0        # How confident in detection (0-1)
    
    # Additional context
    metadata: dict = field(default_factory=dict)  # Type-specific data
    
    def __post_init__(self):
        """Validate field ranges."""
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"strength must be 0-1, got {self.strength}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0-1, got {self.confidence}")
    
    def __str__(self) -> str:
        """Human-readable event description."""
        return (f"[{self.timestamp_s:.2f}s] {self.event_type.value.upper()} "
                f"(strength={self.strength:.2f}, conf={self.confidence:.2f})")


@dataclass
class ContinuousSignals:
    """Smooth time-varying signals.
    
    All values are continuous (not discrete steps) and suitable for
    interpolation, smoothing, and animation. Use these for:
    - Smooth scaling/distortion
    - Color/brightness transitions
    - Parameter modulation
    - Animation easing
    
    Values are normalized 0-1 where possible for easy consumption.
    """
    
    timestamp_s: float              # Current time
    
    # ──────────────────────────────────────────────────────────────────────────
    # TIER 1: VERY FAST (5-10ms latency)
    # Use for: Direct visual response to immediate energy
    # ──────────────────────────────────────────────────────────────────────────
    
    immediate_energy: float         # Current audio amplitude (0-1)
    immediate_energy_derivative: float  # How fast it's changing (change/sec)
    
    # ──────────────────────────────────────────────────────────────────────────
    # TIER 2: MEDIUM (20-50ms latency)
    # Use for: Smooth energy tracking, spectral effects
    # ──────────────────────────────────────────────────────────────────────────
    
    # Frequency bands (smooth)
    bass_energy: float              # 20-250 Hz energy (0-1)
    mid_energy: float               # 250-4k Hz energy (0-1)
    high_energy: float              # 4k-20k Hz energy (0-1)
    
    # Spectral characteristics
    brightness: float               # Spectral centroid normalized (0-1)
    spectral_centroid_hz: Optional[float]  # Actual centroid in Hz
    
    # Spectral distribution
    spectral_density_bass: float    # Proportion of energy in bass (0-1)
    spectral_density_mid: float     # Proportion of energy in mid (0-1)
    spectral_density_high: float    # Proportion of energy in high (0-1)
    
    # Energy rates (for smooth animation)
    bass_energy_derivative: float   # How fast bass is changing (change/sec)
    overall_energy_derivative: float  # How fast overall energy is changing
    
    # ──────────────────────────────────────────────────────────────────────────
    # TIER 3: SLOW (100-500ms latency)
    # Use for: Scene changes, palette shifts, overall dynamics
    # ──────────────────────────────────────────────────────────────────────────
    
    # Sustained energy metrics
    average_energy: float           # Typical loudness over window (0-1)
    energy_variance: float          # How dynamic the section (0-1)
    energy_trend: float             # Building vs fading (-1 to 1)
    
    # Tempo/rhythm
    estimated_bpm: Optional[float]  # Beats per minute
    beat_stability: float           # Tempo consistency (0-1)
    beat_phase_0to1: float         # Phase within beat (0=beat, 1=next)
    
    # ──────────────────────────────────────────────────────────────────────────
    # PREDICTIVE BEAT SYNC (all tiers)
    # Use for: Zero-latency beat-synced effects
    # ──────────────────────────────────────────────────────────────────────────
    
    predicted_beat_timestamp_s: Optional[float]  # When next beat arrives
    prediction_confidence: float    # How confident in prediction (0-1)
    
    def __post_init__(self):
        """Validate all 0-1 ranges."""
        fields_01 = [
            'immediate_energy', 'bass_energy', 'mid_energy', 'high_energy',
            'brightness', 'spectral_density_bass', 'spectral_density_mid',
            'spectral_density_high', 'average_energy', 'energy_variance',
            'beat_stability', 'beat_phase_0to1', 'prediction_confidence',
        ]
        
        for field_name in fields_01:
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be 0-1, got {value}")
        
        if not -1.0 <= self.energy_trend <= 1.0:
            raise ValueError(f"energy_trend must be -1 to 1, got {self.energy_trend}")


@dataclass
class AudioFrame:
    """Combined audio analysis frame.
    
    Contains both discrete events and continuous signals at same timestamp.
    This is what you typically receive from the audio engine.
    
    Usage:
        frame = audio_analyzer.get_frame()
        
        # Handle events
        for event in frame.events:
            if event.event_type == EventType.KICK:
                screen.flash()
        
        # Animate with continuous signals
        object.scale = 1.0 + frame.signals.bass_energy * 0.5
        object.color.hue = frame.signals.brightness * 360
    """
    
    timestamp_s: float
    signals: ContinuousSignals
    events: list[AudioEvent] = field(default_factory=list)
    
    def __str__(self) -> str:
        """Summary of frame contents."""
        event_str = ", ".join(e.event_type.value for e in self.events) if self.events else "none"
        return (f"Frame @ {self.timestamp_s:.2f}s | "
                f"Energy={self.signals.average_energy:.2f} "
                f"Events=[{event_str}]")


def merge_frames(*frames: AudioFrame) -> AudioFrame:
    """Merge multiple frames at nearby timestamps.
    
    Useful when different analysis windows produce results at slightly
    different times but you want to combine them for visualization.
    
    Args:
        frames: AudioFrame objects to merge
        
    Returns:
        Single merged frame with averaged signals and combined events
    """
    if not frames:
        raise ValueError("Must provide at least one frame")
    
    # Average timestamp
    avg_timestamp = sum(f.timestamp_s for f in frames) / len(frames)
    
    # Average all signals (simple mean)
    signals_list = [f.signals for f in frames]
    merged_signals = ContinuousSignals(
        timestamp_s=avg_timestamp,
        immediate_energy=sum(s.immediate_energy for s in signals_list) / len(signals_list),
        immediate_energy_derivative=sum(s.immediate_energy_derivative for s in signals_list) / len(signals_list),
        bass_energy=sum(s.bass_energy for s in signals_list) / len(signals_list),
        mid_energy=sum(s.mid_energy for s in signals_list) / len(signals_list),
        high_energy=sum(s.high_energy for s in signals_list) / len(signals_list),
        brightness=sum(s.brightness for s in signals_list) / len(signals_list),
        spectral_centroid_hz=sum(s.spectral_centroid_hz or 1000 for s in signals_list) / len(signals_list),
        spectral_density_bass=sum(s.spectral_density_bass for s in signals_list) / len(signals_list),
        spectral_density_mid=sum(s.spectral_density_mid for s in signals_list) / len(signals_list),
        spectral_density_high=sum(s.spectral_density_high for s in signals_list) / len(signals_list),
        bass_energy_derivative=sum(s.bass_energy_derivative for s in signals_list) / len(signals_list),
        overall_energy_derivative=sum(s.overall_energy_derivative for s in signals_list) / len(signals_list),
        average_energy=sum(s.average_energy for s in signals_list) / len(signals_list),
        energy_variance=sum(s.energy_variance for s in signals_list) / len(signals_list),
        energy_trend=sum(s.energy_trend for s in signals_list) / len(signals_list),
        estimated_bpm=frames[0].signals.estimated_bpm,  # Use first frame's BPM
        beat_stability=sum(s.beat_stability for s in signals_list) / len(signals_list),
        beat_phase_0to1=sum(s.beat_phase_0to1 for s in signals_list) / len(signals_list),
        predicted_beat_timestamp_s=frames[0].signals.predicted_beat_timestamp_s,
        prediction_confidence=sum(s.prediction_confidence for s in signals_list) / len(signals_list),
    )
    
    # Combine all events
    all_events = []
    for frame in frames:
        all_events.extend(frame.events)
    
    return AudioFrame(
        timestamp_s=avg_timestamp,
        signals=merged_signals,
        events=all_events,
    )
