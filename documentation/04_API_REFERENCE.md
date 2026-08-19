# API Reference

Complete API documentation for all classes and functions.

## Module: src.engine

### AudioPipeline

Main orchestrator for the audio analysis pipeline.

```python
class AudioPipeline:
    def __init__(
        self,
        audio_source: AudioSource,
        num_processing_workers: int = 4,
        circular_buffer_capacity_s: float = 5.0,
        output_queue_maxsize: int = 10,
    ):
        """Initialize the pipeline.
        
        Args:
            audio_source: Audio source (LiveAudio, LocalFileAudio, custom)
            num_processing_workers: Number of parallel STFT workers
            circular_buffer_capacity_s: Size of shared buffer in seconds
            output_queue_maxsize: Max size of rendering queue
        """
    
    def start() -> None:
        """Start all worker threads."""
    
    def stop() -> None:
        """Stop all workers gracefully."""
    
    def get_frame() -> AudioFrame | None:
        """Get latest frame (events + signals)."""
    
    def is_running() -> bool:
        """Check if pipeline is active."""
    
    def join(timeout: float | None = None) -> None:
        """Wait for pipeline to stop."""
```

### CircularAudioBuffer

Thread-safe ring buffer for shared audio storage.

```python
class CircularAudioBuffer:
    def __init__(self, capacity_s: float = 5.0, sample_rate: int = 44100):
        """Initialize buffer.
        
        Args:
            capacity_s: Capacity in seconds
            sample_rate: Sample rate in Hz
        """
    
    def write(self, samples: np.ndarray) -> int:
        """Write audio samples with wrap-around.
        
        Args:
            samples: Audio data (n_samples, 2) in float32
            
        Returns:
            Number of samples written
        """
    
    def read_latest(self, duration_s: float, sample_rate: int) -> np.ndarray:
        """Read most recent samples.
        
        Args:
            duration_s: Duration to read in seconds
            sample_rate: Sample rate in Hz
            
        Returns:
            Audio samples (n_samples, 2) in float32
        """
```

### MultiWindowAudioAnalyzer

Three concurrent analysis windows (Fast/Medium/Slow) on same circular buffer.

```python
class MultiWindowAudioAnalyzer:
    def __init__(
        self,
        sample_rate: int = 44100,
        fast_window_ms: float = 10.0,
        medium_window_ms: float = 32.0,
        slow_window_ms: float = 250.0,
    ):
        """Initialize multi-window analyzer.
        
        Args:
            sample_rate: Sample rate in Hz
            fast_window_ms: Fast window size in milliseconds
            medium_window_ms: Medium window size
            slow_window_ms: Slow window size
        """
    
    def add_audio_chunk(self, audio: np.ndarray) -> None:
        """Add audio to circular buffer.
        
        Args:
            audio: Audio data (n_samples, 2) in float32
        """
    
    def analyze_all(self, timestamp_s: float) -> tuple[FastFeatures, MediumFeatures, SlowFeatures]:
        """Run all three analyzers on current buffer.
        
        Args:
            timestamp_s: Current timestamp
            
        Returns:
            Tuple of (FastFeatures, MediumFeatures, SlowFeatures)
        """
```

### FastAnalyzer

Fast tier analysis (5-10ms latency) for transient detection.

```python
class FastAnalyzer:
    def analyze(self, audio: np.ndarray, timestamp_s: float) -> FastFeatures:
        """Analyze audio chunk for transients.
        
        Args:
            audio: Audio samples (n_samples, 2)
            timestamp_s: Current timestamp
            
        Returns:
            FastFeatures with onset/transient detection
        """

@dataclass
class FastFeatures:
    timestamp_s: float
    raw_energy: float                   # 0-1 current amplitude
    onset_detected: bool                # Any rapid energy rise
    onset_strength: float               # 0-1 strength of onset
    is_percussive_peak: bool            # Kick/snare detected
    percussive_peak_strength: float     # 0-1 peak strength
```

### MediumAnalyzer

Medium tier analysis (20-50ms latency) for energy tracking.

```python
class MediumAnalyzer:
    def analyze(self, audio: np.ndarray, timestamp_s: float) -> MediumFeatures:
        """Analyze frequency bands and energy.
        
        Args:
            audio: Audio samples (n_samples, 2)
            timestamp_s: Current timestamp
            
        Returns:
            MediumFeatures with band energy and spectral info
        """

@dataclass
class MediumFeatures:
    timestamp_s: float
    bass_energy: float                  # 0-1 (20-250 Hz)
    mid_energy: float                   # 0-1 (250-4k Hz)
    high_energy: float                  # 0-1 (4k-20k Hz)
    spectral_centroid_hz: float | None  # Brightness in Hz
    spectral_brightness: float          # 0-1 normalized
    bass_energy_delta: float            # Change in bass energy
    overall_energy_delta: float         # Change in overall energy
```

### SlowAnalyzer

Slow tier analysis (100-500ms latency) for overall metrics.

```python
class SlowAnalyzer:
    def analyze(self, audio: np.ndarray, timestamp_s: float) -> SlowFeatures:
        """Analyze overall metrics and trends.
        
        Args:
            audio: Audio samples (n_samples, 2)
            timestamp_s: Current timestamp
            
        Returns:
            SlowFeatures with metrics and beat stability
        """

@dataclass
class SlowFeatures:
    timestamp_s: float
    average_energy: float               # 0-1 typical loudness
    energy_variance: float              # 0-1 how dynamic
    energy_trend: float                 # -1 to 1 (building/fading)
    spectral_density_low: float         # 0-1 (proportion in bass)
    spectral_density_mid: float         # 0-1
    spectral_density_high: float        # 0-1
    estimated_bpm: float | None         # Beats per minute
    beat_stability: float               # 0-1 tempo consistency
```

### BeatPredictor

Predicts next beat from tempo history.

```python
class BeatPredictor:
    def record_beat(self, timestamp_s: float, confidence: float = 1.0) -> None:
        """Record a detected beat.
        
        Args:
            timestamp_s: Beat timestamp
            confidence: Beat confidence (0-1)
        """
    
    def get_beat_phase(self, timestamp_s: float) -> tuple[float, float]:
        """Get current beat phase and confidence.
        
        Args:
            timestamp_s: Current timestamp
            
        Returns:
            Tuple of (beat_phase_0to1, confidence)
        """
    
    def predict_next_beat(self, timestamp_s: float) -> float | None:
        """Predict when next beat arrives.
        
        Args:
            timestamp_s: Current timestamp
            
        Returns:
            Predicted beat timestamp or None if insufficient history
        """
```

## Module: src.engine.events

### EventType

Enumeration of audio event types.

```python
class EventType(Enum):
    BEAT = "beat"
    KICK = "kick"
    SNARE = "snare"
    CYMBAL = "cymbal"
    PERCUSSION = "percussion"
    ONSET = "onset"
    TRANSIENT = "transient"
    ENERGY_SPIKE = "energy_spike"
    ENERGY_DROP = "energy_drop"
    SILENCE_STARTED = "silence_started"
    SILENCE_ENDED = "silence_ended"
    BASS_SURGE = "bass_surge"
    TREBLE_SURGE = "treble_surge"
```

### AudioEvent

Discrete point-in-time audio event.

```python
@dataclass
class AudioEvent:
    event_type: EventType
    timestamp_s: float
    strength: float = 1.0              # 0-1
    confidence: float = 1.0            # 0-1
    metadata: dict = field(default_factory=dict)
    
    # Methods
    def __str__(self) -> str:
        """Human-readable event description."""
```

### ContinuousSignals

Smooth time-varying audio signals.

```python
@dataclass
class ContinuousSignals:
    timestamp_s: float
    
    # Tier 1 (5-10ms)
    immediate_energy: float
    immediate_energy_derivative: float
    
    # Tier 2 (20-50ms)
    bass_energy: float
    mid_energy: float
    high_energy: float
    brightness: float
    spectral_centroid_hz: float | None
    spectral_density_bass: float
    spectral_density_mid: float
    spectral_density_high: float
    bass_energy_derivative: float
    overall_energy_derivative: float
    
    # Tier 3 (100-500ms)
    average_energy: float
    energy_variance: float
    energy_trend: float  # -1 to 1
    estimated_bpm: float | None
    beat_stability: float
    
    # Beat prediction (all tiers)
    beat_phase_0to1: float
    predicted_beat_timestamp_s: float | None
    prediction_confidence: float
```

### AudioFrame

Container combining events and signals at same timestamp.

```python
@dataclass
class AudioFrame:
    timestamp_s: float
    signals: ContinuousSignals
    events: list[AudioEvent] = field(default_factory=list)
    
    def __str__(self) -> str:
        """Summary of frame contents."""
```

### merge_frames()

Combine multiple frames intelligently.

```python
def merge_frames(*frames: AudioFrame) -> AudioFrame:
    """Merge multiple frames at nearby timestamps.
    
    Args:
        frames: AudioFrame objects to merge
        
    Returns:
        Single merged frame with averaged signals and combined events
        
    Note:
        - Signals are averaged
        - Events are combined into single list
        - Timestamp is averaged
    """
```

## Module: src.sources

### AudioSource (Base Class)

Abstract base class for audio sources.

```python
class AudioSource(ABC):
    @abstractmethod
    def read_chunk(self) -> np.ndarray:
        """Read audio chunk.
        
        Returns:
            Audio data (n_samples, 2) in float32
        """
    
    @property
    def sample_rate(self) -> int:
        """Sample rate in Hz."""
```

### LiveAudio

Capture from Stereo Mix (loopback) or USB device.

```python
class LiveAudio(AudioSource):
    def __init__(
        self,
        device_name: str | None = None,
        sample_rate: int = 44100,
        chunk_size: int = 2048,
    ):
        """Initialize live audio capture.
        
        Args:
            device_name: Audio device name or None for default
            sample_rate: Sample rate in Hz
            chunk_size: Samples per chunk
        """
```

### LocalFileAudio

Play WAV file and analyze.

```python
class LocalFileAudio(AudioSource):
    def __init__(
        self,
        file_path: str,
        sample_rate: int | None = None,
    ):
        """Initialize file playback.
        
        Args:
            file_path: Path to WAV file
            sample_rate: Resample to this rate (default: file rate)
        """
```

## Message Types

### AudioChunkMessage

Raw audio from capture worker.

```python
@dataclass
class AudioChunkMessage:
    samples: np.ndarray  # (n_samples, 2) float32
    sample_rate: int
```

### AudioFeaturesMessage

Features from processing worker.

```python
@dataclass
class AudioFeaturesMessage:
    timestamp_s: float
    overall_amplitude: float
    rms: float
    peak: float
    bass_energy: float
    mid_energy: float
    high_energy: float
    spectral_centroid_hz: float | None
    dominant_frequency_hz: float | None
    onset_detected: bool
    beat_detected: bool
    beat_confidence: float
    bpm: float | None
    band_bass_envelope: tuple[float, ...] | None
    band_mid_envelope: tuple[float, ...] | None
    band_high_envelope: tuple[float, ...] | None
```

### RenderingMessage

Normalized output with predictive sync (optional, for backward compat).

```python
@dataclass
class RenderingMessage:
    timestamp_s: float
    bass: float
    energy: float
    brightness: float
    impact: float
    beat: bool
    beat_confidence: float
    onset: bool
    tempo_bpm: float | None
    dynamics: float
    beat_phase_0to1: float
    predicted_beat_timestamp_s: float | None
    prediction_confidence: float
```

## Utility Functions

### combine_features()

Combine tiered features into rendering message.

```python
def combine_features(
    fast: FastFeatures,
    medium: MediumFeatures,
    slow: SlowFeatures,
    beat_phase: float,
    predicted_beat: float | None,
    prediction_confidence: float,
) -> TieredRenderingMessage:
    """Combine tiered features into single message.
    
    Args:
        fast: Fast analysis result
        medium: Medium analysis result
        slow: Slow analysis result
        beat_phase: Current beat phase (0-1)
        predicted_beat: Predicted next beat timestamp
        prediction_confidence: Confidence in prediction (0-1)
        
    Returns:
        TieredRenderingMessage ready for rendering
    """
```

## Constants

### Frequency Bands
```python
BAND_BASS_MIN_HZ = 20
BAND_BASS_MAX_HZ = 250

BAND_MID_MIN_HZ = 250
BAND_MID_MAX_HZ = 4000

BAND_HIGH_MIN_HZ = 4000
BAND_HIGH_MAX_HZ = 20000
```

### Analysis Windows
```python
FAST_WINDOW_MS = 10.0      # 5-10ms latency
MEDIUM_WINDOW_MS = 32.0    # 20-50ms latency
SLOW_WINDOW_MS = 250.0     # 100-500ms latency
```

### Circular Buffer
```python
BUFFER_CAPACITY_S = 5.0    # 5 second buffer
BUFFER_SAMPLE_RATE = 44100 # Hz
```

### Processing
```python
STFT_N_FFT = 2048
STFT_HOP_LENGTH = 512
STFT_WINDOW = "hann"
NUM_PROCESSING_WORKERS = 4
```

## Error Handling

### Common Exceptions

**ValueError**: Invalid parameter values
```python
try:
    signals = ContinuousSignals(
        timestamp_s=10.5,
        bass_energy=1.5,  # Invalid! Must be 0-1
        # ...
    )
except ValueError as e:
    print(f"Invalid signal value: {e}")
```

**RuntimeError**: Pipeline errors
```python
try:
    pipeline.start()
except RuntimeError as e:
    print(f"Pipeline error: {e}")
```

**IndexError**: Insufficient audio history
```python
if not predictor.predict_next_beat(timestamp):
    print("Insufficient beat history for prediction")
```

## Type Hints

All functions use type hints for IDE support:

```python
# Audio processing
def process_audio(frame: AudioFrame) -> None: ...

# Event handling
def on_event(event: AudioEvent) -> None: ...

# Signal animation
def animate(signals: ContinuousSignals) -> None: ...

# Batch operations
def process_frames(frames: list[AudioFrame]) -> None: ...
```

## Imports

Common import patterns:

```python
# Core classes
from src.engine import (
    AudioPipeline,
    CircularAudioBuffer,
    MultiWindowAudioAnalyzer,
)

# Analysis
from src.engine import (
    FastAnalyzer,
    MediumAnalyzer,
    SlowAnalyzer,
    BeatPredictor,
)

# Events and signals
from src.engine import (
    EventType,
    AudioEvent,
    ContinuousSignals,
    AudioFrame,
)

# Sources
from src.sources import (
    AudioSource,
    LiveAudio,
    LocalFileAudio,
)

# Messages
from src.engine import (
    AudioChunkMessage,
    AudioFeaturesMessage,
    RenderingMessage,
)
```

## Performance Tips

- **FastAnalyzer**: 5-10ms, use for immediate effects
- **MediumAnalyzer**: 20-50ms, use for smooth tracking
- **SlowAnalyzer**: 100-500ms, use for scene changes
- **Events**: Sparse, cheap to broadcast
- **Signals**: Dense, sample once per frame
- **Beat Prediction**: Eliminates 100-150ms latency

See [02_ARCHITECTURE.md](02_ARCHITECTURE.md) for performance benchmarks.
