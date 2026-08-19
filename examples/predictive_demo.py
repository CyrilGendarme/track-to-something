"""Predictive Beat Synchronization - Live Example

Demonstrates the difference between reactive and predictive beat animations.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.engine import BeatPredictor
from dataclasses import dataclass
import time


@dataclass
class AnimationTimeline:
    """Track animation timings to show prediction advantage."""
    name: str
    trigger_time: float
    beat_time: float
    
    @property
    def latency_ms(self) -> float:
        """Latency relative to beat (negative = early, positive = late)."""
        return (self.trigger_time - self.beat_time) * 1000.0


def demonstrate_reactive_vs_predictive():
    """Compare reactive and predictive animation timing."""
    
    print("=" * 90)
    print("PREDICTIVE BEAT SYNC - REACTIVE vs PREDICTIVE COMPARISON")
    print("=" * 90)
    print()
    
    # Simulate music at 120 BPM (0.5 second beats)
    beat_interval = 0.5  # seconds
    beats = [i * beat_interval for i in range(8)]  # 8 beats
    
    print(f"Music: 120 BPM ({beat_interval}s per beat)")
    print(f"Beats occur at: {[f'{b:.1f}s' for b in beats]}")
    print()
    
    # Simulate detection latency (100ms typical)
    detection_latency = 0.1  # seconds
    
    print(f"Audio Processing Latency: {detection_latency*1000:.0f}ms")
    print("(capture + STFT + beat detection)")
    print()
    
    # Create predictor
    predictor = BeatPredictor(max_history=5)
    
    # Feed beats to predictor (simulating real-time analysis)
    print("Recording beat detections...")
    for beat_time in beats[:5]:  # First 5 beats
        detected_time = beat_time + detection_latency
        predictor.record_beat(detected_time)
        print(f"  Beat at {beat_time:.1f}s → Detected at {detected_time:.1f}s")
    
    print()
    
    # Now compare: animate the next two beats reactively vs predictively
    timelines = {
        "Reactive": [],
        "Predictive": [],
    }
    
    for beat_num, beat_time in enumerate(beats[5:7], start=6):
        detected_time = beat_time + detection_latency
        predictor.record_beat(detected_time)
        
        print(f"\n{'─' * 90}")
        print(f"BEAT #{beat_num} - Actual beat occurs at {beat_time:.2f}s")
        print(f"{'─' * 90}")
        
        # --- REACTIVE APPROACH ---
        # Animation triggers when we detect the beat (after latency)
        reactive_trigger = detected_time
        reactive_latency = reactive_trigger - beat_time
        
        print(f"\n1. REACTIVE APPROACH:")
        print(f"   └─ Detect beat at {detected_time:.2f}s")
        print(f"   └─ Trigger animation at {reactive_trigger:.2f}s")
        print(f"   └─ LATENCY: {reactive_latency*1000:+.0f}ms ({reactive_latency*60:.1f} frames @ 60fps)")
        print(f"   └─ FEELS: Late, sluggish, out of sync ❌")
        
        timelines["Reactive"].append(AnimationTimeline(
            f"Reactive Beat {beat_num}",
            reactive_trigger,
            beat_time
        ))
        
        # --- PREDICTIVE APPROACH ---
        # Animation triggers when phase reaches 0.85 (150ms before next beat)
        predicted_next, confidence = predictor.predict_next_beat(detected_time)
        
        if predicted_next is not None:
            # Pre-animate when phase reaches 0.85 (15% before beat)
            animation_trigger_phase = 0.85
            time_to_next_beat = predicted_next - detected_time
            predictive_trigger = detected_time + (time_to_next_beat * animation_trigger_phase)
            predictive_latency = predictive_trigger - beat_time
            
            print(f"\n2. PREDICTIVE APPROACH:")
            print(f"   ├─ Detect beat at {detected_time:.2f}s")
            print(f"   ├─ Predict next beat at {predicted_next:.2f}s (confidence {confidence:.2f})")
            print(f"   ├─ Calculate beat phase = {animation_trigger_phase:.2f} ({animation_trigger_phase*100:.0f}% through cycle)")
            print(f"   ├─ Trigger animation at {predictive_trigger:.2f}s (EARLY!)")
            print(f"   └─ LATENCY: {predictive_latency*1000:+.0f}ms ({predictive_latency*60:.1f} frames @ 60fps)")
            
            if predictive_latency < 0:
                print(f"   └─ FEELS: Tight, responsive, IN SYNC! ✓✓✓")
            else:
                print(f"   └─ FEELS: Still late, but better than reactive")
            
            timelines["Predictive"].append(AnimationTimeline(
                f"Predictive Beat {beat_num}",
                predictive_trigger,
                beat_time
            ))
        else:
            print(f"\n2. PREDICTIVE APPROACH: Not enough data yet")
    
    # Summary comparison
    print(f"\n{'=' * 90}")
    print("TIMING COMPARISON")
    print(f"{'=' * 90}")
    print()
    
    print(f"{'Method':<15} {'Beat':<15} {'Trigger Time':<15} {'vs Beat Time':<20}")
    print("-" * 70)
    
    for method in ["Reactive", "Predictive"]:
        for timeline in timelines[method]:
            latency_str = f"{timeline.latency_ms:+.0f}ms"
            frames_str = f"({timeline.latency_ms/16.67:+.1f} frames)"
            print(f"{method:<15} {timeline.name:<15} {timeline.trigger_time:.3f}s       "
                  f"{latency_str:<12} {frames_str}")
    
    print()
    
    # Calculate average latencies
    if timelines["Reactive"]:
        avg_reactive = sum(t.latency_ms for t in timelines["Reactive"]) / len(timelines["Reactive"])
        print(f"Average Reactive Latency:   {avg_reactive:+.0f}ms ({avg_reactive/16.67:+.1f} frames)")
    
    if timelines["Predictive"]:
        avg_predictive = sum(t.latency_ms for t in timelines["Predictive"]) / len(timelines["Predictive"])
        print(f"Average Predictive Latency: {avg_predictive:+.0f}ms ({avg_predictive/16.67:+.1f} frames)")
    
    print()
    print("=" * 90)
    print("KEY INSIGHT")
    print("=" * 90)
    print("""
Reactive detects beat AFTER it happens → animation plays late.
Predictive estimates next beat → animation plays early, in sync.

At 60 FPS, just 1-2 frame difference feels like the difference between:
  - "Sluggish" (reactive, 100ms late)
  - "Tight" (predictive, 0ms, in sync)

For rhythm games and sync-critical visualization, this matters a LOT!
""")


def demonstrate_tempo_stability_effect():
    """Show how tempo stability affects prediction confidence."""
    
    print("\n" + "=" * 90)
    print("TEMPO STABILITY & PREDICTION CONFIDENCE")
    print("=" * 90)
    print()
    
    scenarios = {
        "Perfect Tempo (Electronic)": [0.500, 0.500, 0.500, 0.500, 0.500],
        "Stable Tempo (Live Band)": [0.500, 0.502, 0.498, 0.501, 0.499],
        "Drifting Tempo (Breathing)": [0.500, 0.510, 0.520, 0.530, 0.540],
        "Chaotic Tempo (Free Jazz)": [0.500, 0.520, 0.470, 0.550, 0.460],
    }
    
    for scenario_name, intervals in scenarios.items():
        print(f"\n{scenario_name}")
        print("-" * 90)
        
        predictor = BeatPredictor(max_history=5)
        
        current_time = 0.0
        for i, interval in enumerate(intervals):
            current_time += interval
            predictor.record_beat(current_time)
            
            if i >= 2:  # Need at least 3 beats to predict
                _, confidence = predictor.predict_next_beat(current_time)
                bpm = predictor.get_estimated_bpm()
                
                confidence_bar = "█" * int(confidence * 20) + "░" * (20 - int(confidence * 20))
                status = "✓ Safe to animate early" if confidence > 0.8 else "⚠ Be conservative" if confidence > 0.6 else "✗ Use reactive only"
                
                print(f"  After beat {i+1}: BPM={bpm:.1f} | Confidence [{confidence_bar}] {confidence:.2f} {status}")
        
        print()


def demonstrate_beat_phase_visualization():
    """Show what beat_phase_0to1 looks like over time."""
    
    print("\n" + "=" * 90)
    print("BEAT PHASE VISUALIZATION (0 to 1 per cycle)")
    print("=" * 90)
    print()
    
    predictor = BeatPredictor(max_history=3)
    beat_interval = 0.5  # 120 BPM
    
    # Prime with some beats
    for i in range(3):
        predictor.record_beat(i * beat_interval)
    
    print("Music at 120 BPM (0.5s per beat)")
    print()
    print("Time   | Beat# | Phase [  visual bar  ] | Status")
    print("─" * 70)
    
    for time_ms in range(0, 1500, 100):  # 0-1500ms
        current_time = time_ms / 1000.0
        
        # Determine which beat we're in
        beat_num = current_time / beat_interval
        phase = predictor.get_beat_phase(current_time)
        
        bar_pos = int(phase * 18)
        bar = " " * bar_pos + "●" + " " * (18 - bar_pos)
        
        if phase < 0.05:
            status = "BEAT! ♪"
        elif phase < 0.2:
            status = "Just after beat"
        elif phase < 0.8:
            status = "Midway"
        elif phase < 0.95:
            status = "Approaching next beat"
        else:
            status = "Very close! (animate now?)"
        
        print(f"{time_ms:>4}ms | {beat_num:>5.2f} | [{bar}] {phase:.2f} | {status}")
    
    print()
    print("At 60 FPS, animation should trigger around phase=0.85")
    print("That's approximately 75ms before the next beat")
    print()


if __name__ == "__main__":
    demonstrate_reactive_vs_predictive()
    demonstrate_tempo_stability_effect()
    demonstrate_beat_phase_visualization()
    
    print("\n" + "=" * 90)
    print("CONCLUSION: Use beat_phase and prediction_confidence for tight sync!")
    print("=" * 90 + "\n")
