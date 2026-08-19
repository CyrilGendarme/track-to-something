# Architecture Guide

Complete overview of the real-time audio analysis engine architecture.

## System Overview

A multi-threaded pipeline that captures, analyzes, and renders audio features in real-time with predictive beat synchronization.

```
Audio Source (Loopback/USB/File)
            ↓
┌─────────────────────────────────────────────┐
│ AudioCaptureWorker (daemon thread)          │
│ • Reads audio chunks from source            │
│ • Stores in 5-second circular buffer        │
│ • Sends to processing queue (~21 fps)       │
└─────────────────────────────────────────────┘
            ↓ processing_queue
┌─────────────────────────────────────────────┐
│ AudioProcessingWorker × 4 (parallel)        │
│ • STFT computation                          │
│ • Spectral feature extraction               │
│ • Beat confidence estimation                │
│ • Tempo/BPM calculation                     │
└─────────────────────────────────────────────┘
            ↓ features_queue
┌─────────────────────────────────────────────┐
│ AnalysisWorker                              │
│ • Event detection (beat, kick, snare)       │
│ • Beat prediction from tempo                │
│ • Onset detection                           │
│ • Event callbacks                           │
└─────────────────────────────────────────────┘
            ↓ rendering_queue
┌─────────────────────────────────────────────┐
│ RenderingWorker                             │
│ • Output to game/visualizer                 │
│ • UI updates                                │
│ • Data logging                              │
└─────────────────────────────────────────────┘
            ↓
     (Game/UI/Output)
```

## Core Components

### 1. CircularAudioBuffer

**Purpose:** Thread-safe ring buffer for shared audio storage

**Size:** 5 seconds (220,500 samples @ 44.1kHz, 2 channels)

**Operations:**
- `write(samples)`: Add chunk with wrap-around
- `read_latest(duration_s)`: Get most recent samples

**Thread Safety:** `threading.RLock` protects all access

```python
buffer = CircularAudioBuffer(capacity_s=5.0, sample_rate=44100)
buffer.write(audio_chunk)  # 2048 samples
recent = buffer.read_latest(1.0)  # Last 1 second
```

### 2. Worker Threads

#### AudioCaptureWorker
- **Role**: Source of audio data
- **Frequency**: Reads 2048-sample chunks ~21 times/second
- **Output**: `AudioChunkMessage` to processing queue
- **Storage**: Circular buffer for multi-window analysis

```python
worker = AudioCaptureWorker(
    audio_source=source,
    output_queue=queue,
    buffer=circular_buffer,
)
worker.start()
```

#### AudioProcessingWorker (×4 parallel)
- **Role**: Feature extraction via STFT
- **Input**: `AudioChunkMessage` from processing queue
- **Output**: `AudioFeaturesMessage` to features queue
- **Parallelism**: 4 workers handle queue load

**Features extracted:**
- Amplitude: RMS, peak, overall
- Spectral: Bass/mid/high energy (3 frequency bands)
- Onset: Rapid energy rise detection
- Tempo: BPM estimation from energy peaks
- Envelopes: Per-band energy over time

```python
worker = AudioProcessingWorker(
    input_queue=processing_queue,
    output_queue=features_queue,
)
worker.start()
```

#### AnalysisWorker
- **Role**: Event detection and prediction
- **Input**: `AudioFeaturesMessage` from features queue
- **Output**: `RenderingMessage` to rendering queue
- **State**: Maintains beat history for tempo estimation

**Detection:**
- Beat transitions (onset confidence → peak)
- Kick detection (bass energy > threshold)
- Snare detection (mid/high energy peaks)
- General onsets (rapid energy rise)

**Prediction:**
- Estimates next beat from recent beat intervals
- Calculates beat phase (0=beat, 1=next beat)
- Computes prediction confidence

```python
worker = AnalysisWorker(
    input_queue=features_queue,
    output_queue=rendering_queue,
)
worker.start()
```

#### RenderingWorker
- **Role**: Final output stage
- **Input**: `RenderingMessage` or `AudioFrame` from rendering queue
- **Output**: Game/UI updates, logging, OSC streaming

```python
worker = RenderingWorker(
    input_queue=rendering_queue,
)
worker.start()
```

### 3. Message Types

#### AudioChunkMessage
Raw audio samples from capture.

```python
@dataclass
class AudioChunkMessage:
    samples: np.ndarray  # (n_samples, 2) float32
    sample_rate: int
```

#### AudioFeaturesMessage
Comprehensive features from processing worker (15 fields).

```python
@dataclass
class AudioFeaturesMessage:
    timestamp_s: float
    
    # Amplitude
    overall_amplitude: float
    rms: float
    peak: float
    
    # Spectral
    bass_energy: float
    mid_energy: float
    high_energy: float
    spectral_centroid_hz: float | None
    dominant_frequency_hz: float | None
    
    # Temporal
    onset_detected: bool
    beat_detected: bool
    beat_confidence: float
    
    # Tempo
    bpm: float | None
    
    # Envelopes
    band_bass_envelope: tuple[float, ...] | None
    band_mid_envelope: tuple[float, ...] | None
    band_high_envelope: tuple[float, ...] | None
```

#### RenderingMessage
Normalized output with predictive beat sync (12 fields).

```python
@dataclass
class RenderingMessage:
    timestamp_s: float
    
    # Energy (0-1)
    bass: float
    energy: float
    brightness: float
    impact: float
    
    # Events
    beat: bool
    beat_confidence: float
    onset: bool
    
    # Derived
    tempo_bpm: float | None
    dynamics: float
    
    # Predictive
    beat_phase_0to1: float
    predicted_beat_timestamp_s: float | None
    prediction_confidence: float
```

#### AudioFrame
Combined events and signals.

```python
@dataclass
class AudioFrame:
    timestamp_s: float
    signals: ContinuousSignals
    events: list[AudioEvent]
```

### 4. Multi-Window Analyzer

**Purpose:** Three concurrent analysis windows on same circular buffer

**Architecture:**
- Single 50-100ms circular buffer
- FastAnalyzer (10ms windows) - immediate transient detection
- MediumAnalyzer (32ms windows) - energy tracking with STFT
- SlowAnalyzer (250ms windows) - overall metrics and beat tracking

**Efficiency:**
- CPU: 5-10% (vs 15-30% for separate pipelines)
- Memory: 100KB (vs 22MB for traditional approach)

```python
analyzer = MultiWindowAudioAnalyzer(
    sample_rate=44100,
    fast_window_ms=10.0,     # 5-10ms latency
    medium_window_ms=32.0,   # 20-50ms latency
    slow_window_ms=250.0,    # 100-500ms latency
)

# Analyze current buffer
fast, medium, slow = analyzer.analyze_all(timestamp_s)
```

### 5. BeatPredictor

**Purpose:** Estimate next beat from tempo history

**Algorithm:**
- Records last N beat timestamps (default: 10)
- Calculates interval statistics (mean, std dev)
- Predicts next beat assuming constant BPM
- Confidence based on interval stability

**Latency Advantage:**
- Reactive beat detection: 100-150ms latency
- Predictive beat detection: -50ms (ahead of audio)
- Enables zero-latency rhythm synchronization

```python
predictor = BeatPredictor()
predictor.record_beat(timestamp_s=10.5)

# 50ms later
beat_phase, confidence = predictor.get_beat_phase(10.55)
next_beat_time = predictor.predict_next_beat(10.55)
```

## Data Flow

### Capture → Processing
1. AudioCaptureWorker reads 2048 samples
2. Stores in circular buffer
3. Sends `AudioChunkMessage` to processing queue
4. Frequency: ~21 times/second (2048 @ 44.1kHz)

### Processing → Analysis
1. AudioProcessingWorker gets `AudioChunkMessage`
2. Computes STFT (n_fft=2048, hop=512, Hann window)
3. Extracts frequency bands (bass, mid, high)
4. Detects onsets, estimates BPM
5. Sends `AudioFeaturesMessage` to features queue
6. With 4 parallel workers: throughput matches or exceeds input

### Analysis → Rendering
1. AnalysisWorker gets `AudioFeaturesMessage`
2. Detects beat transitions and events
3. Updates BeatPredictor with beat timestamps
4. Computes beat phase and next beat prediction
5. Sends `RenderingMessage` to rendering queue
6. Also generates `AudioFrame` with clean events/signals separation

### Rendering → Output
1. RenderingWorker gets `RenderingMessage`/`AudioFrame`
2. Sends to game, UI, OSC, logging, etc.
3. Optional frame skipping for lower CPU

## Threading Model

### Thread Safety

**Circular Buffer:**
- Protected by `threading.RLock`
- Multiple readers (all analyzers) OK
- Single writer (capture worker)

**Queues:**
- Use `queue.Queue` (thread-safe by design)
- Non-blocking get with timeout (0.1s)
- Non-blocking put when queue full

**Worker States:**
- Each thread has `_stop_event` for graceful shutdown
- `is_stopped()` checked in main loop
- `join()` waits for completion

**Event Callbacks:**
- Called from AnalysisWorker thread
- Consumer responsible for thread safety
- Can queue work to game thread instead

### Synchronization

```
Timeline (milliseconds):
0     - Audio sample captured by OS
~5-10 - AudioCaptureWorker reads it
~15   - In circular buffer
~25   - AudioProcessingWorker computes STFT
~35   - AudioFeaturesMessage in queue
~40   - AnalysisWorker processes features
~45   - RenderingMessage ready
~50   - Game/UI receives output

Total latency: 45-50ms (capture to output)
```

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| CPU Usage | 5-10% | vs 15-30% for separate pipelines |
| Memory | ~100KB | Circular buffer only |
| Capture Latency | ~5-10ms | OS audio → engine |
| Processing Latency | ~20-30ms | STFT computation |
| Analysis Latency | ~5ms | Event detection |
| Total Pipeline | ~45-50ms | Capture to output |
| Fast Tier | 5-10ms | From buffer read |
| Medium Tier | 20-50ms | With STFT |
| Slow Tier | 100-500ms | Windowed averaging |
| Predictive Latency | -50ms | Ahead of actual beat |

## Queue Depths

Under normal operation:

| Queue | Typical Depth | Max Depth |
|-------|---------------|-----------|
| Processing | 1-3 chunks | 10 (backpressure) |
| Features | 1-2 messages | 10 |
| Rendering | 0-1 messages | 10 |

When queue full:
- Capture worker waits (backpressure)
- Processing workers drain queue
- System self-regulates

## Integration Points

### Input: Audio Sources
- `LiveAudio`: Loopback (Stereo Mix) or USB device
- `LocalFileAudio`: WAV file playback
- Custom: Implement `AudioSource` interface

### Output: Consumers
- Game engine: Get frames, handle events/signals
- Visualizer: Animate with continuous signals
- OSC: Stream to Max/MSP, Pure Data, etc.
- Network: Send to other machines
- Database: Log analytics
- Callbacks: Event listeners

## Configuration

### Typical Setup
```python
from src.engine import AudioPipeline
from src.sources import LiveAudio

pipeline = AudioPipeline(
    audio_source=LiveAudio(),
    num_processing_workers=4,
    circular_buffer_capacity_s=5.0,
    output_queue_maxsize=10,
)
pipeline.start()
```

### Tuning for Your Use Case

**Low Latency (games):**
- Use FastAnalyzer and events
- Small rendering queue (1-2 items)
- Skip non-critical frames

**Smooth Animation:**
- Use MediumAnalyzer and signals
- Enable interpolation in consumer

**Beat Synchronization:**
- Use BeatPredictor
- Predictive latency: -50ms (ahead)

**Analysis/Logging:**
- Use SlowAnalyzer for metrics
- Large circular buffer (5-10s)
- Log all events

## Design Decisions

### Why Multi-Threaded?

**Benefits:**
- Capture never blocks processing
- Processing never blocks analysis
- UI thread stays responsive
- Scales to multiple cores

**Trade-offs:**
- Complexity of queue management
- Potential for queue backlog
- Thread synchronization overhead

### Why Circular Buffer?

**Benefits:**
- Constant memory (no growth)
- Efficient for multi-window analysis
- Single shared buffer for all analyzers

**Trade-offs:**
- Fixed size (can't grow larger)
- Wrap-around complexity

### Why Multi-Window?

**Benefits:**
- Different latencies for different needs
- Single efficient buffer
- Optimal CPU usage

**Trade-offs:**
- More complex than single-window
- Requires explicit tier selection

### Why Predictive Beat?

**Benefits:**
- Zero-latency rhythm sync (-50ms)
- Enables rhythm games
- Better UX for user actions

**Trade-offs:**
- Requires stable tempo
- Needs beat detection first

## Extending the System

### Add Custom Audio Source
```python
from src.sources import AudioSource

class MyAudioSource(AudioSource):
    def read_chunk(self) -> np.ndarray:
        # Return (n_samples, 2) float32 audio
        pass
```

### Add Custom Analysis
```python
# Hook into AnalysisWorker's processing
def custom_analysis(features: AudioFeaturesMessage) -> dict:
    return {
        "custom_metric": calculate_something(features)
    }
```

### Add Custom Event Type
```python
from src.engine.events import EventType

# Extend EventType enum
# Add to event detection in AnalysisWorker
```

### Add Custom Rendering
```python
class CustomRenderer(RenderingWorker):
    def _process_item(self, item: RenderingMessage):
        # Custom output here
        pass
```

## Troubleshooting Architecture Issues

### Queue Bottleneck
- Increase `num_processing_workers`
- Profile with `queue.qsize()`
- Check if consumer is slow

### High Latency
- Reduce circular buffer size
- Skip some processing
- Profile timing at each stage

### Lost Events
- Increase queue sizes
- Add event buffering
- Verify event generation

### Out of Sync Beat
- Check BeatPredictor confidence
- Verify beat detection is working
- Try different confidence thresholds

See [06_TIERED_ANALYSIS.md](06_TIERED_ANALYSIS.md) for analysis specifics and [08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md) for consumer patterns.
