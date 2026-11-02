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
  thread. A hop costs about 0.15 ms, around 3% of real time.
- **Beat tracking**: a phase-locked loop running at the consensus BPM. Each
  kick's attack is located inside the hop (to about 1 ms) and corrects both
  the beat phase and a small tempo offset, so a slightly-off BPM estimate
  doesn't leave a lag. Beats come from the prediction, not the detection:
  each one is emitted ahead of time by the measured age of the audio
  (device buffering + analysis), plus `MOSHPRO_BEAT_LEAD_S`, and carries its
  exact predicted time. The tracker keeps going through short breakdowns.
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
| `fast` | every hop | `onset_detected`, `onset_strength`, `is_percussive_peak` (kick), `raw_energy`, `beat_detected`, `beat_phase`, `beat_confidence`, `tempo_bpm`, `predicted_next_beat_s`, `predicted_next_beat_unix_s`, `audio_age_s` |
| `medium` | every hop | `bass_energy`, `mid_energy`, `high_energy` (0-1, relative to the band's recent peak), deltas, `custom_energy` (a band you pick: `pipeline.set_custom_band(40, 120)` or the GUI sliders) |
| `slow` | on each job result | levels, `spectral_density_*`, `energy_trend`, `detected_key`, `key_confidence`, `estimated_bpm`, `beat_stability`, band envelopes |
| `bpm_estimates` | every ~1 s | per-method BPM + confidence, plus the octave-aware consensus |

Timestamps are stream time in seconds (sample count / sample rate). For live
devices, `predicted_next_beat_unix_s` (and `time_unix` on beat events) give
the beat as a Unix time, so other local processes, e.g. an OBS browser source
using `Date.now() / 1000`, can schedule on it.

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

`MOSHPRO_LATENCY_PROFILE` (`balanced`, `low`, `ultra`,
`crazy_ultra_amazing_waw`) trades CPU for latency in one setting: smaller
device buffers, finer analysis steps, faster job, GUI and API refresh, WASAPI
exclusive mode, and for the last one high priority audio threads. Measured
audio age at analysis: 20 ms (`balanced`), 6.6 ms (`ultra`), 4.4 ms
(`crazy_ultra_amazing_waw`); details in
[09](documentation/09_CONFIGURATION_AND_DIAGNOSTICS.md#latency-profiles).

`MOSHPRO_BEAT_LEAD_S` emits beats earlier to cover latency the engine can't
measure: upstream (a virtual cable's buffer, mixer → interface) and downstream
(OBS, video pipeline, projector). The loopback test below suggests a value for
the upstream part.

## Tests and diagnostics

```bash
python -m pytest -q                      # synthetic audio, no files or devices needed
                                         # pipeline.stats(): live load, backlog, overflows, job times
python -m src.diagnostics.worker_debug   # real-time health check on a local file

# Real hardware: play a known 128 BPM / C major signal into an output and
# analyze it live from an input (virtual cable or line out -> line in).
# Nothing is recorded; prints driver overflows, backlog, accuracy and
# wall-clock event timing, and suggests a MOSHPRO_BEAT_LEAD_S value.
python -m src.diagnostics.loopback_test --out "CABLE Input" --in "CABLE Output"
```

Measured through VB-Audio Virtual Cable (WASAPI, 48 kHz, 512-sample blocks):
0 overflows and 0 skipped hops; BPM and key correct, with the first estimates
2.5 s and 3.4 s after playback starts; kick timing ±1–2 ms; beats within
±3 ms of the kicks; audio about 24 ms old when analyzed. With the suggested
lead, beat events arrive within a few ms of the kick reaching the output.

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

## Documentation

Detailed guides are in [documentation/](documentation/00_README.md):
architecture, events vs. signals, API reference, analysis methods, beat
tracking and latency, integration (OBS / browser / Python), the GUI, and
configuration and diagnostics.
