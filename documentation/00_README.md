# moshpro-spout-obs-glue-script Documentation

Complete documentation for the real-time audio analysis engine with multi-threaded architecture, multi-window tiered analysis, and predictive beat synchronization.

## 📚 Documentation Structure

### Getting Started
- **[01_QUICK_START.md](01_QUICK_START.md)** - Installation, basic usage, first program in 10 minutes
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Cheat sheet for common patterns

### Core Architecture
- **[02_ARCHITECTURE.md](02_ARCHITECTURE.md)** - Complete system architecture, data flow, threading model
- **[03_EVENTS_VS_SIGNALS.md](03_EVENTS_VS_SIGNALS.md)** - Separation of discrete events from continuous signals
- **[04_API_REFERENCE.md](04_API_REFERENCE.md)** - Complete API documentation for all classes and functions

### Audio Analysis
- **[05_FEATURE_EXTRACTION.md](05_FEATURE_EXTRACTION.md)** - Audio features extracted (amplitude, spectrum, onset, tempo)
- **[06_TIERED_ANALYSIS.md](06_TIERED_ANALYSIS.md)** - Multi-window tiered analysis (Fast/Medium/Slow)
- **[07_BEAT_PREDICTION.md](07_BEAT_PREDICTION.md)** - Predictive beat synchronization for zero-latency effects

### Integration
- **[08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md)** - How to integrate with games, visualizers, other apps
- **[EXAMPLES.md](EXAMPLES.md)** - Complete working examples for common use cases

## 🚀 Quick Start

### Installation
```bash
pip install -r requirements.txt
```

### Basic Usage
```python
from src.engine import AudioPipeline
from src.sources import LocalFileAudio

# Create pipeline
pipeline = AudioPipeline(audio_source=LocalFileAudio("song.wav"))
pipeline.start()

# Get frames
while pipeline.is_running():
    frame = pipeline.get_frame()
    if frame:
        # Handle events
        for event in frame.events:
            print(f"Event: {event.event_type.value}")
        
        # Animate with signals
        scale = 1.0 + frame.signals.bass_energy * 0.3
```

See [01_QUICK_START.md](01_QUICK_START.md) for detailed setup.

## 🏗️ Architecture Overview

### Multi-Threaded Pipeline
```
Audio Source
    ↓
[AudioCaptureWorker] → (5-second circular buffer)
    ↓
[AudioProcessingWorker × 4] → (STFT, spectral features)
    ↓
[AnalysisWorker] → (event detection, beat prediction)
    ↓
[RenderingWorker] → (output to game/UI)
```

### Three-Tier Analysis
**Single circular buffer shared by all analyzers:**
- **Fast Tier (5-10ms)**: Kick/snare/transient detection
- **Medium Tier (20-50ms)**: Energy bands, spectral changes
- **Slow Tier (100-500ms)**: Overall metrics, tempo, palette

### Clean Data Separation
- **Events**: Discrete point-in-time (beat, kick, snare, onset)
- **Signals**: Continuous smooth values (bass 0.85, brightness 0.72)

See [02_ARCHITECTURE.md](02_ARCHITECTURE.md) for detailed diagrams.

## 🎯 Key Features

### ✓ Real-Time Multi-Threaded
- Concurrent audio capture, processing, analysis, rendering
- Queue-based communication prevents thread coupling
- ~5-10% CPU overhead

### ✓ Multi-Window Tiered Analysis
- Three analysis windows at different latencies
- Single shared circular buffer (100KB memory)
- Efficient CPU usage vs. separate pipelines

### ✓ Predictive Beat Synchronization
- Estimate next beat from tempo history
- Know beat is arriving before audio plays
- Eliminates 100-150ms reactive latency

### ✓ Rich Audio Features
- Amplitude: RMS, peak, overall
- Spectral: bass/mid/high energy, centroid, brightness
- Temporal: onset detection, beat confidence, tempo
- Spectral density: energy distribution per band

### ✓ Events vs Signals Separation
- **Events**: Trigger callbacks, discrete occurrences (14 types)
- **Signals**: Smooth animation, continuous values (25 fields)
- Different handling patterns for different use cases

### ✓ Flexible Audio Sources
- Loopback audio (Stereo Mix)
- USB audio input
- File playback
- Custom audio sources

## 📖 Documentation by Task

### I want to...

**...get started quickly**
→ [01_QUICK_START.md](01_QUICK_START.md)

**...understand the architecture**
→ [02_ARCHITECTURE.md](02_ARCHITECTURE.md)

**...use events and signals**
→ [03_EVENTS_VS_SIGNALS.md](03_EVENTS_VS_SIGNALS.md)

**...see what audio features are available**
→ [05_FEATURE_EXTRACTION.md](05_FEATURE_EXTRACTION.md)

**...synchronize to beat with zero latency**
→ [07_BEAT_PREDICTION.md](07_BEAT_PREDICTION.md)

**...integrate with my game/app**
→ [08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md)

**...see working code examples**
→ [EXAMPLES.md](EXAMPLES.md)

**...find API documentation**
→ [04_API_REFERENCE.md](04_API_REFERENCE.md)

**...use quick reference/cheat sheet**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

## 🔧 Project Structure

```
moshpro-spout-obs-glue-script/
├── README.md                          # Main project readme
├── requirements.txt                   # Python dependencies
├── documentation/                     # This documentation
│   ├── 00_README.md
│   ├── 01_QUICK_START.md
│   ├── 02_ARCHITECTURE.md
│   ├── 03_EVENTS_VS_SIGNALS.md
│   ├── 04_API_REFERENCE.md
│   ├── 05_FEATURE_EXTRACTION.md
│   ├── 06_TIERED_ANALYSIS.md
│   ├── 07_BEAT_PREDICTION.md
│   ├── 08_INTEGRATION_GUIDE.md
│   ├── QUICK_REFERENCE.md
│   └── EXAMPLES.md
├── src/
│   ├── engine/                        # Core audio engine
│   │   ├── workers.py                 # Worker threads
│   │   ├── events.py                  # Event types & continuous signals
│   │   ├── multi_window_analyzer.py   # Three-tier analysis
│   │   ├── tiered_rendering.py        # Rendering format
│   │   ├── pipeline.py                # Pipeline orchestrator
│   │   └── __init__.py                # Engine exports
│   ├── sources/                       # Audio source implementations
│   │   ├── audio_source.py            # Base class
│   │   ├── live_audio.py              # Loopback/USB
│   │   ├── track_audio.py             # File playback
│   │   └── ...
│   ├── analysis/                      # Analysis utilities
│   │   └── audio_analyzer.py
│   ├── models/                        # Data models
│   ├── gui/                           # GUI components
│   └── ...
├── tests/                             # Test suite
├── submodules/
│   ├── rekordbox-databridge/          # DJ software integration
│   └── ...
└── ...
```

## 🎓 Learning Path

1. **Beginner**: Start with [01_QUICK_START.md](01_QUICK_START.md) to get code running
2. **Intermediate**: Read [02_ARCHITECTURE.md](02_ARCHITECTURE.md) to understand design
3. **Advanced**: Explore [03_EVENTS_VS_SIGNALS.md](03_EVENTS_VS_SIGNALS.md) and [06_TIERED_ANALYSIS.md](06_TIERED_ANALYSIS.md)
4. **Expert**: Study [04_API_REFERENCE.md](04_API_REFERENCE.md) and source code in `src/engine/` and `src/analysis/`

## 📊 Performance

| Aspect | Value |
|--------|-------|
| CPU Usage | 5-10% (vs 15-30% for separate pipelines) |
| Memory | ~100KB (vs 22MB for 5-second buffer approach) |
| Latency: Fast tier | 5-10ms |
| Latency: Medium tier | 20-50ms |
| Latency: Slow tier | 100-500ms |
| Predictive beat latency | -50ms (ahead of audio) |

## 🔗 Links

- **Source Code**: `src/engine/` (core), `src/analysis/` (analysis), `src/sources/` (inputs)
- **Examples**: `examples/` - Various example scripts
- **Tests**: `tests/` - Test suite
- **Main Project**: Root directory

## 💡 Tips

- Start with [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for copy-paste patterns
- Check [EXAMPLES.md](EXAMPLES.md) for working code you can adapt
- Read [03_EVENTS_VS_SIGNALS.md](03_EVENTS_VS_SIGNALS.md) first if integrating with existing code
- Profile your use case with the performance metrics in [02_ARCHITECTURE.md](02_ARCHITECTURE.md)

## 🐛 Troubleshooting

Common issues and solutions are documented in each guide. See:
- [01_QUICK_START.md](01_QUICK_START.md) - Installation issues
- [02_ARCHITECTURE.md](02_ARCHITECTURE.md) - Design questions
- [08_INTEGRATION_GUIDE.md](08_INTEGRATION_GUIDE.md) - Integration problems

## 📝 License & Attribution

This project integrates with [rekordbox-databridge](../submodules/rekordbox-databridge) for DJ software integration.

---

**Last Updated**: 2026-08-18  
**Version**: 1.0  
**Status**: Production Ready
