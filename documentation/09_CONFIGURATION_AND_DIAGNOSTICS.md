# Configuration and diagnostics

## Settings

All settings are in `src/config/settings.py`. Each one can be overridden with
an environment variable of the same name prefixed with `MOSHPRO_` (e.g.
`BPM_INTERVAL_S` → `MOSHPRO_BPM_INTERVAL_S`).

Defaults marked † come from the latency profile (see below).

| Variable | Default | Effect |
|---|---|---|
| `MOSHPRO_LATENCY_PROFILE` | balanced | `balanced`, `low` or `ultra`; see [Latency profiles](#latency-profiles) |
| `MOSHPRO_SAMPLE_RATE` | 44100 | default sample rate when none is given |
| `MOSHPRO_BLOCK_SIZE` | 512 † | device block size; bounds capture latency (512 @ 48 kHz = 10.7 ms) |
| `MOSHPRO_DEVICE_LATENCY` | high † | driver buffering: `low`, `high` or seconds |
| `MOSHPRO_WASAPI_EXCLUSIVE` | false † | WASAPI exclusive mode (falls back to shared if refused) |
| `MOSHPRO_APPLY_HPF` | true | 20 Hz high-pass on capture |
| `MOSHPRO_BIT_DEPTH` | 16 | quantize capture below 16 bits (off by default) |
| `MOSHPRO_BUFFER_CAPACITY_SECONDS` | 12 | minimum ring buffer size |
| `MOSHPRO_REALTIME_HOP_SIZE` | 256 † | real-time hop (analysis rate) |
| `MOSHPRO_REALTIME_FFT_SIZE` | 1024 | real-time analysis frame |
| `MOSHPRO_ONSET_THRESHOLD_K` | 2.0 † | onset sensitivity (lower = more onsets) |
| `MOSHPRO_KICK_THRESHOLD_K` | 2.0 | kick sensitivity (lower = more kicks) |
| `MOSHPRO_ONSET_MIN_INTERVAL_S` / `MOSHPRO_KICK_MIN_INTERVAL_S` | 0.08 / 0.2 | refractory periods |
| `MOSHPRO_SILENCE_RMS` | 0.001 | below this (≈ −60 dBFS), no onsets |
| `MOSHPRO_BEAT_LEAD_S` | 0.0 | extra beat lead for latency outside the engine ([06](06_BEAT_TRACKING_AND_LATENCY.md)) |
| `MOSHPRO_DYNAMICS_INTERVAL_S` / `MOSHPRO_DYNAMICS_WINDOW_S` | 0.25 † / 2.0 | dynamics job |
| `MOSHPRO_BPM_INTERVAL_S` / `MOSHPRO_BPM_WINDOW_S` | 1.0 † / 8.0 | BPM jobs |
| `MOSHPRO_KEY_INTERVAL_S` / `MOSHPRO_KEY_WINDOW_S` | 2.0 † / 8.0 | key job |
| `MOSHPRO_SCHEDULER_TICK_S` | 0.02 † | how often the scheduler checks for due jobs |
| `MOSHPRO_KEY_HISTORY_SIZE` | 4 | key smoothing (estimates) |
| `MOSHPRO_JOBS_USE_PROCESSES` | true | false runs every job in threads (debugging) |
| `MOSHPRO_API_HOST` / `MOSHPRO_API_PORT` | 127.0.0.1 / 8768 | local API bind address |
| `MOSHPRO_API_MAX_PUSH_HZ` | 60 † | WebSocket push rate cap |
| `MOSHPRO_GUI_REFRESH_MS` | 50 † | GUI metrics refresh period |

## Latency profiles

`MOSHPRO_LATENCY_PROFILE` trades CPU for latency in one setting. It only
changes defaults: any variable in the table below still overrides it.

```powershell
$env:MOSHPRO_LATENCY_PROFILE = "low"     # PowerShell; in cmd: set MOSHPRO_LATENCY_PROFILE=low
python -m src.gui.main_gui
```

| Setting | `balanced` (default) | `low` | `ultra` |
|---|---|---|---|
| `MOSHPRO_BLOCK_SIZE` (device block) | 512 | 256 | 128 |
| `MOSHPRO_DEVICE_LATENCY` (driver buffering) | high | low | low |
| `MOSHPRO_WASAPI_EXCLUSIVE` | false | false | true |
| `MOSHPRO_REALTIME_HOP_SIZE` | 256 | 128 | 64 |
| `MOSHPRO_ONSET_THRESHOLD_K` | 2.0 | 2.3 | 2.5 |
| `MOSHPRO_DYNAMICS_INTERVAL_S` | 0.25 | 0.1 | 0.05 |
| `MOSHPRO_BPM_INTERVAL_S` / `MOSHPRO_KEY_INTERVAL_S` | 1.0 / 2.0 | 0.5 / 1.0 | 0.5 / 1.0 |
| `MOSHPRO_SCHEDULER_TICK_S` | 0.02 | 0.01 | 0.005 |
| `MOSHPRO_GUI_REFRESH_MS` | 50 | 16 | 16 |
| `MOSHPRO_API_MAX_PUSH_HZ` | 60 | 120 | 240 |

Measured (48 kHz):

| | `balanced` | `low` | `ultra` |
|---|---|---|---|
| Driver input latency, WASAPI | 22 ms (shared) | 22 ms (shared; Windows fixes it) | 5.3 ms (exclusive) |
| Driver input latency, MME | 35 ms | 17 ms | 15 ms |
| Audio age when analyzed (live, VB-Audio cable) | 22.5 ms | 21.8 ms | 5.9 ms |
| Kick detection after the attack | 4.7 ms | 3.5 ms | 2.8 ms |
| Onset detection after the attack | 5.1 ms | 4.1 ms | 3.5 ms |
| GUI refresh / API push wait (worst case) | 50 / 17 ms | 16 / 8 ms | 16 / 4 ms |
| Real-time path CPU (share of one core) | ~3% | ~5% | ~10% |
| Background jobs | baseline | ~2x as often | ~2x as often, dynamics 5x |

All profiles detected every kick with 0 driver overflows and 0 skipped hops
on the live test. Memory is unchanged: the buffers are sized in seconds.

What each one gives up:

- `low`: nothing much beyond CPU. On WASAPI shared mode the driver latency
  can't go lower, so the gain there is detection and refresh only (about
  20 ms less from sound to GUI, 5–10 ms less to the API); on MME it also
  saves about 18 ms of driver buffering.
- `ultra`: **WASAPI exclusive** saves about 16 ms more, but while the
  analysis runs no other app can record from that input (e.g. OBS capturing
  the same device). If the device refuses (already in use, unsupported
  format), the source falls back to shared mode with a warning;
  `stats()["wasapi_exclusive"]` and the GUI's Performance panel show which
  one you got. Set `MOSHPRO_WASAPI_EXCLUSIVE=false` to keep the rest of
  `ultra` without it. Smaller blocks and buffers leave less margin: if the
  Performance panel shows driver overflows, go back to `low`.
- Smaller hops make onset detection slightly more sensitive; the profiles
  raise `MOSHPRO_ONSET_THRESHOLD_K` to keep the onset rate comparable. Kick
  detection (`MOSHPRO_KICK_THRESHOLD_K`) is unaffected.
- `MOSHPRO_REALTIME_FFT_SIZE` is deliberately not in the profiles: 512 is too
  coarse in the bass and breaks kick detection.

Note: the GUI currently lists only 44.1 kHz devices, which on many machines
means MME/DirectSound entries; WASAPI devices running at 48 kHz (where
exclusive mode applies) are only reachable from code or the diagnostics.


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
| Raw energy stuck at ~0.001; kick strength, beat phase/lock, band levels, amplitude/RMS/peak stay at 0, while onset strength, BPM or key still move | no music reaches the selected input (raw energy 0.001 = −60 dBFS, a noise floor); the Performance panel's *Input level* is flagged red. Pick the input the music is actually routed to (e.g. the virtual cable the player outputs to), or enable Stereo Mix. The ratio-based values move on noise too, so they don't prove a signal |
| `ValueError: Source sample rate … does not match` | pass the device's sample rate to `AudioPipeline` |
| BPM/key slow to appear | worker processes still warming (librosa takes seconds to load on first use); call `prewarm_job_processes()` early |
| `hops_skipped` > 0, a large `max_backlog_s` or a high `load` | the real-time thread is starved of CPU; close heavy apps or raise `MOSHPRO_REALTIME_HOP_SIZE` |
| `overflows` > 0 | the driver dropped input; raise `MOSHPRO_BLOCK_SIZE` |
| Beats consistently early or late | tune `MOSHPRO_BEAT_LEAD_S` ([06](06_BEAT_TRACKING_AND_LATENCY.md)) |
| Key flips between relative major/minor | expected on ambiguous material; check `key_confidence` |
