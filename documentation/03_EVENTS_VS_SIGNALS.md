# Events vs Continuous Signals

Clean architectural separation of discrete audio events from continuous signal values.

## Core Concept

Audio analysis produces **two fundamentally different types** of data:

### Events (Discrete)
- **Point-in-time** occurrences at specific timestamps
- **No duration** (or instantaneous duration)
- **Trigger immediate** actions (flash screen, play sound)
- **Sparse** delivery (10-50 per second)
- **Examples**: Beat detected, kick detected, snare, onset

### Continuous Signals (Smooth)
- **Time-varying** numeric values (0-1 normalized)
- **Change smoothly** from one value to next
- **Drive animations** and parameter modulation
- **Dense** delivery (60-120 per second, every frame)
- **Examples**: Bass energy 0.72, brightness 0.84

## Why Separate?

### The Problem with Mixed Data

```python
# BAD: Events and signals mixed together
render_message = {
    "timestamp_s": 10.5,
    "kick_detected": True,           # <-- EVENT
    "bass_energy": 0.85,             # <-- SIGNAL
    "snare_detected": False,         # <-- EVENT
    "brightness": 0.72,              # <-- SIGNAL
    "beat_phase": 0.45,              # <-- SIGNAL
}

# Unclear consumption:
# - Is kick_detected still true 20ms from now?
# - Should I sample bass_energy every frame or only when kick_detected?
# - Does beat_phase interpolate smoothly or step?
```

### The Benefits of Separation

```python
# GOOD: Clear distinction

# Discrete events (point-in-time)
events = [
    AudioEvent(EventType.KICK, timestamp_s=10.5, strength=0.9, confidence=0.95),
    AudioEvent(EventType.ONSET, timestamp_s=10.52, strength=0.6, confidence=0.85),
]

# Continuous signals (smooth, always available)
signals = ContinuousSignals(
    timestamp_s=10.5,
    bass_energy=0.85,           # Sample every frame
    brightness=0.72,            # Interpolate smoothly
    beat_phase=0.45,            # Continuous 0-1 value
)

# Now it's crystal clear:
for event in events:
    if event.event_type == EventType.KICK:
        screen.flash(intensity=event.strength)  # Immediate

object.scale = 1.0 + signals.bass_energy * 0.5  # Smooth animation
```

## Event Types (14 Total)

### Temporal Events (Rhythm/Beat)
```python
EventType.BEAT              # Detected beat
EventType.KICK              # Bass transient (kick drum)
EventType.SNARE             # Mid/high transient (snare, clap)
EventType.CYMBAL            # High transient (cymbal, shaker)
EventType.PERCUSSION        # Generic percussion hit
```

### Transient Events (Attack Detection)
```python
EventType.ONSET             # Any rapid energy rise (attack)
EventType.TRANSIENT         # Generic rapid attack
EventType.ENERGY_SPIKE      # Sudden increase in overall energy
EventType.ENERGY_DROP       # Sudden decrease in overall energy
```

### State Change Events
```python
EventType.SILENCE_STARTED   # Energy dropped below threshold
EventType.SILENCE_ENDED     # Energy rose above threshold
```

### Spectral Events
```python
EventType.BASS_SURGE        # Bass energy spike
EventType.TREBLE_SURGE      # High frequency energy spike
```

## AudioEvent Structure

```python
@dataclass
class AudioEvent:
    event_type: EventType          # Type of event
    timestamp_s: float             # When it occurred
    strength: float                # How strong (0-1)
    confidence: float              # How confident (0-1)
    metadata: dict = {}            # Type-specific data
```

### Example Events

```python
# Kick drum
kick = AudioEvent(
    EventType.KICK,
    timestamp_s=10.5,
    strength=0.9,           # Very strong
    confidence=0.95,        # Very confident
    metadata={"detected_hz": 120, "attack_ms": 10},
)

# Onset
onset = AudioEvent(
    EventType.ONSET,
    timestamp_s=10.52,
    strength=0.6,
    confidence=0.85,
)

# Beat
beat = AudioEvent(
    EventType.BEAT,
    timestamp_s=11.0,
    strength=1.0,
    confidence=0.92,        # BPM stability
    metadata={"bpm": 128},
)

print(kick)  # [10.50s] KICK (strength=0.90, conf=0.95)
```

## Continuous Signals (25 Fields)

Organized by latency tier:

### Tier 1: Very Fast (5-10ms latency)
```python
signals.immediate_energy             # 0-1 (current amplitude)
signals.immediate_energy_derivative  # change/sec
```

### Tier 2: Medium (20-50ms latency)
```python
# Frequency bands
signals.bass_energy                  # 0-1 (20-250 Hz)
signals.mid_energy                   # 0-1 (250-4k Hz)
signals.high_energy                  # 0-1 (4k-20k Hz)

# Spectral characteristics
signals.brightness                   # 0-1 (spectral centroid)
signals.spectral_centroid_hz         # Hz
signals.spectral_density_bass        # 0-1 (proportion)
signals.spectral_density_mid         # 0-1
signals.spectral_density_high        # 0-1

# Energy rates (for smooth animation)
signals.bass_energy_derivative       # change/sec
signals.overall_energy_derivative    # change/sec
```

### Tier 3: Slow (100-500ms latency)
```python
# Sustained metrics
signals.average_energy               # 0-1 (typical loudness)
signals.energy_variance              # 0-1 (how dynamic)
signals.energy_trend                 # -1 to 1 (building vs fading)

# Tempo/rhythm
signals.estimated_bpm                # Hz (or None)
signals.beat_stability               # 0-1 (tempo consistency)
```

### Beat Prediction (all tiers)
```python
signals.beat_phase_0to1              # 0=beat, 1=next beat
signals.predicted_beat_timestamp_s   # When next beat arrives
signals.prediction_confidence        # 0-1
```

## AudioFrame: Container for Both

Combines events and signals at same timestamp:

```python
@dataclass
class AudioFrame:
    timestamp_s: float
    signals: ContinuousSignals
    events: list[AudioEvent]
```

### Usage

```python
frame = AudioFrame(
    timestamp_s=10.5,
    signals=continuous_signals,
    events=[kick, onset],  # Multiple events per frame
)

# Access
print(frame.signals.bass_energy)      # 0.85
print(frame.events[0].event_type)     # EventType.KICK
```

## Consumer Patterns

### Pattern 1: Event-Driven (Immediate Response)
Handle events immediately with callbacks.

```python
for event in frame.events:
    if event.event_type == EventType.KICK:
        screen.flash(brightness=1.0, duration=0.1)
    elif event.event_type == EventType.SNARE:
        camera.shake(intensity=event.strength)
    elif event.event_type == EventType.ONSET:
        if event.strength > 0.6:
            light_strobe.trigger(intensity=event.strength)
```

**Latency**: 5-10ms  
**Density**: Sparse (10-50 events/sec)  
**Best for**: Responsive effects, immediate feedback

### Pattern 2: Animation-Driven (Smooth Interpolation)
Sample and interpolate signals for smooth animation.

```python
def update_animation(frame, dt):
    smooth_factor = 0.15
    
    # Bass energy → object scale
    target_scale = 1.0 + frame.signals.bass_energy * 0.4
    object.scale = lerp(object.scale, target_scale, smooth_factor)
    
    # Brightness → color
    target_hue = frame.signals.brightness * 360
    object.color.hue = lerp(object.color.hue, target_hue, smooth_factor)
    
    # Energy trend → animation speed
    if frame.signals.energy_trend > 0.3:
        object.animation_speed = 1.5
    elif frame.signals.energy_trend < -0.3:
        object.animation_speed = 0.5
    else:
        object.animation_speed = 1.0
```

**Latency**: 20-200ms (depending on tier)  
**Density**: Dense (60-120 samples/sec)  
**Best for**: Smooth animation, visual feedback

### Pattern 3: Hybrid (Events + Signals)
Combine for maximum responsiveness and smoothness.

```python
def on_audio_frame(frame):
    signals = frame.signals
    
    # 1. Handle events (immediate)
    for event in frame.events:
        if event.event_type == EventType.KICK:
            screen.flash(intensity=0.3)
    
    # 2. Animate with signals (smooth)
    object.scale = 1.0 + signals.bass_energy * 0.3
    object.color.brightness = signals.brightness
    
    # 3. Combine: Event intensity × signal energy
    if any(e.event_type == EventType.KICK for e in frame.events):
        kick_event = next(e for e in frame.events if e.event_type == EventType.KICK)
        effect_strength = kick_event.strength * signals.bass_energy
        particles.emit("kick_burst", strength=effect_strength)
    
    # 4. React to signal trends
    if signals.energy_trend > 0.5:
        animator.play("building")
    elif signals.energy_trend < -0.5:
        animator.play("fading")
```

### Pattern 4: Event Broadcasting
Broadcast events to multiple listeners.

```python
event_bus = EventBus()

# Register listeners
event_bus.on(EventType.KICK, lambda e: screen.flash(e.strength))
event_bus.on(EventType.KICK, lambda e: particles.emit("kick_burst", e.strength))
event_bus.on(EventType.KICK, lambda e: camera.shake(e.strength))

# Broadcast events
for event in frame.events:
    event_bus.emit(event)
```

**Advantage**: One kick event triggers many effects  
**Scalability**: Add listeners without changing event source

### Pattern 5: Predictive Rhythm Sync
Use beat prediction for zero-latency rhythm gameplay.

```python
time_until_beat = frame.signals.predicted_beat_timestamp_s - frame.timestamp_s

if player.pressed_button:
    # How accurate was the press?
    error_ms = abs(time_until_beat) * 1000
    accuracy = max(0, 1.0 - (error_ms / hit_window_ms))
    score += int(100 * accuracy)
    
    if accuracy > 0.9:
        hit_zone.flash("perfect")
    elif accuracy > 0.7:
        hit_zone.flash("good")
    else:
        hit_zone.flash("miss")
```

**Latency**: -50ms (ahead of audio, eliminates reactive delay)  
**Best for**: Rhythm games, beat-synced effects

### Pattern 6: Shader Effects
Pass signals directly to GPU:

```glsl
uniform float bassEnergy;      // 0-1
uniform float brightness;      // 0-1
uniform float beatPhase;       // 0-1

void main() {
    // Scale vertices by bass energy
    vec3 scaled = position * (1.0 + bassEnergy * 0.3);
    
    // Pulse based on beat phase
    float pulse = cos(beatPhase * 3.14159);
    scaled *= (1.0 + pulse * 0.1);
    
    // Brightness affects vertex color
    vec3 color = mix(vec3(0.0), vec3(1.0), brightness);
    
    gl_Position = projection * view * vec4(scaled, 1.0);
}
```

### Pattern 7: OSC/Network Streaming
Stream events (sparse) and signals (continuous) to external apps.

```python
import OSC

osc = OSC.OSCClient()
osc.connect(("localhost", 9000))

# Send continuous signals every frame (smooth)
osc.send_message("/audio/signals", [
    frame.signals.bass_energy,
    frame.signals.brightness,
    frame.signals.average_energy,
    frame.signals.beat_phase_0to1,
])

# Send events only when they occur (sparse)
for event in frame.events:
    if event.event_type == EventType.KICK:
        osc.send_message("/audio/kick", [event.strength])
    elif event.event_type == EventType.BEAT:
        osc.send_message("/audio/beat", [event.confidence])
```

## Comparison Table

| Aspect | Events | Signals |
|--------|--------|---------|
| Type | Discrete | Continuous |
| Timing | Point-in-time | Smooth over time |
| Latency | Very fast (5-10ms) | Tiered (5-10ms, 20-50ms, 100-500ms) |
| Density | Sparse (10-50/sec) | Dense (60-120/sec) |
| Consumption | Callbacks/listeners | Sampling/interpolation |
| Delivery | At occurrence time | Every frame available |
| Deduplication | Yes (fire once) | No (sample continuously) |
| Example | Kick at 10.5s | Bass 0.85 at 10.5s |
| Best for | Immediate actions | Smooth animation |
| Scaling | Broadcast to many | Sample per-object |

## Design Principles

1. **Clarity**: Each type has single, clear purpose
2. **Efficiency**: Events sparse, signals dense - optimal for different patterns
3. **Flexibility**: Use events alone, signals alone, or both
4. **Scalability**: Events broadcast; signals sampled per-object
5. **Latency Awareness**: Tiers for different latency requirements
6. **Interpolation**: Signals designed for smooth frame-to-frame interpolation
7. **Metadata**: Events carry type-specific data for rich context

## Migration from Old Approach

If converting from mixed `TieredRenderingMessage`:

```python
# Old way (mixed)
render = TieredRenderingMessage(
    timestamp_s=10.5,
    kick_detected=True,
    bass_energy=0.8,
    beat_phase=0.45,
)

# New way (separated)
frame = AudioFrame(
    timestamp_s=10.5,
    signals=ContinuousSignals(...),  # All continuous values
    events=[
        AudioEvent(EventType.KICK, timestamp_s=10.5, strength=0.9),
    ],
)

# Optional: Create rendering message for backward compat
def to_rendering_message(frame: AudioFrame) -> TieredRenderingMessage:
    kick_detected = any(e.event_type == EventType.KICK for e in frame.events)
    return TieredRenderingMessage(
        timestamp_s=frame.timestamp_s,
        kick_detected=kick_detected,
        bass_energy=frame.signals.bass_energy,
        # ... map other fields
    )
```

## Summary

Think of it this way:
- **Events** = Things that *happen* at a moment (beat occurred, kick detected)
- **Signals** = Things that *are true* over time (bass is 0.85, brightness is 0.72)

Different data types → Different handling → Better code → Clearer intent → Easier debugging

See [01_QUICK_START.md](01_QUICK_START.md) for examples and [08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md) for real-world patterns.
