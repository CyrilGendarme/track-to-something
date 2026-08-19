"""Example: Clean Separation of Events and Continuous Signals

This demonstrates the architectural pattern:
- EVENTS: Discrete point-in-time occurrences (beat, kick, snare, onset)
- SIGNALS: Smooth time-varying values (bass energy, brightness, etc.)

Different handling patterns for each type.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.engine import (
    MultiWindowAudioAnalyzer,
    EventType, AudioEvent, ContinuousSignals, AudioFrame,
    combine_features,
)
import numpy as np


class AudioReactiveGame:
    """Example game using events and continuous signals separately."""
    
    def __init__(self):
        self.analyzer = MultiWindowAudioAnalyzer(
            sample_rate=44100,
            fast_window_ms=10.0,
            medium_window_ms=32.0,
            slow_window_ms=250.0,
        )
        
        # Game state
        self.frame_count = 0
        self.events_this_frame = []
        self.current_signals = None
        
        # Game objects
        self.player_scale = 1.0
        self.player_brightness = 0.5
        self.animation_speed = 1.0
        self.score = 0
        self.particles = []
        self.screen_flashes = []
    
    def add_audio_chunk(self, audio: np.ndarray) -> None:
        """Feed audio to analyzer."""
        self.analyzer.add_audio_chunk(audio)
    
    def on_frame(self, timestamp_s: float) -> None:
        """Update game for one frame.
        
        This demonstrates the clean pattern:
        1. Get current frame from analyzer
        2. Handle events immediately (first-pass)
        3. Animate with continuous signals (smooth interpolation)
        """
        self.frame_count += 1
        
        # Get current analysis
        fast, medium, slow = self.analyzer.analyze_all(timestamp_s)
        render = combine_features(fast, medium, slow, beat_phase=0.5, 
                                  predicted_beat=timestamp_s + 0.5, prediction_confidence=0.8)
        
        # Convert to clean event/signal separation
        frame = self._create_frame(render, timestamp_s)
        self.current_signals = frame.signals
        self.events_this_frame = frame.events
        
        # STEP 1: Handle events (discrete, immediate)
        self._handle_events(frame.events)
        
        # STEP 2: Animate with signals (smooth, continuous)
        self._update_animation(frame.signals)
        
        # Log summary
        if self.frame_count % 60 == 0:
            self._log_frame(frame)
    
    def _create_frame(self, render, timestamp_s: float) -> AudioFrame:
        """Convert TieredRenderingMessage to clean Event/Signal separation."""
        
        # Build continuous signals
        signals = ContinuousSignals(
            timestamp_s=timestamp_s,
            immediate_energy=render.immediate_energy,
            immediate_energy_derivative=0.0,  # Would come from history
            bass_energy=render.bass_energy,
            mid_energy=render.mid_energy,
            high_energy=render.high_energy,
            brightness=render.brightness,
            spectral_centroid_hz=render.spectral_centroid_hz,
            spectral_density_bass=render.spectral_density_bass,
            spectral_density_mid=render.spectral_density_mid,
            spectral_density_high=render.spectral_density_high,
            bass_energy_derivative=render.bass_energy_change_per_sec,
            overall_energy_derivative=render.overall_energy_change_per_sec,
            average_energy=render.average_energy,
            energy_variance=render.energy_variance,
            energy_trend=render.energy_trend,
            estimated_bpm=render.estimated_bpm,
            beat_stability=render.beat_stability or 0.0,
            beat_phase_0to1=render.beat_phase_0to1,
            predicted_beat_timestamp_s=render.predicted_beat_timestamp_s,
            prediction_confidence=render.prediction_confidence,
        )
        
        # Build discrete events
        events = []
        
        if render.kick_detected:
            events.append(AudioEvent(
                EventType.KICK,
                timestamp_s=timestamp_s,
                strength=render.kick_strength,
                confidence=0.9,
                metadata={"tier": "very_fast"},
            ))
        
        if render.snare_detected:
            events.append(AudioEvent(
                EventType.SNARE,
                timestamp_s=timestamp_s,
                strength=render.snare_strength,
                confidence=0.9,
                metadata={"tier": "very_fast"},
            ))
        
        if render.transient_detected:
            events.append(AudioEvent(
                EventType.TRANSIENT,
                timestamp_s=timestamp_s,
                strength=render.transient_strength,
                confidence=0.8,
                metadata={"tier": "very_fast"},
            ))
        
        # Detect slow-tier events
        if render.average_energy > 0.7:
            events.append(AudioEvent(
                EventType.ENERGY_SPIKE,
                timestamp_s=timestamp_s,
                strength=render.average_energy,
                confidence=0.8,
                metadata={"tier": "slow"},
            ))
        
        return AudioFrame(timestamp_s=timestamp_s, signals=signals, events=events)
    
    def _handle_events(self, events: list[AudioEvent]) -> None:
        """PATTERN 1: Event-driven responses (immediate, low-latency).
        
        Each event triggers an immediate action.
        Events are discrete, so they fire once then go away.
        """
        for event in events:
            if event.event_type == EventType.KICK:
                self._on_kick(event)
            elif event.event_type == EventType.SNARE:
                self._on_snare(event)
            elif event.event_type == EventType.TRANSIENT:
                self._on_transient(event)
            elif event.event_type == EventType.ENERGY_SPIKE:
                self._on_energy_spike(event)
    
    def _on_kick(self, event: AudioEvent) -> None:
        """Handle kick detection event."""
        intensity = event.strength
        print(f"  [EVENT] KICK detected (strength={intensity:.2f})")
        
        # Immediate effects
        self.screen_flashes.append({
            'color': 'yellow',
            'duration': 0.1,
            'intensity': intensity,
        })
        
        # Particle burst
        self.particles.extend([
            f"kick_particle_{i}" for i in range(int(20 * intensity))
        ])
        
        # Score bonus
        self.score += int(100 * event.confidence)
    
    def _on_snare(self, event: AudioEvent) -> None:
        """Handle snare detection event."""
        intensity = event.strength
        print(f"  [EVENT] SNARE detected (strength={intensity:.2f})")
        
        # Immediate effects
        self.screen_flashes.append({
            'color': 'cyan',
            'duration': 0.08,
            'intensity': intensity * 0.7,
        })
        
        # Camera shake
        print(f"  [FX] Camera shake (intensity={intensity:.2f})")
        
        self.score += int(50 * event.confidence)
    
    def _on_transient(self, event: AudioEvent) -> None:
        """Handle generic transient event."""
        if event.strength > 0.6:
            print(f"  [EVENT] TRANSIENT detected (strength={event.strength:.2f})")
    
    def _on_energy_spike(self, event: AudioEvent) -> None:
        """Handle energy spike event (scene change)."""
        print(f"  [EVENT] ENERGY SPIKE (strength={event.strength:.2f})")
        print(f"  [SCENE] Shifting to high-energy aesthetic")
    
    def _update_animation(self, signals: ContinuousSignals) -> None:
        """PATTERN 2: Animation-driven updates (smooth, continuous).
        
        Continuous signals are sampled every frame and interpolated.
        They vary smoothly, so animation should be smooth too.
        """
        dt = 1.0 / 60.0  # Assume 60 FPS
        smooth_factor = 0.15  # Lerp smoothing
        
        # 1. Bass energy -> player scale
        target_scale = 1.0 + signals.bass_energy * 0.4
        self.player_scale = self._lerp(self.player_scale, target_scale, smooth_factor)
        
        # 2. Brightness -> player color
        target_brightness = signals.brightness
        self.player_brightness = self._lerp(self.player_brightness, target_brightness, smooth_factor)
        
        # 3. Energy trend -> animation speed
        # Building (trend > 0): speed up
        # Fading (trend < 0): slow down
        target_speed = 0.7 + (signals.energy_trend + 1.0) * 0.3  # 0.4 to 1.0
        self.animation_speed = self._lerp(self.animation_speed, target_speed, smooth_factor)
    
    def _lerp(self, current: float, target: float, factor: float) -> float:
        """Simple linear interpolation."""
        return current * (1.0 - factor) + target * factor
    
    def _log_frame(self, frame: AudioFrame) -> None:
        """Log current frame state."""
        print(f"\n[Frame {self.frame_count}] @ {frame.timestamp_s:.2f}s")
        print(f"  Events this frame: {len(frame.events)}")
        
        for event in frame.events:
            print(f"    - {event}")
        
        print(f"  Continuous signals:")
        print(f"    - Immediate: {frame.signals.immediate_energy:.2f}")
        print(f"    - Bass: {frame.signals.bass_energy:.2f}")
        print(f"    - Brightness: {frame.signals.brightness:.2f}")
        print(f"    - Trend: {frame.signals.energy_trend:+.2f}")
        print(f"    - BPM: {frame.signals.estimated_bpm or 'N/A'}")
        
        print(f"  Game state:")
        print(f"    - Scale: {self.player_scale:.2f}")
        print(f"    - Brightness: {self.player_brightness:.2f}")
        print(f"    - Speed: {self.animation_speed:.2f}")
        print(f"    - Score: {self.score}")


def main():
    """Run the example."""
    print("=" * 80)
    print("EVENTS vs CONTINUOUS SIGNALS - PRACTICAL EXAMPLE")
    print("=" * 80)
    print()
    print("This demonstrates the clean separation pattern:")
    print("  - EVENTS: Discrete point-in-time occurrences (kick, snare, beat, onset)")
    print("  - SIGNALS: Smooth time-varying values (bass, brightness, energy, etc.)")
    print()
    print("Different handlers for each:")
    print("  - Events: Trigger callbacks immediately")
    print("  - Signals: Interpolate smoothly for animation")
    print()
    print("=" * 80)
    print()
    
    game = AudioReactiveGame()
    
    # Simulate different musical moments
    scenarios = [
        ("Quiet intro", 0.1, 0.0, 0.0, -0.5),
        ("Bass drop (KICK!)", 0.95, 0.0, 0.0, 0.8),
        ("Snare/hi-hat", 0.2, 0.0, 0.9, 0.0),
        ("Busy section", 0.6, 0.6, 0.6, 0.2),
        ("Building to chorus", 0.7, 0.7, 0.5, 0.4),
    ]
    
    timestamp_s = 0.0
    dt = 1.0 / 21  # 21 fps in demo (one frame per ~47ms)
    
    for scenario_name, bass, mid, high, trend in scenarios * 2:
        print(f"\n{'=' * 80}")
        print(f"Scenario: {scenario_name}")
        print(f"{'=' * 80}")
        
        # Generate test audio
        duration_samples = 1024
        audio = np.zeros((duration_samples, 2), dtype=np.float32)
        t = np.linspace(0, duration_samples / 44100, duration_samples)
        
        if bass > 0:
            audio[:, 0] += np.sin(2 * np.pi * 100 * t) * bass
        if mid > 0:
            audio[:, 0] += np.sin(2 * np.pi * 1000 * t) * mid
        if high > 0:
            audio[:, 0] += np.sin(2 * np.pi * 8000 * t) * high
        
        audio[:, 1] = audio[:, 0]
        
        # Process frames
        for frame_in_scenario in range(3):
            game.add_audio_chunk(audio)
            game.on_frame(timestamp_s)
            timestamp_s += dt
    
    print("\n" + "=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()
    print("Key insights:")
    print("  1. Events are handled immediately (first-pass)")
    print("  2. Signals are sampled and interpolated (smooth)")
    print("  3. This enables both responsive AND smooth effects")
    print("  4. Clear separation makes code easier to understand and debug")
    print()
    print("Consumer patterns enabled by this separation:")
    print("  1. Event listeners (callbacks for discrete events)")
    print("  2. Signal animation (interpolation and easing)")
    print("  3. Hybrid (both events and signals in same update)")
    print("  4. Event broadcasting (one kick triggers many effects)")
    print("  5. Signal sampling (per-object, per-frame)")
    print()
    print("This architecture scales from:")
    print("  - Single-threaded indie games")
    print("  - Multi-threaded game engines (Unity, Unreal)")
    print("  - OSC/network streaming to other apps")
    print("  - Shader effects and GPU processing")
    print()


if __name__ == "__main__":
    main()
