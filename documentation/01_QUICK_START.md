# Quick Start Guide

Get the audio analysis engine running in 10 minutes.

## Prerequisites

- Python 3.13+
- pip
- Windows 10/11 with audio input (loopback audio or USB device)

## Installation

### 1. Clone and Install
```bash
cd moshpro-spout-obs-glue-script
pip install -r requirements.txt
```

### 2. Setup Audio Source

#### Option A: Loopback Audio (Stereo Mix)
**Windows:**
1. Right-click Speaker → Sound settings
2. Advanced → App volume and device preferences
3. Find stereo mix in recording devices
4. Enable if disabled
5. Set as default recording device

#### Option B: USB Audio Device
Just plug in your USB audio interface - it's automatically detected.

#### Option C: File Playback
Use any WAV file on disk.

## Your First Program (10 lines)

```python
from src.engine import AudioPipeline
from src.sources import LocalFileAudio

# Create pipeline
pipeline = AudioPipeline(audio_source=LocalFileAudio("song.wav"))
pipeline.start()

# Process frames
for _ in range(100):
    frame = pipeline.get_frame()
    if frame:
        print(f"Bass: {frame.signals.bass_energy:.2f}")

pipeline.stop()
```

## Common Patterns

### Pattern 1: Respond to Events

```python
from src.engine import AudioPipeline, EventType
from src.sources import LocalFileAudio

pipeline = AudioPipeline(audio_source=LocalFileAudio("song.wav"))
pipeline.start()

while pipeline.is_running():
    frame = pipeline.get_frame()
    if not frame:
        continue
    
    # Handle events
    for event in frame.events:
        if event.event_type == EventType.KICK:
            print(f"KICK! (strength={event.strength:.2f})")
        elif event.event_type == EventType.SNARE:
            print(f"SNARE! (strength={event.strength:.2f})")
        elif event.event_type == EventType.BEAT:
            print(f"BEAT (confidence={event.confidence:.2f})")

pipeline.stop()
```

### Pattern 2: Animate with Signals

```python
from src.engine import AudioPipeline
from src.sources import LocalFileAudio

pipeline = AudioPipeline(audio_source=LocalFileAudio("song.wav"))
pipeline.start()

# Object state
scale = 1.0
brightness = 0.5

while pipeline.is_running():
    frame = pipeline.get_frame()
    if not frame:
        continue
    
    # Smooth interpolation
    target_scale = 1.0 + frame.signals.bass_energy * 0.5
    scale = scale * 0.85 + target_scale * 0.15  # Lerp with factor 0.15
    
    target_brightness = frame.signals.brightness
    brightness = brightness * 0.9 + target_brightness * 0.1
    
    print(f"Scale: {scale:.2f}, Brightness: {brightness:.2f}")

pipeline.stop()
```

### Pattern 3: Hybrid (Events + Signals)

```python
from src.engine import AudioPipeline, EventType
from src.sources import LocalFileAudio

pipeline = AudioPipeline(audio_source=LocalFileAudio("song.wav"))
pipeline.start()

while pipeline.is_running():
    frame = pipeline.get_frame()
    if not frame:
        continue
    
    # Immediate response to events
    for event in frame.events:
        if event.event_type == EventType.KICK:
            print("FLASH!")
    
    # Smooth animation with signals
    bass_scale = 1.0 + frame.signals.bass_energy * 0.3
    brightness = frame.signals.brightness
    
    print(f"Bass scale: {bass_scale:.2f}, Brightness: {brightness:.2f}")

pipeline.stop()
```

### Pattern 4: Predictive Beat Sync

```python
from src.engine import AudioPipeline
from src.sources import LocalFileAudio

pipeline = AudioPipeline(audio_source=LocalFileAudio("song.wav"))
pipeline.start()

while pipeline.is_running():
    frame = pipeline.get_frame()
    if not frame:
        continue
    
    # How far away is the next beat?
    time_until_beat = frame.signals.predicted_beat_timestamp_s - frame.timestamp_s
    
    if 0 < time_until_beat < 0.05:  # 50ms before beat
        print(f"BEAT ARRIVING IN {time_until_beat*1000:.1f}ms!")
    
    # Use this to trigger effects 50ms early
    # Eliminates 100-150ms reactive latency
    print(f"Beat phase: {frame.signals.beat_phase_0to1:.2f}")

pipeline.stop()
```

## Understanding the Output

### AudioFrame Structure

Every frame contains:
- `timestamp_s`: Current time in seconds
- `signals`: Smooth continuous values
- `events`: Discrete occurrences this frame

### ContinuousSignals (25 fields)

Organized by latency tier:

**Tier 1 (5-10ms latency):**
```python
frame.signals.immediate_energy           # 0-1 current amplitude
frame.signals.immediate_energy_derivative # change/sec
```

**Tier 2 (20-50ms latency):**
```python
frame.signals.bass_energy                # 0-1 (20-250 Hz)
frame.signals.mid_energy                 # 0-1 (250-4k Hz)
frame.signals.high_energy                # 0-1 (4k-20k Hz)
frame.signals.brightness                 # 0-1 (spectral centroid)
frame.signals.spectral_density_bass      # 0-1 (proportion)
frame.signals.spectral_density_mid       # 0-1
frame.signals.spectral_density_high      # 0-1
```

**Tier 3 (100-500ms latency):**
```python
frame.signals.average_energy             # 0-1 typical loudness
frame.signals.energy_variance            # 0-1 how dynamic
frame.signals.energy_trend               # -1 to 1 (building vs fading)
frame.signals.estimated_bpm              # Hz (or None)
frame.signals.beat_stability             # 0-1 tempo consistency
```

**Beat Prediction (all tiers):**
```python
frame.signals.beat_phase_0to1            # 0=beat, 1=next beat
frame.signals.predicted_beat_timestamp_s # When next beat arrives
frame.signals.prediction_confidence      # 0-1
```

### AudioEvent Types (14 types)

```python
EventType.BEAT              # Detected beat
EventType.KICK              # Bass transient
EventType.SNARE             # Mid/high transient
EventType.CYMBAL            # High transient
EventType.PERCUSSION        # Generic percussion
EventType.ONSET             # Any rapid energy rise
EventType.TRANSIENT         # Rapid attack
EventType.ENERGY_SPIKE      # Sudden energy increase
EventType.ENERGY_DROP       # Sudden energy decrease
EventType.SILENCE_STARTED   # Energy below threshold
EventType.SILENCE_ENDED     # Energy above threshold
EventType.BASS_SURGE        # Bass energy spike
EventType.TREBLE_SURGE      # Treble energy spike
```

## Using Different Audio Sources

### Loopback Audio
```python
from src.sources import LiveAudio
from src.engine import AudioPipeline

# Auto-detect Stereo Mix
pipeline = AudioPipeline(audio_source=LiveAudio())
```

### USB Audio Device
```python
from src.sources import LiveAudio
from src.engine import AudioPipeline

# Auto-detect USB device
pipeline = AudioPipeline(audio_source=LiveAudio(device_name="USB"))
```

### File Playback
```python
from src.sources import LocalFileAudio
from src.engine import AudioPipeline

pipeline = AudioPipeline(audio_source=LocalFileAudio("song.wav"))
```

## Adjusting for Your Use Case

### For Responsive Effects (Low Latency)
Use **Tier 1 events** + **Tier 2 signals**:
```python
for event in frame.events:
    # These have 5-10ms latency
    if event.event_type == EventType.KICK:
        trigger_effect()

# These have 20-50ms latency
scale = 1.0 + frame.signals.bass_energy * 0.3
```

### For Smooth Animation (Interpolated)
Use **Tier 2 and 3 signals**:
```python
# Tier 2: 20-50ms, responsive
bass_scale = 1.0 + frame.signals.bass_energy * 0.3

# Tier 3: 100-500ms, smooth
overall_brightness = frame.signals.average_energy
```

### For Predictive Rhythm Sync (Zero Latency)
Use **beat prediction**:
```python
time_until = frame.signals.predicted_beat_timestamp_s - frame.timestamp_s
if 0 < time_until < 0.05:
    prepare_effect()  # Will sync exactly at beat
```

## Troubleshooting

### No events detected
- Make sure Stereo Mix is enabled (for loopback audio)
- Check that audio is actually playing
- Volume might be too low - ensure audio source is loud enough

### Audio processing is slow
- Reduce frame rate in integration code
- Run with fewer processing workers
- Profile with `time.time()` to find bottleneck

### Pipeline doesn't start
- Check that audio source is available
- Verify audio device is properly configured
- Try with a file source first

### Inaccurate beat detection
- Different music styles require tuning
- Try adjusting confidence thresholds in analysis
- Use beat prediction instead of reactive detection

## Next Steps

- Read [02_ARCHITECTURE.md](02_ARCHITECTURE.md) to understand the design
- Explore [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for more patterns
- Check [EXAMPLES.md](EXAMPLES.md) for real-world use cases
- See [08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md) for game/app integration

## Performance Tips

1. **Don't process every frame** - Add frame skipping if CPU is high
2. **Use appropriate tiers** - Fast tier for immediate, Slow tier for smooth
3. **Batch events** - Collect events over multiple frames if possible
4. **Cache calculations** - Don't recalculate values each frame

See [02_ARCHITECTURE.md](02_ARCHITECTURE.md) for performance benchmarks.
