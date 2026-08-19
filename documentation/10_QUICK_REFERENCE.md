# Quick Reference

Fast lookup for common tasks and patterns.

## 10-Second Setup

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline

pipeline = AudioPipeline(LiveAudio()).start()

while True:
    frame = pipeline.get_frame()
    print(f"Bass: {frame.signals.bass_energy:.2f}")
```

## Common Imports

```python
# Audio sources
from src.sources import LiveAudio, LocalFileAudio

# Engine core
from src.engine import AudioPipeline, BeatPredictor

# Analyzers
from src.engine import FastAnalyzer, MediumAnalyzer, SlowAnalyzer

# Events and signals
from src.engine import EventType, AudioEvent, ContinuousSignals, AudioFrame
```

## Quick Lookups

### EventType Enum

| Constant | Value | Use |
|----------|-------|-----|
| `BEAT` | "beat" | Detected beat |
| `KICK` | "kick" | Bass transient |
| `SNARE` | "snare" | Mid/high transient |
| `CYMBAL` | "cymbal" | High transient |
| `ONSET` | "onset" | Any attack |
| `ENERGY_SPIKE` | "energy_spike" | Sudden loud |
| `ENERGY_DROP` | "energy_drop" | Sudden quiet |
| `BASS_SURGE` | "bass_surge" | Bass spike |
| `TREBLE_SURGE` | "treble_surge" | High spike |

### Common Signals (ContinuousSignals)

| Field | Range | Meaning |
|-------|-------|---------|
| `immediate_energy` | 0-1 | Current loudness |
| `bass_energy` | 0-1 | 20-250 Hz energy |
| `mid_energy` | 0-1 | 250-4k Hz energy |
| `high_energy` | 0-1 | 4k-20k Hz energy |
| `brightness` | 0-1 | Spectral centroid (normalized) |
| `average_energy` | 0-1 | Overall loudness |
| `energy_trend` | -1 to 1 | Building (+) or fading (-) |
| `estimated_bpm` | 50-200 | Detected tempo |
| `beat_phase_0to1` | 0-1 | Phase within beat (0=beat, 1=next beat) |

## Code Snippets

### Detect Kick

```python
for event in frame.events:
    if event.event_type == EventType.KICK:
        print(f"KICK! Strength: {event.strength}")
```

### Animate with Bass

```python
scale = 1.0 + frame.signals.bass_energy * 0.3
object.scale = lerp(object.scale, scale, 0.1)
```

### Get Beat Phase

```python
beat_phase, confidence = predictor.get_beat_phase(frame.timestamp_s)
if beat_phase is not None:
    pulse = cos(beat_phase * 3.14159)
    object.scale = 1.0 + pulse * 0.2
```

### Detect Onset

```python
if any(e.event_type == EventType.ONSET for e in frame.events):
    print("Attack detected")
```

### Track Brightness

```python
color_hue = frame.signals.brightness * 360
object.hue = color_hue
```

### Check Tempo Building

```python
if frame.signals.energy_trend > 0.3:
    scene.set_intensity("high")
```

## Common Patterns

### Pattern: Event Handler

```python
def on_audio_frame(frame):
    for event in frame.events:
        handler = {
            EventType.KICK: lambda e: screen.flash(),
            EventType.SNARE: lambda e: camera.shake(e.strength),
            EventType.BEAT: lambda e: light.pulse(e.confidence),
        }.get(event.event_type)
        
        if handler:
            handler(event)
```

### Pattern: Signal Animator

```python
def animate_with_audio(frame, dt):
    s = frame.signals
    
    obj.scale = 1.0 + s.bass_energy * 0.3
    obj.rotation = s.beat_phase_0to1 * 360
    obj.brightness = s.brightness
    obj.color.saturation = s.high_energy
```

### Pattern: Hybrid (Events + Signals)

```python
def react_to_audio(frame):
    # Immediate (event)
    if any(e.event_type == EventType.KICK for e in frame.events):
        particles.burst("kick")
    
    # Smooth (signals)
    base_scale = 1.0 + frame.signals.bass_energy * 0.3
    object.scale = lerp(object.scale, base_scale, 0.1)
```

### Pattern: Beat-Synced Loop

```python
def record_and_predict(frame, predictor):
    for event in frame.events:
        if event.event_type == EventType.BEAT:
            predictor.record_beat(event.timestamp_s, event.confidence)
    
    next_beat = predictor.predict_next_beat(frame.timestamp_s)
    if next_beat and (next_beat - frame.timestamp_s) < 0.05:
        effect.trigger()
```

## Troubleshooting

| Problem | Check |
|---------|-------|
| No audio data | `LiveAudio.list_devices()` |
| Choppy visuals | Use signals instead of events |
| High CPU | Reduce `num_processing_workers` |
| Beat unstable | Collect 4+ consistent beats |
| Latency high | Use Fast analyzer instead |
| Memory leak | Call `pipeline.stop()` |

## Performance Tips

| Goal | Solution |
|------|----------|
| **Lower latency** | Use `frame.events` (5-10ms) |
| **Smooth animation** | Use `frame.signals` (20-50ms) |
| **CPU efficient** | Shared buffer (88KB total) |
| **Stable metrics** | Use slow window (250ms) |
| **Event broadcast** | One event → many effects |
| **Signal sampling** | Sample once per frame |

## File Locations

```
src/
  engine/
    __init__.py           # Main exports
    events.py            # EventType, AudioEvent, ContinuousSignals, AudioFrame
    multi_window_analyzer.py
    pipeline.py
  sources/
    audio_source.py      # Base class
    live_audio.py        # LiveAudio
    track_audio.py       # LocalFileAudio

documentation/
  00_README.md           # Overview
  01_QUICK_START.md      # Getting started
  02_ARCHITECTURE.md     # System design
  03_EVENTS_VS_SIGNALS.md
  04_API_REFERENCE.md
  05_FEATURE_EXTRACTION.md
  06_TIERED_ANALYSIS.md
  07_BEAT_PREDICTION.md
  08_INTEGRATION_GUIDE.md
  09_EXAMPLES.md
  10_QUICK_REFERENCE.md  # This file
```

## Latency Summary

| Component | Latency | Use For |
|-----------|---------|---------|
| **Fast Analyzer** | 5-10ms | Kicks, onsets |
| **Medium Analyzer** | 20-50ms | Energy tracking |
| **Slow Analyzer** | 100-500ms | Metrics, tempo |
| **Beat Prediction** | -50ms | Zero-latency sync |

Negative latency = Ahead of audio (predicting next beat)

## Normalization Ranges

| Field | Min | Max | Meaning |
|-------|-----|-----|---------|
| Energy | 0.0 | 1.0 | Silence → Clipping |
| Confidence | 0.0 | 1.0 | Unsure → Certain |
| Strength | 0.0 | 1.0 | Subtle → Strong |
| Beat Phase | 0.0 | 1.0 | Beat → Next beat |
| BPM | 50 | 300 | Slow → Fast |
| Trend | -1.0 | 1.0 | Fading → Building |

## Thread Safety

Safe to call from any thread:
- `pipeline.get_frame()`
- `pipeline.is_running()`

Thread-safe data:
- `AudioFrame` and all contents

Don't share between threads:
- `AudioPipeline.start()` / `stop()` (call once)

## Common Conversions

### Phase to Time

```python
beat_interval_s = 60 / bpm  # e.g., 60/120 = 0.5s
time_into_beat = beat_phase * beat_interval_s  # e.g., 0.3 * 0.5 = 0.15s
```

### Energy to Scale

```python
scale = 1.0 + energy * 0.5  # 0-1 energy → 1.0-1.5x scale
```

### Beat Phase to Angle

```python
angle = beat_phase * 360  # 0-1 phase → 0-360°
angle_rad = beat_phase * 3.14159 * 2  # To radians
```

### BPM to Milliseconds

```python
beat_ms = (60 / bpm) * 1000  # e.g., 120 BPM = 500ms per beat
```

## Debugging Output

### Frame Summary

```python
def debug_frame(frame):
    print(f"Time: {frame.timestamp_s:.2f}s")
    print(f"Signals: {len(frame.events)} events")
    print(f"  Bass={frame.signals.bass_energy:.2f}")
    print(f"  Brightness={frame.signals.brightness:.2f}")
    print(f"  Phase={frame.signals.beat_phase_0to1:.2f}")
    for e in frame.events:
        print(f"  Event: {e.event_type.value} ({e.strength:.2f})")
```

### Pipeline Status

```python
print(f"Running: {pipeline.is_running()}")
print(f"Threads: {threading.active_count()}")

frame = pipeline.get_frame()
if frame:
    print(f"Latest: {frame.timestamp_s:.2f}s ago")
else:
    print("Waiting for first frame...")
```

## Quick Decisions

**Choose this...** | **If you need...**
---|---
Events | Immediate response (< 20ms)
Signals | Smooth animation (20-500ms)
Both | Responsive + smooth
Fast tier | Transient detection
Medium tier | Energy tracking
Slow tier | Stable metrics
Beat prediction | Zero-latency sync
OSC | External app integration

## See Also

- [01_QUICK_START.md](01_QUICK_START.md) - Getting started in 10 minutes
- [04_API_REFERENCE.md](04_API_REFERENCE.md) - Complete API documentation
- [08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md) - Framework integration
- [09_EXAMPLES.md](09_EXAMPLES.md) - Working code examples
