# Beat Prediction Guide

Zero-latency predictive beat synchronization for rhythm games, animations, and synchronized effects.

## The Latency Problem

### Traditional Approach (Reactive)

```
Audio Event (Kick detected)
          ↓
       ~50ms
          ↓
Visual Effect (Screen flash)
```

**Problem**: User perceives 50-100ms delay between audio and visual feedback

### Predictive Approach (Proactive)

```
Audio Events (Build beat history)
          ↓
   Predict next beat
          ↓
   Trigger effect BEFORE beat arrives
          ↓
   Effect visible when beat hits audio
```

**Result**: Zero perceived latency, perfectly synchronized

## How Beat Prediction Works

### Step 1: Record Beat History

Every detected beat is recorded with timestamp and confidence:

```python
predictor = BeatPredictor()

# Record detected beats
predictor.record_beat(timestamp_s=10.0, confidence=0.95)
predictor.record_beat(timestamp_s=11.0, confidence=0.92)
predictor.record_beat(timestamp_s=12.0, confidence=0.94)
predictor.record_beat(timestamp_s=13.0, confidence=0.93)
```

### Step 2: Calculate Inter-Beat Intervals

```
Beat history: [10.0s, 11.0s, 12.0s, 13.0s]
Intervals:     [1.0s,  1.0s,  1.0s]
Average:       ~1.0s per beat
BPM:           60 BPM
```

### Step 3: Predict Future Beats

```python
next_beat = 13.0 + 1.0 = 14.0s
beat_after_next = 14.0 + 1.0 = 15.0s
```

### Step 4: Generate Beat Phase

Beat phase tracks position between beats:

```
0.0 = Beat just occurred
0.5 = Halfway to next beat
1.0 = Next beat about to occur (wraps to 0.0)

beat_phase = (current_time - last_beat_time) / interval
```

Visualized:

```
BEAT #1          BEAT #2          BEAT #3
  |                |                |
  v                v                v
  0─────────────────1─────────────────0
  │                 │                 │
  └─ phase 0.3 ────┘                 │
                    └─ phase 0.7 ────┘
```

### Step 5: Measure Confidence

```
confidence = (1.0 - interval_variance) * stability
```

Higher confidence = More stable tempo

## API

### Recording Beats

```python
def record_beat(timestamp_s: float, confidence: float = 1.0) -> None:
    """Record a detected beat.
    
    Args:
        timestamp_s: Beat timestamp in seconds
        confidence: Beat confidence (0-1, default 1.0)
    """
```

Example:
```python
# From analysis results
if slow_features.beat_detected:
    predictor.record_beat(
        timestamp_s=current_time,
        confidence=slow_features.beat_confidence
    )
```

### Getting Beat Phase

```python
def get_beat_phase(timestamp_s: float) -> tuple[float, float]:
    """Get current beat phase.
    
    Args:
        timestamp_s: Current timestamp
        
    Returns:
        Tuple of (beat_phase_0to1, confidence)
        
    Returns (None, 0.0) if insufficient beat history
    """
```

Example:
```python
beat_phase, confidence = predictor.get_beat_phase(current_time)

if beat_phase is not None:
    pulse = cos(beat_phase * 3.14159)  # 0 at beat, -1 at half, 0 at next
    object.scale = 1.0 + pulse * 0.2
```

### Predicting Next Beat

```python
def predict_next_beat(timestamp_s: float) -> float | None:
    """Predict when next beat arrives.
    
    Args:
        timestamp_s: Current timestamp
        
    Returns:
        Predicted beat timestamp or None if insufficient history
    """
```

Example:
```python
next_beat_time = predictor.predict_next_beat(current_time)

if next_beat_time is not None:
    time_until_beat = next_beat_time - current_time
    
    if time_until_beat < 0.05:  # Within 50ms
        effect.trigger()  # Trigger before beat arrives
```

## Zero-Latency Rhythm Game

Classic example: Tap on beat

```python
class RhythmGame:
    def __init__(self, predictor: BeatPredictor):
        self.predictor = predictor
        self.hit_window_ms = 100  # ±100ms acceptable
    
    def update(self, current_time: float):
        # Get next beat prediction
        next_beat = self.predictor.predict_next_beat(current_time)
        
        if next_beat is None:
            return  # Insufficient history
        
        time_until_beat = next_beat - current_time
        
        # Show countdown
        if time_until_beat < 0.3:  # 300ms before
            self.show_countdown(time_until_beat)
        
        # If beat just occurred
        if -0.05 < time_until_beat < 0.05:
            self.target.highlight()
    
    def on_player_tap(self, tap_time: float):
        # Get latest beat
        beat_phase, confidence = self.predictor.get_beat_phase(tap_time)
        
        if beat_phase is None:
            self.show_feedback("Too early")
            return
        
        # Calculate error from beat
        phase_error = abs(beat_phase - 0.0) * interval  # Convert phase to time
        if phase_error > 0.5:  # Closer to half-beat
            phase_error = interval - phase_error
        
        accuracy_ms = phase_error * 1000
        
        if accuracy_ms < 20:
            self.score += 300  # Perfect!
            self.show_feedback("PERFECT")
        elif accuracy_ms < 50:
            self.score += 150  # Good
            self.show_feedback("GOOD")
        elif accuracy_ms < self.hit_window_ms:
            self.score += 50   # OK
            self.show_feedback("OK")
        else:
            self.show_feedback("MISS")
```

## Predictive Animation Sync

Animate exactly on the beat:

```python
class PulseAnimation:
    def __init__(self, predictor: BeatPredictor):
        self.predictor = predictor
    
    def update(self, current_time: float, object_to_animate):
        beat_phase, confidence = self.predictor.get_beat_phase(current_time)
        
        if beat_phase is None:
            return  # No prediction yet
        
        # Pulse: 1.0 at beat, 0.0 at half, 1.0 at next beat
        pulse = (cos(beat_phase * 3.14159) + 1) / 2
        
        # Apply to scale
        scale = 1.0 + pulse * 0.3
        object_to_animate.scale = scale
        
        # Apply to rotation
        rotation = beat_phase * 360
        object_to_animate.rotation = rotation
        
        # Optional: Rotate faster when confident
        if confidence > 0.8:
            object_to_animate.animation_speed = 1.5
        else:
            object_to_animate.animation_speed = 1.0
```

## Event Generation

Generate events at predicted beats:

```python
class PredictiveEventGenerator:
    def __init__(self, predictor: BeatPredictor):
        self.predictor = predictor
        self.last_generated = -999
    
    def update(self, current_time: float) -> list[AudioEvent]:
        next_beat = self.predictor.predict_next_beat(current_time)
        
        if next_beat is None:
            return []
        
        # Only generate once per beat
        if round(next_beat, 2) != self.last_generated:
            self.last_generated = round(next_beat, 2)
            
            # Generate event at predicted time
            return [
                AudioEvent(
                    event_type=EventType.BEAT,
                    timestamp_s=next_beat,
                    strength=1.0,
                    confidence=self.predictor.get_beat_phase(current_time)[1],
                )
            ]
        
        return []
```

## Lighting Sync

Synchronize lighting with beat:

```python
class BeatSyncedLighting:
    def __init__(self, predictor: BeatPredictor):
        self.predictor = predictor
    
    def update(self, current_time: float, lighting_rig):
        beat_phase, confidence = self.predictor.get_beat_phase(current_time)
        
        if beat_phase is None:
            return
        
        # Brightness pulses with beat
        pulse = (cos(beat_phase * 3.14159) + 1) / 2
        brightness = 0.3 + pulse * 0.7
        lighting_rig.set_brightness(brightness)
        
        # Color changes at beat
        if beat_phase < 0.1:  # Near beat
            lighting_rig.set_color("white")
        else:
            lighting_rig.set_color("blue")
        
        # Strobe effect when very confident
        if confidence > 0.9 and beat_phase < 0.02:
            lighting_rig.strobe(duration=0.05)
```

## Shader Effects

Use beat prediction in GLSL:

```glsl
uniform float beatPhase;           // 0-1
uniform float predictionConfidence; // 0-1

void main() {
    // Pulse vertices with beat
    float pulse = cos(beatPhase * 3.14159);
    vec3 scaled = position * (1.0 + pulse * 0.2);
    
    // Rotate based on phase
    float rotation = beatPhase * 6.28319;
    scaled = rotate(scaled, rotation);
    
    // Brighten when confident
    vec3 color = baseColor * (0.5 + 0.5 * predictionConfidence);
    
    gl_Position = projection * view * vec4(scaled, 1.0);
}
```

## Robustness

### Handling Beat Tempo Changes

The predictor automatically adapts:

```python
# Tempo change from 120 BPM to 130 BPM
predictor.record_beat(10.0, 0.95)  # 120 BPM
predictor.record_beat(11.0, 0.93)  # 120 BPM
predictor.record_beat(11.88, 0.91) # 130 BPM (shorter interval)

# Predictor detects tempo change and adapts interval
```

### Low Confidence (Variable Tempo)

When tempo is unstable:

```python
beat_phase, confidence = predictor.get_beat_phase(current_time)

if confidence < 0.5:
    # Low confidence - tempo is unstable
    # Reduce reliance on prediction
    effect.scale_intensity(confidence)
else:
    # High confidence - safe to use
    effect.scale_intensity(1.0)
```

### Insufficient History

Until enough beats recorded:

```python
next_beat = predictor.predict_next_beat(current_time)

if next_beat is None:
    # Still building beat history
    # Fall back to reactive mode
    if frame.events and EventType.BEAT in frame.events:
        effect.trigger()  # React immediately instead of predicting
```

**Beat history needed**: 2-4 consistent beats for prediction to stabilize

## Performance

### CPU Cost

Prediction is computationally cheap:
- Recording beat: O(1)
- Calculating phase: O(1)
- Predicting next: O(1)

Total: < 0.1% CPU overhead

### Memory Cost

Stores only beat history:
- Typical history: 20-30 beats
- Memory per beat: ~16 bytes
- Total: < 1KB

## Limitations

1. **Requires Consistent Tempo**: Works best with steady beat (120±20 BPM)
2. **Gradual Tempo Changes**: Handles gradual (over 8+ beats), not sudden
3. **Complex Rhythms**: Works for simple 4/4 beat; polyrhythms need refinement
4. **Silent Sections**: Prediction continues based on history but confidence drops
5. **Lead-in Time**: Needs 2-4 beat observations before accurate prediction

## Best Practices

1. **Use in Conjunction with Fast Events**: Don't replace event detection, complement it
2. **Monitor Confidence**: Always check confidence before triggering critical effects
3. **Gradual Falloff**: Reduce effect intensity as confidence drops
4. **Visual Feedback**: Show when prediction is high/low confidence
5. **Testing**: Always test with actual music, not metronome (music has slight tempo variations)

## Example: Complete Beat-Synced Visual

```python
class BeatSyncedVisual:
    def __init__(self, predictor: BeatPredictor):
        self.predictor = predictor
        self.object = None
    
    def update(self, current_time: float):
        frame = pipeline.get_frame()
        
        if frame is None:
            return
        
        # Record new beats from events
        for event in frame.events:
            if event.event_type == EventType.BEAT:
                self.predictor.record_beat(
                    event.timestamp_s,
                    event.confidence
                )
        
        # Predictive sync
        beat_phase, confidence = self.predictor.get_beat_phase(current_time)
        
        if beat_phase is not None and confidence > 0.6:
            # Predictive mode
            pulse = cos(beat_phase * 3.14159)
            scale = 1.0 + pulse * 0.3 * confidence
        else:
            # Fallback to reactive mode
            scale = 1.0 + frame.signals.bass_energy * 0.3
        
        self.object.scale = lerp(self.object.scale, scale, 0.15)
```

See [03_EVENTS_VS_SIGNALS.md](03_EVENTS_VS_SIGNALS.md#pattern-5-predictive-rhythm-sync) for more pattern examples and [06_TIERED_ANALYSIS.md](06_TIERED_ANALYSIS.md) for how beat data is generated across analysis tiers.
