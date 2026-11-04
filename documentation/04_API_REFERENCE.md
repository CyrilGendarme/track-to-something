# API reference

## Python

### `AudioPipeline` — `src.engine`

```python
AudioPipeline(
    audio_source: Callable[[], Iterable[AudioChunk]],
    buffer_capacity_s: float = 12.0,          # enlarged to fit the longest job window
    sample_rate: int = 44100,                 # must match the source
    event_callback: Callable[[str, dict], None] | None = None,
    feature_cache: FeatureCache | None = None,  # share one across restarts
    use_processes: bool = True,               # BPM/key jobs in worker processes
    beat_lead_s: float | None = None,         # default: MOSHPRO_BEAT_LEAD_S
    custom_band_hz: tuple[float, float] | None = None,  # see set_custom_band
)
```

| Member | Description |
|---|---|
| `start() -> AudioPipeline` | start the capture, real-time and scheduler threads |
| `stop()` | stop everything and close the source (unblocks a waiting device read) |
| `wait(timeout=None)` | wait until the source ends and is analyzed (final job results included) or the pipeline is stopped; re-raises a capture error such as a device failure or sample-rate mismatch |
| `is_running() -> bool` | audio is still being captured or analyzed |
| `set_custom_band(low_hz, high_hz)` | track an extra band as `MediumFeatures.custom_energy`; any thread, any time; `set_custom_band(None)` turns it off |
| `stats() -> dict` | health snapshot: `running`, `uptime_s`, `audio_s`, `hops_processed`, `hops_skipped`, `load` (analysis time per hop ÷ hop duration), `backlog_s`, `max_backlog_s`, `audio_age_s`, `input_dbfs` (input level over the last second), `overflows` (`None` for non-device sources), `latency_profile`, `block_size`, `hop_size`, `wasapi_exclusive` (whether exclusive mode was granted; `None` for non-device sources), `high_res_timer`, `realtime_boost`, and `jobs` (per job: `runs`, `skipped`, `last_compute_s`) |
| `feature_cache` | the `FeatureCache` |
| `get_events() -> list[(t, kind)]` | recent onset/beat events |
| `get_latest_audio(duration_s) -> np.ndarray` | latest mono audio from the ring buffer |
| `realtime_worker` | `hops_processed`, `hops_skipped`, `backlog_s`, `max_backlog_s`, `audio_age_s` |
| `jobs` | the `AnalysisJob`s, with `runs`, `skipped`, `last_compute_s` |

Event callback payloads:

- `("onset", {"timestamp": t, "strength": s})`
- `("beat", {"timestamp": t, "time_unix": u, "confidence": c, "bpm": b})`

`timestamp` is stream time in seconds. `time_unix` is the beat's wall-clock
time, or `None` without a capture clock (e.g. file sources).

`prewarm_job_processes()` starts and warms the shared worker processes ahead
of the first pipeline. The GUI calls it at launch.

### `FeatureCache` — `src.engine`

Thread-safe store: `get_all() -> (fast, medium, slow)` (each may be `None`
before the first result), `get_bpm_estimates() -> dict[str, BPMEstimate]`,
`set_update_callback(fn)` (called from producer threads; must be cheap).

### Sources — `src.sources`

| Class | Use |
|---|---|
| `AudioInputSource(device=…, sample_rate=…, block_size=512, channels=2)` | an input device (index or name) |
| `SystemLoopbackSource(speaker=None, sample_rate=48000, channels=2, block_size=…)` | what an output device plays (WASAPI loopback via `soundcard`); `speaker` is an id or name substring, None for the default output |
| `ApplicationAudioSource(application_name=…, device=None, …)` | checks the app is running, then records its output device's loopback (the device's whole mix, not the app alone) |
| `TrackAudioSource(block_size=…, audio_roots=…)` | reads the track the Rekordbox DataBridge reports as loaded |
| `AudioChunk(samples, sample_rate, capture_time_s=None)` | the unit sources yield; `capture_time_s` is the Unix time of the first sample, if known |

Live sources expose `overflows` (blocks the driver reported as dropped).

### Feature dataclasses — `src.analysis`

**`FastFeatures`** (every hop)

| Field | Description |
|---|---|
| `timestamp_s` | stream time of the end of the hop |
| `onset_detected`, `onset_strength` | onset on this hop; flux ÷ (2 × threshold), 0–1 |
| `is_percussive_peak`, `percussive_peak_strength` | kick on this hop; kick strength (bass flux ÷ 2 × threshold, 0–1), held and decaying over ~100 ms so polling consumers see it |
| `raw_energy` | RMS of the newest hop |
| `beat_detected` | a beat was emitted on this hop |
| `beat_phase` | 0 at the beat → 1 just before the next |
| `beat_confidence` | tracker lock quality, 0–1 |
| `tempo_bpm` | tempo the tracker currently uses (the prior plus its learned correction) |
| `predicted_next_beat_s` / `predicted_next_beat_unix_s` | next beat, in stream time / Unix time |
| `audio_age_s` | how old the analyzed audio was (capture path + analysis) |
| `onset_count`, `kick_count`, `beat_count` | running totals; compare between reads |

**`MediumFeatures`** (every hop): `bass_energy`, `mid_energy`, `high_energy`
(0–1, relative to each band's recent peak), `bass_energy_delta`,
`overall_energy_delta`, `custom_energy` (same scale, for the band set with
`set_custom_band`; 0 when none) and `custom_band_hz` (`[low, high]` or
`null`).

**`SlowFeatures`** (on each job result)

| Field | From |
|---|---|
| `overall_amplitude`, `peak`, `rms`, `average_energy` | dynamics job (2 s window) |
| `bass_energy`, `mid_energy`, `high_energy` | mean of the window's band envelopes |
| `spectral_density_low/mid/high` | share of power per band |
| `energy_variance`, `energy_trend` | frame-loudness variation and slope |
| `band_bass/mid/high_envelope` | 20-point band contours over the window |
| `detected_key`, `key_confidence` | key job, smoothed over the last 4 estimates |
| `estimated_bpm`, `beat_stability` | BPM consensus and its confidence |
| `onset_detected`, `beat_detected`, `beat_confidence` | real-time events within the dynamics window |

**`BPMEstimate`**: `method`, `bpm`, `confidence`, `available`, `error`, `extra`.

Bands: bass 20–250 Hz, mid 250–4000 Hz, high 4000–20000 Hz.

## Local HTTP / WebSocket API

Started from the GUI's **Enable Local API** checkbox, or in code with
`AnalysisAPIServer(feature_cache).start()` (`src.api`). It binds
`127.0.0.1:8768` by default.

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /features` | `{"fast", "medium", "slow", "bpm_estimates", "bpm_consensus": {"bpm", "confidence"}}` |
| `GET /features/fast`, `/medium`, `/slow` | that group, or `null` |
| `GET /features/bpm` | `{"estimates": {method: BPMEstimate}, "consensus": {"bpm", "confidence"}}` |
| `WS /ws` | the `/features` payload: once on connect, then whenever data changes, at most `MOSHPRO_API_MAX_PUSH_HZ` (60) per second |

Notes:

- Values are plain JSON. numpy types are converted, and NaN/Inf become `null`.
- CORS is open (`*`), so a local web page can fetch the data. The server
  only listens on loopback unless you change `MOSHPRO_API_HOST`.
- The cache, and so the API, keeps the last values after analysis stops.
