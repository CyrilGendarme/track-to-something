# MoshPro Spout OBS Glue Script

Real-time audio analysis engine for audio-reactive visualizations, games, and effects.

## Quick Start

**New here?** Start here: [documentation/01_QUICK_START.md](documentation/01_QUICK_START.md) (10 minutes to first program)

## Documentation

All documentation is in the [documentation/](documentation/) folder:

### Learning Path
- **[00_README.md](documentation/00_README.md)** - Overview & navigation
- **[01_QUICK_START.md](documentation/01_QUICK_START.md)** - Getting started (10 min)
- **[02_ARCHITECTURE.md](documentation/02_ARCHITECTURE.md)** - How it works
- **[03_EVENTS_VS_SIGNALS.md](documentation/03_EVENTS_VS_SIGNALS.md)** - Core pattern

### Reference
- **[04_API_REFERENCE.md](documentation/04_API_REFERENCE.md)** - Complete API docs
- **[10_QUICK_REFERENCE.md](documentation/10_QUICK_REFERENCE.md)** - Cheat sheet

### Detailed Guides
- **[05_FEATURE_EXTRACTION.md](documentation/05_FEATURE_EXTRACTION.md)** - Audio features explained
- **[06_TIERED_ANALYSIS.md](documentation/06_TIERED_ANALYSIS.md)** - Multi-window analysis
- **[07_BEAT_PREDICTION.md](documentation/07_BEAT_PREDICTION.md)** - Zero-latency beat sync
- **[08_INTEGRATION_GUIDE.md](documentation/08_INTEGRATION_GUIDE.md)** - Framework integration
- **[09_EXAMPLES.md](documentation/09_EXAMPLES.md)** - 9 working code examples

## Features

- **Three-tier analysis** (5-10ms / 20-50ms / 100-500ms latency)
- **Event detection** (beats, kicks, snares, onsets, spectral surges)
- **Continuous signals** (25 normalized audio features)
- **Beat prediction** (-50ms latency for zero-lag sync)
- **Efficient** (5-10% CPU, 100KB memory)
- **Thread-safe** (async-ready)

## Installation

```bash
pip install -r requirements.txt
```

## Basic Usage

```python
from src.sources import LiveAudio
from src.engine import AudioPipeline

# Create and start pipeline
pipeline = AudioPipeline(LiveAudio()).start()

# Main loop
while True:
    frame = pipeline.get_frame()
    if frame:
        print(f"Bass: {frame.signals.bass_energy:.2f}")
```

See [documentation/01_QUICK_START.md](documentation/01_QUICK_START.md) for full setup guide.

## Project Structure

```
src/
  engine/               # Core pipeline orchestration
    pipeline.py        # Main AudioPipeline orchestrator
    workers.py         # Worker thread implementations
    events.py          # Event and signal type definitions
    tiered_rendering.py
    __init__.py
  
  analysis/             # Audio analysis and feature extraction
    multi_window_analyzer.py  # FastAnalyzer, MediumAnalyzer, SlowAnalyzer
    audio_analyzer.py
    __init__.py
  
  sources/              # Audio input sources
    live_audio.py
    track_audio.py
    audio_source.py
  
  models/               # Data models
    rekordbox.py
  
  gui/                  # GUI/UI components

examples/              # Working code examples
  events_vs_signals_example.py
  predictive_demo.py
  tiered_analysis_example.py
  ...

documentation/         # Complete guides (start here!)
  00_README.md
  01_QUICK_START.md
  02_ARCHITECTURE.md
  ...

tests/                 # Validation tests
  test_events_signals.py
  test_audio_sources_analysis.py
  ...
requirements.txt
```

## Examples

See [documentation/09_EXAMPLES.md](documentation/09_EXAMPLES.md) for:
- Audio visualization
- Beat detection
- Real-time waveform monitoring
- Game integration
- OSC streaming to OBS

## Architecture

The engine is built on:
- **Circular buffer** (5 seconds, shared between tiers)
- **Three parallel analyzers** (Fast/Medium/Slow windows)
- **Thread-safe queues** (async-ready)
- **Events + signals** (clean separation of concerns)

See [documentation/02_ARCHITECTURE.md](documentation/02_ARCHITECTURE.md) for full details.

## Requirements

- Python 3.13+
- NumPy, SciPy, Librosa
- Platform-specific audio APIs (Windows: PyAudio, Linux: PulseAudio)

See [requirements.txt](requirements.txt) for dependencies.

## License

See project license file.

---

**Start learning:** [documentation/01_QUICK_START.md](documentation/01_QUICK_START.md)  
**API reference:** [documentation/04_API_REFERENCE.md](documentation/04_API_REFERENCE.md)  
**Examples:** [documentation/09_EXAMPLES.md](documentation/09_EXAMPLES.md)