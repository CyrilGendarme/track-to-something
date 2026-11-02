# Configuration and diagnostics

## Settings

All settings are in `src/config/settings.py`. Each one can be overridden with
an environment variable of the same name prefixed with `MOSHPRO_` (e.g.
`BPM_INTERVAL_S` → `MOSHPRO_BPM_INTERVAL_S`).

| Variable | Default | Effect |
|---|---|---|
| `MOSHPRO_SAMPLE_RATE` | 44100 | default sample rate when none is given |
| `MOSHPRO_BLOCK_SIZE` | 512 | device block size; bounds capture latency (512 @ 48 kHz = 10.7 ms) |
| `MOSHPRO_APPLY_HPF` | true | 20 Hz high-pass on capture |
| `MOSHPRO_BIT_DEPTH` | 16 | quantize capture below 16 bits (off by default) |
| `MOSHPRO_BUFFER_CAPACITY_SECONDS` | 12 | minimum ring buffer size |
| `MOSHPRO_REALTIME_HOP_SIZE` | 256 | real-time hop (analysis rate) |
| `MOSHPRO_REALTIME_FFT_SIZE` | 1024 | real-time analysis frame |
| `MOSHPRO_ONSET_THRESHOLD_K` | 2.0 | onset sensitivity (lower = more onsets) |
| `MOSHPRO_ONSET_MIN_INTERVAL_S` / `MOSHPRO_KICK_MIN_INTERVAL_S` | 0.08 / 0.2 | refractory periods |
| `MOSHPRO_SILENCE_RMS` | 0.001 | below this (≈ −60 dBFS), no onsets |
| `MOSHPRO_BEAT_LEAD_S` | 0.0 | extra beat lead for latency outside the engine ([06](06_BEAT_TRACKING_AND_LATENCY.md)) |
| `MOSHPRO_DYNAMICS_INTERVAL_S` / `MOSHPRO_DYNAMICS_WINDOW_S` | 0.25 / 2.0 | dynamics job |
| `MOSHPRO_BPM_INTERVAL_S` / `MOSHPRO_BPM_WINDOW_S` | 1.0 / 8.0 | BPM jobs |
| `MOSHPRO_KEY_INTERVAL_S` / `MOSHPRO_KEY_WINDOW_S` | 2.0 / 8.0 | key job |
| `MOSHPRO_KEY_HISTORY_SIZE` | 4 | key smoothing (estimates) |
| `MOSHPRO_JOBS_USE_PROCESSES` | true | false runs every job in threads (debugging) |
| `MOSHPRO_API_HOST` / `MOSHPRO_API_PORT` | 127.0.0.1 / 8768 | local API bind address |
| `MOSHPRO_API_MAX_PUSH_HZ` | 60 | WebSocket push rate cap |

## Tests

```bash
python -m pytest -q
```

The suite takes about 45 s and needs no audio files or devices. It uses
synthetic tracks with a known BPM and key (`src/diagnostics/signals.py`) and
covers:

- ring buffer and capture clock;
- onset, kick and attack localization;
- beat tracker phase and tempo correction, flywheel and lookahead;
- the scheduler's latest-wins behaviour;
- all 24 keys and cadences;
- BPM detectors and the consensus;
- the API;
- end-to-end runs in thread and process mode.

## Diagnostics

**Real hardware loopback** — `python -m src.diagnostics.loopback_test`.
It plays a known 128 BPM / C major signal to an output, and analyzes it live
from an input with the production setup (warm process pools, device thread).
Nothing is recorded. It reports:

- driver overflows, hops skipped and the real-time backlog;
- per-job runs, skips and compute time;
- BPM, key and kick detection versus the ground truth, and time to the
  first result;
- kick and beat precision in stream time;
- wall-clock event timing, plus a suggested `MOSHPRO_BEAT_LEAD_S`.

```bash
python -m src.diagnostics.loopback_test --out "CABLE Input" --in "CABLE Output"
python -m src.diagnostics.loopback_test --out 14 --in 17 --seconds 30 --lead 0.055
```

Use a virtual cable (VB-Audio) or a physical line-out → line-in loop. The
output and input default sample rates must match.

**File at real-time pace** — `python -m src.diagnostics.worker_debug`.
It feeds a local file (from `tests/settings.py`) at real-time pace and prints
thread liveness, hop counters and job statistics once per second.

**Live health** — `pipeline.stats()` (also shown in the GUI's Performance
panel) gives the real-time load, backlog, audio age, driver overflows and
per-job compute times at any moment.

**Devices** — `python list_devices.py`.

**Tests** — `python -m pytest -q` runs `tests/` only (see `pytest.ini`); the
`test_*.py` scripts at the repo root are manual tools that open the GUI,
list devices or connect to a running API. If a test stalls for 120 s,
pytest dumps every thread's stack.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Unanticipated host error" when starting | WASAPI stream opened without COM on the thread; fixed in `SoundDeviceSource`. If it persists, the device is held exclusively by another app |
| `ValueError: Source sample rate … does not match` | pass the device's sample rate to `AudioPipeline` |
| BPM/key slow to appear | worker processes still warming (librosa takes seconds to load on first use); call `prewarm_job_processes()` early |
| `hops_skipped` > 0, a large `max_backlog_s` or a high `load` | the real-time thread is starved of CPU; close heavy apps or raise `MOSHPRO_REALTIME_HOP_SIZE` |
| `overflows` > 0 | the driver dropped input; raise `MOSHPRO_BLOCK_SIZE` |
| Beats consistently early or late | tune `MOSHPRO_BEAT_LEAD_S` ([06](06_BEAT_TRACKING_AND_LATENCY.md)) |
| Key flips between relative major/minor | expected on ambiguous material; check `key_confidence` |
