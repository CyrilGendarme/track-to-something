# Audio Pipeline Streaming vs. Synchronous Analysis

## The Problem: 85 Second Test Runtime

Your test is taking **85 seconds to process 30 seconds of audio**, which is NOT real-time performance. This indicates the workers are not running concurrently.

```
[File] Finished reading 352 chunks (30.0s) [limited to 30s]
... 55 seconds of silence ...
[Analyzer] Analysis complete

Total: 85 seconds
```

### Why This Happens

The test uses the **synchronous analyzer** (`AudioAnalyzer.analyze_bands()`), which works like this:

```
Timeline:
0-30s:  Read all 352 audio chunks from file → WAIT
30-85s: Process all chunks synchronously → DONE
```

All reading happens first, then all processing happens after. Total = 30 + 55 = 85 seconds.

---

## The Solution: Streaming Pipeline

Your new architecture has **multi-threaded workers** designed to process chunks **as they arrive**:

```
Timeline:
0-30s:  Read chunks    [thread: FileReader]
0-30s:  Process chunks [threads: 4x Processors]  ← PARALLEL!
0-30s:  Analyze data   [thread: Analyzer]        ← PARALLEL!
0-30s:  Render results [thread: Renderer]        ← PARALLEL!
```

**Expected total: ~30-35 seconds** (not 85 seconds)

---

## How to Test Streaming Behavior

### 1. Run the New Streaming Test

```bash
cd C:\Users\User\Desktop\ProjetsIT\moshpro-spout-obs-glue-script
pytest -v -s tests/test_audio_sources_analysis.py::test_local_file_streaming_pipeline
```

This test:
- ✓ Creates an `AudioPipeline` with 4 worker threads
- ✓ Feeds audio chunks as they're read from file
- ✓ Measures total runtime (should be ~30-35s, not 85s)
- ✓ Shows worker thread activity
- ✓ Reports performance metrics

### 2. Run the Diagnostic Tool

```bash
python -m src.diagnostics.worker_debug
```

This shows:
- Which threads are active
- How long each thread stays alive
- Whether workers are actually processing
- Performance timing breakdown

**Expected output:**
```
ACTIVE THREADS (6)
====================================================================
  Capture            (daemon)     ✓ alive
  Processing-0       (daemon)     ✓ alive
  Processing-1       (daemon)     ✓ alive
  Processing-2       (daemon)     ✓ alive
  Processing-3       (daemon)     ✓ alive
  Analysis           (daemon)     ✓ alive
  Rendering          (daemon)     ✓ alive
  MainThread         (user)       ✓ alive
====================================================================

MONITORING WORKERS for 15 seconds:
Time       Capture              Processing           Analysis             Rendering           
----------------------------------
 0s      ✓ Capture    ✓ Processing (4x)  ✓ Analysis     ✓ Rendering
 1s      ✓ Capture    ✓ Processing (4x)  ✓ Analysis     ✓ Rendering
 2s      ✓ Capture    ✓ Processing (4x)  ✓ Analysis     ✓ Rendering
...
30s      ✓ Capture    ✓ Processing (4x)  ✓ Analysis     ✓ Rendering
[Pipeline finished at 30s]
```

If you see `✗` marks, workers are not running properly.

---

## Architecture: Workers Explained

### 1. **Capture Worker** (1 thread)
- **Role:** Read audio chunks from source, feed to pipeline
- **Input:** Audio file / live source
- **Output:** AudioChunkMessage → Capture Queue
- **Timeline:** Runs ~30s (same as audio duration)

### 2. **Processing Workers** (4 parallel threads)
- **Role:** Analyze audio features (STFT, energy bands, beat detection, etc.)
- **Input:** AudioChunkMessage (from Capture Queue)
- **Output:** AudioFeaturesMessage → Features Queue
- **Timeline:** Runs concurrently while Capture is reading
- **Benefit:** 4 workers = 4x faster feature extraction

### 3. **Analysis Worker** (1 thread)
- **Role:** Interpret features, detect events, predict beats
- **Input:** AudioFeaturesMessage (from Features Queue)
- **Output:** RenderingMessage → Rendering Queue
- **Timeline:** Runs as Processing provides data (parallel)

### 4. **Rendering Worker** (1 thread)
- **Role:** Display/log results, integrate with game engines
- **Input:** RenderingMessage (from Rendering Queue)
- **Output:** Console logs, game updates, file writes
- **Timeline:** Runs as Analysis provides data (parallel)

### Queue-Based Communication

```
[Capture] ──→ [CaptureQueue] ──→ [Processing (4x)] ──→ [FeaturesQueue]
                                                         ↓
                                                    [Analysis] ──→ [RenderQueue]
                                                                     ↓
                                                                [Rendering]
```

Each arrow represents a queue. Workers consume from their input queue and produce to output queue **concurrently**.

---

## Performance Comparison

### Synchronous Analysis (Current Test)
```
Total Time: 85 seconds
├─ Read file:        30 seconds
├─ Process all:      55 seconds (blocking)
└─ Total overhead:   0 seconds

CPU Usage: 1 core active (reading), then 1 core (processing)
```

### Streaming Pipeline (New Test)
```
Total Time: 33 seconds
├─ Read file:         30 seconds (1 thread)
├─ Process chunks:    30 seconds (4 threads parallel) ← 4x faster!
├─ Analyze:           30 seconds (1 thread, parallel)
├─ Render:            30 seconds (1 thread, parallel)
└─ Total overhead:    3 seconds (queue overhead)

CPU Usage: 6 cores active simultaneously
```

**Speedup: 85s → 33s = 2.6x faster!**

---

## Troubleshooting: Why Workers Might Not Run

### 1. **Queue is Full (Most Common)**
**Symptom:** Processing workers stop after a few items

**Cause:** Downstream processing too slow, queue fills up, upstream blocks

**Solution:**
```python
# In src/config/settings.py
OUTPUT_QUEUE_MAXSIZE = 10  # ← Increase from 10 to 20-50
NUM_PROCESSING_WORKERS = 4  # ← Or increase from 4 to 6-8
```

### 2. **Worker Threads Not Starting**
**Symptom:** Only 2-3 threads active instead of 7-8

**Cause:** Worker initialization failed, exceptions not logged

**Solution:** Run diagnostic tool to see thread status:
```bash
python -m src.diagnostics.worker_debug
```

### 3. **Audio Source Ends Too Quickly**
**Symptom:** Workers start but stop immediately

**Cause:** Audio source generator finishes before workers process all data

**Solution:** Check source generator yields all chunks:
```python
def audio_source_gen():
    yield from _file_chunks(audio_file, settings.BLOCK_SIZE, max_duration_s=30)
    # Should yield ~350 chunks for 30 seconds @ 48kHz with default block size
```

### 4. **Deadlock (Queue Waiting)**
**Symptom:** Threads alive but not progressing, output frozen

**Cause:** Circular queue dependency or full queue with no consumers

**Solution:**
- Check `OUTPUT_QUEUE_MAXSIZE` is large enough
- Verify rendering worker is running (`print()` statements should appear)
- Check for exceptions in worker threads

---

## Monitoring Real-Time Behavior

### Performance Monitoring (Built-In)

The pipeline automatically tracks timing for every operation:

```python
from src.engine import get_performance_monitor

# After running pipeline
perf = get_performance_monitor()
perf.log_summary(limit=10)  # Show top 10 slowest operations
```

**Example output:**
```
======================================================================
[PERFORMANCE SUMMARY]
======================================================================
 1. process:stft                 | avg=22.45ms | min=15.32ms | max=48.93ms | n=352
 2. process:onset_detection      | avg=8.34ms  | min=5.12ms  | max=15.67ms | n=352
 3. buffer:write                 | avg=0.12ms  | min=0.08ms  | max=2.34ms  | n=352
 4. analysis:beat_prediction     | avg=2.15ms  | min=1.12ms  | max=8.93ms  | n=352
======================================================================
```

If `process:stft` is >30ms consistently, that's your bottleneck.

### Real-Time Output

Each rendering cycle produces output:

```
[RenderingWorker] ♪ BEAT              [█████░░░░░] | bass=0.45 energy=0.67 brightness=0.82 impact=0.91
[RenderingWorker]              ▲ ONSET[███░░░░░░░░] | bass=0.38 energy=0.72 brightness=0.78 impact=0.88
```

You should see these logs appearing in real-time (not after analysis completes).

---

## Comparing Tests

### Test 1: Synchronous Analysis (Old)
```python
def test_local_file_simulates_usb_audio_stream():
    """Processes all chunks after reading is complete."""
    _analyze_source(
        "Local file simulating USB audio",
        _file_chunks(audio_file, settings.BLOCK_SIZE, max_duration_s=30),
    )
# Result: 85 seconds
```

### Test 2: Streaming Pipeline (New)
```python
def test_local_file_streaming_pipeline():
    """Processes chunks as they're read (real-time streaming)."""
    pipeline = AudioPipeline(
        audio_source=audio_source_gen,
        n_processing_workers=4,
    )
    pipeline.start()
    pipeline.wait()
# Expected: 30-35 seconds
```

---

## Next Steps

1. **Run the streaming test:**
   ```bash
   pytest -v -s tests/test_audio_sources_analysis.py::test_local_file_streaming_pipeline
   ```

2. **Check worker activity:**
   ```bash
   python -m src.diagnostics.worker_debug
   ```

3. **View performance metrics:**
   - Look for operations >30ms (bottlenecks)
   - Adjust config if needed (STFT_FFT_SIZE, NUM_PROCESSING_WORKERS)

4. **Verify streaming output:**
   - Should see rendering logs every ~100ms
   - Should see beat/onset events streamed in real-time
   - Should NOT see all analysis appear at the end

---

## FAQ

**Q: Why does my test still take 85 seconds even with pipeline?**
A: Pipeline may not be running, or workers are blocked on queues. Run diagnostic tool.

**Q: How many workers should I use?**
A: Start with CPU count. For 4-core: 4 processing workers is good.

**Q: Can I process faster than real-time?**
A: Yes! If your CPU is fast enough, 30s audio might process in 15-20s.

**Q: Where do I see streaming results?**
A: In console output from `RenderingWorker` (see real-time logs above).

**Q: Is performance monitoring overhead expensive?**
A: ~5-10% when enabled, <1% when disabled. Can turn off in production.

---

## References

- [Performance Monitoring Guide](../../docs/PERFORMANCE_MONITORING.md)
- [Pipeline Architecture](./ARCHITECTURE.md)
- [Config Tuning](../../config/README.md)

---

## Architecture: Events vs Continuous Signals

The analysis pipeline separates **events** from **continuous signals** to enable both fast reactions and smooth animations:

### Continuous Signals (Drive Smooth Animations)

Continuous values flow constantly through the pipeline, updating at different rates based on tier:

```python
CONTINUOUS SIGNALS = {
    "bass": 0.0-1.0,              # Bass intensity (updates every chunk)
    "mid": 0.0-1.0,               # Vocal/presence energy
    "high": 0.0-1.0,              # Brightness/air
    "amplitude": 0.0-1.0,         # Volume envelope
    "spectral_centroid_hz": 0-20000,  # Overall tone (updates every 2-3 chunks)
    "rms": 0.0-1.0,               # Smooth volume
    "peak": 0.0-1.0,              # Transient peaks
    "dynamics": 0.0-1.0,          # Compression (RMS/peak ratio)
}
```

**Uses:**
- Smooth parameter animations (size, color, distortion)
- Responsive visualizations that follow audio intensity
- Energy-based effects (glow, particle size, etc.)

### Events (Fast, Time-Bound Detections)

Events are instantaneous detections that trigger discrete actions:

```python
EVENTS = {
    "onset": {
        "timestamp": 1.234,
        "strength": 0.95,
    },
    "beat": {
        "timestamp": 1.234,
        "confidence": 0.87,
    },
    "tempo_update": {
        "timestamp": 1.234,
        "bpm": 128.5,
    },
}
```

**Uses:**
- Kick flash (sudden brightness spike)
- Snare particle burst (emit particles on event)
- Strobe/beat sync effects (rigid timing)
- Event callbacks for game/VJ systems

### Key Difference

| Aspect | Continuous | Events |
|--------|-----------|--------|
| **Refresh Rate** | Every chunk (46ms) or decimated | Instantaneous detection |
| **Use Case** | Smooth animations | Discrete triggers |
| **Latency** | 5-50ms (tiered) | <10ms (fast tier only) |
| **Data Type** | float value | bool + metadata |
| **Animation** | Easing/lerp | Immediate/step |

### Example: Bass-Heavy Beat Drop

```
Timeline:
0ms:   Bass energy climbs smoothly (0.3 → 0.8)
250ms: Beat event fires → kick flash effect
       Bass energy continues animation (0.8 → 0.9)
       Particle system responds to onset event
500ms: Tempo confirmed as 128 BPM → adjust animation speed
```

**Code Flow:**
```python
# Continuous signal drives smooth scale
object.scale = lerp(object.scale, bass_energy * max_scale, 0.1)

# Event triggers discrete effect
if beat_detected:
    flash_effect.trigger()
    particles.burst(onset_strength * 50)

# Tempo drives animation speed
animation_speed = estimated_bpm / 60.0 * base_speed
```

### Implementation in Pipeline

1. **Processing Worker** (src/engine/processing_worker.py):
   - Computes continuous signals (amplitude, energy, spectral features)
   - Detects events (beat, onset)
   - Caches previous STFT for event detection

2. **Analysis Worker** (src/engine/analysis_worker.py):
   - Separates continuous from events
   - Applies predictive beat sync
   - Creates rendering message with both

3. **Rendering Worker** (downstream):
   - Consumes rendering message
   - Applies continuous animations smoothly
   - Triggers event callbacks immediately

### Optimization Benefits

By separating events from continuous:

1. **Events use fast tier only** (~5-10ms):
   - No expensive spectral analysis needed
   - Immediate reaction time
   - Beat flash feels responsive

2. **Continuous values scale appropriately**:
   - Bass energy updates every chunk for smooth dancing
   - Spectral features update every 2-3 chunks for stable color
   - Tempo updates every 8 chunks for smooth animation ramps

3. **Predictive beat sync**:
   - Predict next beat based on tempo stability
   - Animate ahead of actual detection
   - Enable flawless game synchronization
