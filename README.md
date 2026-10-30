# MoshPro Spout OBS Glue Script

Real-time audio analysis for audio-reactive visuals and lighting. It captures a
live input (mixer, USB interface, or a running application's output), analyzes
it, and serves the results to the GUI and to other local apps (OBS browser
sources, lighting controllers, scripts) over HTTP and WebSocket.

## Quick start

```bash
pip install -r requirements.txt
python -m src.gui.main_gui
```

Pick an audio input, press **Start**, and optionally enable the local API.

## Using the engine from code

```python
import time
from src.engine import AudioPipeline
from src.sources import AudioInputSource

source = AudioInputSource(device=3, sample_rate=48000)   # see list_devices.py
pipeline = AudioPipeline(
    audio_source=lambda: source,
    sample_rate=48000,                                    # must match the source
    event_callback=lambda kind, data: print(kind, data),  # "onset" / "beat", real-time thread
).start()

try:
    while True:
        fast, medium, slow = pipeline.feature_cache.get_all()
        if fast:
            print(f"bass={medium.bass_energy:.2f} phase={fast.beat_phase:.2f} "
                  f"bpm={slow.estimated_bpm if slow else None}")
        time.sleep(0.05)
finally:
    pipeline.stop()
    pipeline.wait()
```

Any iterable of `src.sources.AudioChunk` works as a source; see
`examples/example.py` for a file source.

## Architecture

```
 audio device ──► AudioCaptureWorker ──► RingBuffer (mono, absolute sample index)
                  (mono mix, 20 Hz HPF)      │
                    ┌────────────────────────┴───────────────────────┐
                    ▼                                                ▼
        RealtimeWorker — every hop (~6 ms)               JobScheduler — latest-wins
        onsets, kicks, band levels,                      dynamics     thread   every 0.25 s, 2 s window
        beat tracker ◄──── consensus tempo ───────────── BPM (numpy)  process  every 1 s,    8 s window
                    │                                    BPM (librosa) process every 1 s,    8 s window
                    │                                    key          process  every 2 s,    8 s window
                    ▼                                                │
                    └───────────────► FeatureCache ◄─────────────────┘
                                          │
                          GUI (polls, 20 Hz)   Local API (push, ≤ 60 Hz)
```

- **One writer, one ring buffer.** The capture thread is the only writer.
  Every reader asks for an exact span by absolute sample index, so analyses
  can use any window length, independent of the device block size.
- **Real-time path** (`src/engine/realtime.py`): sequential and stateful
  (spectral flux, adaptive thresholds, beat phase), so it runs in exactly one
  thread. It costs well under a millisecond per hop.
- **Beat tracking**: a phase-locked loop running at the consensus BPM and
  nudged by detected kicks. Beats are emitted when the predicted beat time
  arrives, so they don't carry detection latency, and the tracker keeps
  going through short breakdowns.
- **Background jobs** (`src/engine/scheduler.py`): each job declares its
  cadence, window and executor. If a job is still running, the next tick is
  skipped, never queued. Heavy jobs run in app-wide worker processes, which
  the GUI warms up at launch: librosa takes several seconds to load in a
  fresh process, so it gets its own pool.
- **FeatureCache** (`src/engine/pipeline.py`) is the only thing consumers
  read. Tk widgets are updated only from the Tk thread.

## Outputs

| Group | Updated | Fields (highlights) |
|---|---|---|
| `fast` | every hop | `onset_detected`, `onset_strength`, `is_percussive_peak` (kick), `raw_energy`, `beat_detected`, `beat_phase`, `beat_confidence`, `tempo_bpm`, `predicted_next_beat_s` |
| `medium` | every hop | `bass_energy`, `mid_energy`, `high_energy` (0-1, relative to the band's recent peak), deltas |
| `slow` | on each job result | levels, `spectral_density_*`, `energy_trend`, `detected_key`, `key_confidence`, `estimated_bpm`, `beat_stability`, band envelopes |
| `bpm_estimates` | every ~1 s | per-method BPM + confidence, plus the octave-aware consensus |

Timestamps are stream time in seconds (sample count / sample rate).

## Local API

Bound to `127.0.0.1:8768` by default (`MOSHPRO_API_HOST`, `MOSHPRO_API_PORT`).

- `GET /health`
- `GET /features`, `/features/fast`, `/features/medium`, `/features/slow`, `/features/bpm`
- `WS /ws`: sends a snapshot on connect, then whenever the data changes
  (at most `MOSHPRO_API_MAX_PUSH_HZ` per second, default 60)

## Configuration

All settings live in `src/config/settings.py` and can be overridden with
`MOSHPRO_*` environment variables, e.g. block and hop sizes, job intervals and
windows (`MOSHPRO_BPM_INTERVAL_S`, `MOSHPRO_KEY_WINDOW_S`, …), and
`MOSHPRO_JOBS_USE_PROCESSES=false` to run every job in threads.

## Tests and diagnostics

```bash
python -m pytest -q                      # synthetic audio, no files or devices needed
python -m src.diagnostics.worker_debug   # real-time health check on a local file
```

## Project layout

```
src/
  engine/      pipeline, ring buffer, capture, real-time path, job scheduler
  analysis/    BPM detectors, key detection, dynamics, feature dataclasses
  sources/     sounddevice input/loopback sources, track file source
  api/         local HTTP + WebSocket server
  gui/         Tkinter application
tests/         pytest suite (synthetic audio helpers in tests/synthetic.py)
```

> The long-form guides in `documentation/` and `docs/` describe an earlier
> version of the engine (e.g. `LiveAudio`, `pipeline.get_frame()`) and are
> out of date; this README reflects the current code.
