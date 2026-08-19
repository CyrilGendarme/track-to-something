# Integration Guide

How to integrate the audio engine with games, visualizers, and other applications.

## Quick Integration (5 Minutes)

### 1. Create Audio Source

```python
from src.sources import LiveAudio

# Option A: System loopback (Windows: Stereo Mix)
source = LiveAudio(device_name="Stereo Mix")

# Option B: USB input
source = LiveAudio(device_name="USB Audio Device")

# Option C: Audio file
from src.sources import LocalFileAudio
source = LocalFileAudio("music.wav")
```

### 2. Create and Start Pipeline

```python
from src.engine import AudioPipeline

pipeline = AudioPipeline(
    audio_source=source,
    num_processing_workers=4,
    circular_buffer_capacity_s=5.0,
    output_queue_maxsize=10,
)

pipeline.start()
```

### 3. Get Audio Frames in Main Loop

```python
import time

running = True
while running:
    frame = pipeline.get_frame()
    
    if frame is None:
        continue
    
    # Frame contains:
    # - frame.timestamp_s: Current time
    # - frame.signals: ContinuousSignals (25 fields)
    # - frame.events: list[AudioEvent] (beats, kicks, etc.)
    
    update_visual(frame)
    time.sleep(1/60)  # 60 FPS target

pipeline.stop()
```

## Integration Patterns

### Pattern 1: Game with Events + Signals

```python
class AudioReactiveGame:
    def __init__(self):
        self.source = LiveAudio()
        self.pipeline = AudioPipeline(self.source)
        self.pipeline.start()
    
    def update(self):
        frame = self.pipeline.get_frame()
        if not frame:
            return
        
        # Handle events (immediate)
        self._handle_events(frame.events)
        
        # Animate with signals (smooth)
        self._update_animation(frame.signals)
    
    def _handle_events(self, events):
        for event in events:
            if event.event_type == EventType.KICK:
                self.camera.shake(event.strength)
            elif event.event_type == EventType.SNARE:
                self.particles.emit("snare_burst")
    
    def _update_animation(self, signals):
        # Scale with bass
        self.object.scale = 1.0 + signals.bass_energy * 0.3
        
        # Color with brightness
        self.object.hue = signals.brightness * 360
        
        # Rotate with beat phase
        self.object.rotation = signals.beat_phase_0to1 * 360
    
    def close(self):
        self.pipeline.stop()
```

### Pattern 2: Visualizer with Spectral Tracking

```python
class AudioVisualizer:
    def __init__(self):
        self.source = LiveAudio()
        self.pipeline = AudioPipeline(self.source)
        self.pipeline.start()
        
        # For smooth animation
        self.smoothed_bass = 0.0
        self.smoothed_mid = 0.0
        self.smoothed_high = 0.0
    
    def update(self):
        frame = self.pipeline.get_frame()
        if not frame:
            return
        
        signals = frame.signals
        smooth_factor = 0.1
        
        # Smooth spectral bands
        self.smoothed_bass = lerp(self.smoothed_bass, signals.bass_energy, smooth_factor)
        self.smoothed_mid = lerp(self.smoothed_mid, signals.mid_energy, smooth_factor)
        self.smoothed_high = lerp(self.smoothed_high, signals.high_energy, smooth_factor)
        
        # Draw visualization
        self.draw_bars(self.smoothed_bass, self.smoothed_mid, self.smoothed_high)
    
    def draw_bars(self, bass, mid, high):
        # Height proportional to energy
        bar_bass_height = bass * 200
        bar_mid_height = mid * 200
        bar_high_height = high * 200
        
        # Color based on spectral density
        color_r = self.smoothed_high * 255
        color_g = self.smoothed_mid * 255
        color_b = self.smoothed_bass * 255
        
        self.renderer.draw_bar(100, bar_bass_height, (0, 0, int(color_b)))
        self.renderer.draw_bar(150, bar_mid_height, (0, int(color_g), 0))
        self.renderer.draw_bar(200, bar_high_height, (int(color_r), 0, 0))
    
    def close(self):
        self.pipeline.stop()
```

### Pattern 3: OBS Integration with OSC Streaming

```python
import OSC

class OBSAudioReactor:
    def __init__(self, obs_host: str = "localhost", obs_port: int = 9000):
        self.source = LiveAudio()
        self.pipeline = AudioPipeline(self.source)
        self.pipeline.start()
        
        # OSC client to OBS
        self.osc = OSC.OSCClient()
        self.osc.connect((obs_host, obs_port))
    
    def update(self):
        frame = self.pipeline.get_frame()
        if not frame:
            return
        
        # Send continuous signals (smooth updates)
        self._send_signals(frame.signals)
        
        # Send events (discrete updates)
        self._send_events(frame.events)
    
    def _send_signals(self, signals):
        # Send all signal values to OBS
        osc_message = [
            signals.bass_energy,
            signals.mid_energy,
            signals.high_energy,
            signals.brightness,
            signals.average_energy,
            signals.beat_phase_0to1,
        ]
        self.osc.send_message("/audio/signals", osc_message)
    
    def _send_events(self, events):
        for event in events:
            if event.event_type == EventType.KICK:
                self.osc.send_message("/audio/kick", [event.strength])
            elif event.event_type == EventType.SNARE:
                self.osc.send_message("/audio/snare", [event.strength])
            elif event.event_type == EventType.BEAT:
                self.osc.send_message("/audio/beat", [event.confidence])
    
    def close(self):
        self.pipeline.stop()
```

### Pattern 4: Beat-Synced Animation

```python
from src.engine import BeatPredictor

class BeatSyncedAnimator:
    def __init__(self):
        self.source = LiveAudio()
        self.pipeline = AudioPipeline(self.source)
        self.pipeline.start()
        
        self.predictor = BeatPredictor()
    
    def update(self):
        frame = self.pipeline.get_frame()
        if not frame:
            return
        
        # Record beats
        for event in frame.events:
            if event.event_type == EventType.BEAT:
                self.predictor.record_beat(event.timestamp_s, event.confidence)
        
        # Get beat prediction
        beat_phase, confidence = self.predictor.get_beat_phase(frame.timestamp_s)
        
        if beat_phase is not None:
            # Predictive animation
            pulse = cos(beat_phase * 3.14159)
            scale = 1.0 + pulse * 0.2 * confidence
            self.object.scale = scale
        else:
            # Fallback to reactive
            scale = 1.0 + frame.signals.bass_energy * 0.2
            self.object.scale = scale
    
    def close(self):
        self.pipeline.stop()
```

## Threading Model Integration

### Thread Safety

The engine uses thread-safe queues internally. Safe to call `pipeline.get_frame()` from any thread:

```python
import threading

class MultiThreadedApp:
    def __init__(self):
        self.pipeline = AudioPipeline(LiveAudio())
        self.pipeline.start()
    
    def main_thread(self):
        while True:
            frame = self.pipeline.get_frame()
            if frame:
                self.render(frame)
    
    def audio_thread(self):
        # Audio pipeline runs in background
        # Calling get_frame() is thread-safe
        pass
    
    def physics_thread(self):
        # Can also call get_frame() from physics thread
        frame = self.pipeline.get_frame()
        if frame:
            self.update_physics(frame)
```

### Async Integration

Use with async frameworks:

```python
import asyncio

class AsyncAudioApp:
    def __init__(self):
        self.pipeline = AudioPipeline(LiveAudio())
        self.pipeline.start()
    
    async def render_loop(self):
        while True:
            frame = self.pipeline.get_frame()
            if frame:
                await self.render(frame)
            
            await asyncio.sleep(1/60)  # 60 FPS
    
    async def main(self):
        await self.render_loop()
    
    def close(self):
        self.pipeline.stop()

# Usage
app = AsyncAudioApp()
asyncio.run(app.main())
app.close()
```

## Error Handling

### Handling Missing Audio Source

```python
def get_audio_source():
    # Try loopback first
    try:
        return LiveAudio(device_name="Stereo Mix")
    except:
        pass
    
    # Try USB fallback
    try:
        return LiveAudio(device_name="USB Audio Device")
    except:
        pass
    
    # Fall back to file
    return LocalFileAudio("fallback_audio.wav")

source = get_audio_source()
```

### Handling Pipeline Errors

```python
try:
    pipeline.start()
except RuntimeError as e:
    print(f"Pipeline error: {e}")
    # Fall back to silent mode
    run_without_audio()
```

### Handling Missing Frames

```python
for _ in range(100):
    frame = pipeline.get_frame()
    
    if frame is None:
        # Pipeline not ready yet, wait a bit
        time.sleep(0.01)
        continue
    
    # Process frame
    update_visual(frame)
```

## Performance Integration

### CPU Budget

The engine uses ~3-5% CPU at 44.1kHz with 4 processing workers.

**Budgeting**:
```
Total available: ~100% CPU
Audio engine:   ~5%
Your app:       ~50-60%
OS/overhead:    ~30-40%
Headroom:       ~5-10%
```

### Frame Rate Integration

Target 60 FPS:

```python
import time

fps_target = 60
frame_time = 1.0 / fps_target

last_time = time.time()

while running:
    frame = pipeline.get_frame()
    if frame:
        update(frame)
        render()
    
    # Frame pacing
    elapsed = time.time() - last_time
    sleep_time = frame_time - elapsed
    
    if sleep_time > 0:
        time.sleep(sleep_time)
    
    last_time = time.time()
```

### Memory Budget

Total memory footprint:

```
Circular buffer:    ~88KB
Queue buffers:      ~50KB
Feature buffers:    ~30KB
Beat history:       ~1KB
---
Total:              ~170KB
```

Plus your application's memory. Very lightweight!

## GUI Framework Integration

### PyQt/PySide Integration

```python
from PyQt6.QtCore import QThread, pyqtSignal

class AudioWorkerThread(QThread):
    frame_ready = pyqtSignal(object)  # Emit frame
    
    def __init__(self):
        super().__init__()
        self.pipeline = AudioPipeline(LiveAudio())
        self.running = True
    
    def run(self):
        self.pipeline.start()
        
        while self.running:
            frame = self.pipeline.get_frame()
            if frame:
                self.frame_ready.emit(frame)
            
            self.msleep(16)  # ~60 FPS
    
    def stop(self):
        self.running = False
        self.pipeline.stop()
        self.wait()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.worker = AudioWorkerThread()
        self.worker.frame_ready.connect(self.on_audio_frame)
        self.worker.start()
    
    def on_audio_frame(self, frame):
        # Update GUI with audio data
        self.update_visual(frame)
    
    def closeEvent(self, event):
        self.worker.stop()
        super().closeEvent(event)
```

### Pygame Integration

```python
import pygame

class AudioReactiveGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        
        self.pipeline = AudioPipeline(LiveAudio())
        self.pipeline.start()
    
    def run(self):
        clock = pygame.time.Clock()
        running = True
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            frame = self.pipeline.get_frame()
            if frame:
                self.update(frame)
                self.draw()
            
            pygame.display.flip()
            clock.tick(60)
        
        self.close()
    
    def close(self):
        self.pipeline.stop()
        pygame.quit()
```

### Unity/Godot Integration

For game engine integration, use OSC to communicate:

```python
# Python side
osc = OSC.OSCClient()
osc.connect(("localhost", 9000))

# Send signals every frame
osc.send_message("/audio/bass", [signals.bass_energy])
osc.send_message("/audio/beat", [beat_phase, confidence])
```

On game engine side (C# for Unity):

```csharp
void ReceiveOSCMessage(string address, float value)
{
    if (address == "/audio/bass")
    {
        transform.localScale = new Vector3(1 + value * 0.3f, 1 + value * 0.3f, 1);
    }
    else if (address == "/audio/beat")
    {
        animator.speed = 1.0f + value * 0.5f;
    }
}
```

## Cleanup

Always clean up properly:

```python
try:
    # ... run application ...
finally:
    pipeline.stop()
```

Or use context manager pattern:

```python
class AudioPipelineContext:
    def __enter__(self):
        self.pipeline = AudioPipeline(LiveAudio())
        self.pipeline.start()
        return self.pipeline
    
    def __exit__(self, *args):
        self.pipeline.stop()

# Usage
with AudioPipelineContext() as pipeline:
    while running:
        frame = pipeline.get_frame()
        # ... process ...
```

## Common Pitfalls

| Issue | Solution |
|-------|----------|
| **No audio data** | Check audio device name with `LiveAudio.list_devices()` |
| **Choppy animation** | Use `signals`, not just events. Events are sparse! |
| **High CPU** | Reduce `num_processing_workers` (default 4) |
| **Latency too high** | Lower processing workers, or sample only Medium/Fast tiers |
| **Beat prediction unstable** | Need 4+ consistent beats, check `confidence` before using |
| **Pipeline hangs** | Ensure you're calling `pipeline.get_frame()` regularly |
| **Memory leak** | Always call `pipeline.stop()` in cleanup |

## Debugging

### Check Pipeline Status

```python
if pipeline.is_running():
    print("Pipeline active")

frame = pipeline.get_frame()
if frame is None:
    print("Waiting for first frame...")
else:
    print(f"Frame time: {frame.timestamp_s:.3f}s")
    print(f"Bass energy: {frame.signals.bass_energy:.2f}")
    print(f"Events: {len(frame.events)}")
```

### Log Frame Data

```python
def log_frame(frame):
    print(f"[{frame.timestamp_s:.2f}s]")
    print(f"  Signals: bass={frame.signals.bass_energy:.2f}, "
          f"mid={frame.signals.mid_energy:.2f}, "
          f"high={frame.signals.high_energy:.2f}")
    print(f"  Events: {[e.event_type.value for e in frame.events]}")
```

### Monitor Thread Health

```python
import threading

def show_threads():
    for thread in threading.enumerate():
        print(f"  {thread.name}: {'alive' if thread.is_alive() else 'dead'}")
```

## Performance Profiling

Use Python profiler to identify bottlenecks:

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# ... run for a while ...

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

See [02_ARCHITECTURE.md](02_ARCHITECTURE.md) for more details on threading and performance, and [01_QUICK_START.md](01_QUICK_START.md) for basic setup.
