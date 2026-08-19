# Code Examples

Complete working examples for common use cases.

## Example 1: Basic Audio Visualization

Simple bar graph showing frequency bands:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline
import time

def main():
    # Setup
    source = LiveAudio(device_name="Stereo Mix")
    pipeline = AudioPipeline(source)
    pipeline.start()
    
    print("Listening to audio... Press Ctrl+C to stop\n")
    
    try:
        while True:
            frame = pipeline.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            
            # Get energy levels (0-1)
            bass = frame.signals.bass_energy
            mid = frame.signals.mid_energy
            high = frame.signals.high_energy
            
            # Draw bars
            bass_bar = "█" * int(bass * 40)
            mid_bar = "█" * int(mid * 40)
            high_bar = "█" * int(high * 40)
            
            print(f"\rBass [{bass_bar:<40}] {bass:.2f}")
            print(f"Mid  [{mid_bar:<40}] {mid:.2f}")
            print(f"High [{high_bar:<40}] {high:.2f}", end="\n\n")
            
            time.sleep(0.05)
    
    finally:
        pipeline.stop()

if __name__ == "__main__":
    main()
```

## Example 2: Beat Detection Event Logger

Log detected beats with timing:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline, EventType
import time

def main():
    source = LiveAudio()
    pipeline = AudioPipeline(source)
    pipeline.start()
    
    print("Detecting beats... (Press Ctrl+C to stop)\n")
    
    event_count = {e: 0 for e in EventType}
    
    try:
        while True:
            frame = pipeline.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            
            # Log all events
            for event in frame.events:
                event_count[event.event_type] += 1
                print(f"[{frame.timestamp_s:7.2f}s] {event.event_type.value.upper():15s} "
                      f"strength={event.strength:.2f} conf={event.confidence:.2f}")
            
            time.sleep(0.01)
    
    finally:
        pipeline.stop()
        
        print("\n\nEvent Summary:")
        for event_type, count in sorted(event_count.items(), key=lambda x: -x[1]):
            if count > 0:
                print(f"  {event_type.value:20s}: {count:4d} events")

if __name__ == "__main__":
    main()
```

## Example 3: Real-Time Waveform Monitor

Display current audio energy with trend:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline
import time
from collections import deque

def main():
    source = LiveAudio()
    pipeline = AudioPipeline(source)
    pipeline.start()
    
    # Circular buffer of last 60 values for trend
    energy_history = deque(maxlen=60)
    
    print("Energy Monitor (Press Ctrl+C to stop)\n")
    
    try:
        while True:
            frame = pipeline.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            
            # Get overall energy
            energy = frame.signals.average_energy
            energy_history.append(energy)
            
            # Draw sparkline
            sparkline_chars = "▁▂▃▄▅▆▇█"
            sparkline = "".join(
                sparkline_chars[min(int(e * 8), 7)]
                for e in energy_history
            )
            
            # Trend indicator
            if len(energy_history) > 10:
                recent_avg = sum(list(energy_history)[-10:]) / 10
                old_avg = sum(list(energy_history)[:-10]) / 50
                trend = (recent_avg - old_avg) * 100
                trend_str = f"↑{trend:+.1f}%" if trend > 0 else f"↓{trend:+.1f}%"
            else:
                trend_str = "→ (building...)"
            
            print(f"Energy: {energy:.3f} [{sparkline}] {trend_str}")
            
            time.sleep(0.05)
    
    finally:
        pipeline.stop()

if __name__ == "__main__":
    main()
```

## Example 4: Kick + Snare Detection

Separate kick and snare detection:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline, EventType
import time

class DrumDetector:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.kick_count = 0
        self.snare_count = 0
    
    def detect_from_frame(self, frame):
        for event in frame.events:
            if event.event_type == EventType.KICK:
                self.kick_count += 1
                self._on_kick(event)
            
            elif event.event_type == EventType.SNARE:
                self.snare_count += 1
                self._on_snare(event)
    
    def _on_kick(self, event):
        intensity = "HARD" if event.strength > 0.7 else "MEDIUM" if event.strength > 0.4 else "soft"
        print(f"🥁 KICK ({intensity}) - strength={event.strength:.2f}")
    
    def _on_snare(self, event):
        intensity = "CRISP" if event.strength > 0.7 else "MEDIUM" if event.strength > 0.4 else "soft"
        print(f"🔊 SNARE ({intensity}) - strength={event.strength:.2f}")

def main():
    source = LiveAudio()
    pipeline = AudioPipeline(source)
    pipeline.start()
    
    detector = DrumDetector(pipeline)
    
    print("Drum Detection (Press Ctrl+C to stop)\n")
    
    try:
        while True:
            frame = pipeline.get_frame()
            if frame:
                detector.detect_from_frame(frame)
            time.sleep(0.01)
    
    finally:
        pipeline.stop()
        print(f"\n\nDetected {detector.kick_count} kicks and {detector.snare_count} snares")

if __name__ == "__main__":
    main()
```

## Example 5: Beat Phase Visualization

Show beat phase with colored indicator:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline, BeatPredictor, EventType
import time
import math

def main():
    source = LiveAudio()
    pipeline = AudioPipeline(source)
    pipeline.start()
    
    predictor = BeatPredictor()
    
    print("Beat Phase Monitor (Record at least 4 beats first)\n")
    
    try:
        beat_count = 0
        
        while True:
            frame = pipeline.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            
            # Record beats
            for event in frame.events:
                if event.event_type == EventType.BEAT:
                    beat_count += 1
                    predictor.record_beat(event.timestamp_s, event.confidence)
            
            # Get phase
            beat_phase, confidence = predictor.get_beat_phase(frame.timestamp_s)
            
            if beat_phase is not None:
                # Visualize phase as circular progress
                position = int(beat_phase * 32)
                circle = ["◯"] * 32
                circle[position] = "◉"
                circle_str = "".join(circle)
                
                print(f"Beat #{beat_count:3d} | Phase: {circle_str} | "
                      f"Phase={beat_phase:.3f} | Conf={confidence:.2f}")
            else:
                print(f"Beat #{beat_count:3d} | Waiting for beat data...")
            
            time.sleep(0.05)
    
    finally:
        pipeline.stop()

if __name__ == "__main__":
    main()
```

## Example 6: Spectral Density Logger

Track color characteristics:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline
import time

def main():
    source = LiveAudio()
    pipeline = AudioPipeline(source)
    pipeline.start()
    
    print("Spectral Density Monitor\n")
    print("🔴 = Bass-heavy")
    print("🟢 = Balanced")
    print("🔵 = Bright\n")
    
    try:
        frame_count = 0
        
        while True:
            frame = pipeline.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            
            frame_count += 1
            
            if frame_count % 5 == 0:  # Log every 5th frame
                # Get spectral density
                total_energy = (frame.signals.bass_energy + 
                               frame.signals.mid_energy + 
                               frame.signals.high_energy)
                
                if total_energy > 0.01:
                    density_bass = frame.signals.spectral_density_bass
                    density_mid = frame.signals.spectral_density_mid
                    density_high = frame.signals.spectral_density_high
                    
                    # Color representation
                    if density_bass > 0.5:
                        color = "🔴"
                    elif density_high > 0.5:
                        color = "🔵"
                    else:
                        color = "🟢"
                    
                    print(f"{color} Bass={density_bass:.2f} Mid={density_mid:.2f} High={density_high:.2f} "
                          f"| Brightness={frame.signals.brightness:.2f}")
            
            time.sleep(0.01)
    
    finally:
        pipeline.stop()

if __name__ == "__main__":
    main()
```

## Example 7: Simple Game Loop

Minimal game with audio-reactive square:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline, EventType
import time
import math

class AudioGame:
    def __init__(self):
        self.source = LiveAudio()
        self.pipeline = AudioPipeline(self.source)
        self.pipeline.start()
        
        # Game state
        self.square_scale = 1.0
        self.square_rotation = 0.0
        self.screen_shake = 0.0
    
    def update(self):
        frame = self.pipeline.get_frame()
        if frame is None:
            return
        
        # Bass energy → scale
        target_scale = 1.0 + frame.signals.bass_energy * 0.5
        self.square_scale = self.square_scale * 0.9 + target_scale * 0.1
        
        # Beat phase → rotation
        rotation_speed = 360 * frame.signals.beat_phase_0to1
        self.square_rotation = rotation_speed
        
        # Kick event → screen shake
        for event in frame.events:
            if event.event_type == EventType.KICK:
                self.screen_shake = event.strength
        
        # Decay shake
        self.screen_shake *= 0.95
    
    def render(self):
        # Simple ASCII rendering
        size = int(5 + self.square_scale * 5)
        rotation_char = "◆" if self.square_rotation % 180 < 90 else "◇"
        
        print(f"\n{rotation_char} * {self.square_scale:.2f}x | Shake: {self.screen_shake:.2f}")
        print("█" * (size + int(self.screen_shake * 5)))
        print("█" * size)
    
    def run(self):
        try:
            frame_count = 0
            while True:
                self.update()
                
                if frame_count % 10 == 0:
                    self.render()
                
                frame_count += 1
                time.sleep(1/60)
        
        finally:
            self.pipeline.stop()

if __name__ == "__main__":
    game = AudioGame()
    game.run()
```

## Example 8: Audio File Analysis

Analyze pre-recorded audio:

```python
from src.sources import LocalFileAudio
from src.engine import AudioPipeline, EventType
import time

def analyze_audio_file(file_path):
    print(f"Analyzing {file_path}...\n")
    
    source = LocalFileAudio(file_path)
    pipeline = AudioPipeline(source)
    pipeline.start()
    
    # Collect statistics
    frame_count = 0
    max_energy = 0.0
    min_energy = 1.0
    avg_energy = 0.0
    event_counts = {}
    
    try:
        while True:
            frame = pipeline.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            
            frame_count += 1
            
            # Track energy
            energy = frame.signals.average_energy
            max_energy = max(max_energy, energy)
            min_energy = min(min_energy, energy)
            avg_energy = (avg_energy * (frame_count - 1) + energy) / frame_count
            
            # Count events
            for event in frame.events:
                key = event.event_type.value
                event_counts[key] = event_counts.get(key, 0) + 1
            
            # Print progress
            if frame_count % 100 == 0:
                print(f"Processed {frame.timestamp_s:.2f}s...")
    
    except (KeyboardInterrupt, StopIteration):
        pass
    
    finally:
        pipeline.stop()
    
    # Print results
    print(f"\nAnalysis Results:")
    print(f"Duration: {frame.timestamp_s:.2f}s")
    print(f"Frames: {frame_count}")
    print(f"Energy: min={min_energy:.3f}, avg={avg_energy:.3f}, max={max_energy:.3f}")
    print(f"Events: {sum(event_counts.values())} total")
    
    if event_counts:
        print("  Breakdown:")
        for event_type, count in sorted(event_counts.items(), key=lambda x: -x[1]):
            print(f"    {event_type:20s}: {count:4d}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python example.py <audio_file.wav>")
        sys.exit(1)
    
    analyze_audio_file(sys.argv[1])
```

## Example 9: Multi-Effect Reactor

Multiple effects triggered by different audio features:

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline, EventType
import time

class MultiEffectReactor:
    def __init__(self):
        self.pipeline = AudioPipeline(LiveAudio())
        self.pipeline.start()
        
        # Effect states
        self.effects = {
            "flash": {"active": False, "timer": 0},
            "shake": {"intensity": 0},
            "spin": {"speed": 0},
            "pulse": {"scale": 1.0},
        }
    
    def update(self, frame):
        # Flash on kick
        for event in frame.events:
            if event.event_type == EventType.KICK:
                self.effects["flash"]["active"] = True
                self.effects["flash"]["timer"] = 0.1
            elif event.event_type == EventType.SNARE:
                self.effects["shake"]["intensity"] = event.strength
        
        # Shake decays
        self.effects["shake"]["intensity"] *= 0.95
        
        # Flash decays
        if self.effects["flash"]["timer"] > 0:
            self.effects["flash"]["timer"] -= 0.016
        else:
            self.effects["flash"]["active"] = False
        
        # Spin with beat phase
        self.effects["spin"]["speed"] = frame.signals.beat_phase_0to1 * 360
        
        # Pulse with bass
        self.effects["pulse"]["scale"] = 1.0 + frame.signals.bass_energy * 0.3
    
    def render(self):
        status = []
        
        if self.effects["flash"]["active"]:
            status.append("⚡FLASH")
        
        if self.effects["shake"]["intensity"] > 0.1:
            status.append(f"📉SHAKE({self.effects['shake']['intensity']:.1f})")
        
        status.append(f"🌀SPIN({self.effects['spin']['speed']:.0f}°)")
        status.append(f"📈PULSE({self.effects['pulse']['scale']:.2f}x)")
        
        print(" | ".join(status))
    
    def run(self):
        try:
            frame_count = 0
            while True:
                frame = self.pipeline.get_frame()
                if frame:
                    self.update(frame)
                    
                    if frame_count % 5 == 0:
                        self.render()
                    
                    frame_count += 1
                
                time.sleep(0.01)
        
        finally:
            self.pipeline.stop()

if __name__ == "__main__":
    reactor = MultiEffectReactor()
    reactor.run()
```

## Running Examples

```bash
# Basic visualization
python examples/1_visualization.py

# Beat detection
python examples/2_beat_detection.py

# Waveform monitor
python examples/3_waveform_monitor.py

# Drum detection
python examples/4_drum_detection.py

# Beat phase
python examples/5_beat_phase.py

# Spectral tracking
python examples/6_spectral_density.py

# Simple game
python examples/7_simple_game.py

# Analyze audio file
python examples/8_audio_analysis.py music.wav

# Multi-effect
python examples/9_multi_effect.py
```

## Adapting Examples

All examples follow this pattern:

```python
1. Create audio source
2. Create pipeline
3. Start pipeline
4. Main loop:
   - Get frame
   - Process audio data
   - Render/output
5. Stop pipeline
```

Modify any step for your use case!

See [04_API_REFERENCE.md](04_API_REFERENCE.md) for complete API and [08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md) for GUI framework integration.
