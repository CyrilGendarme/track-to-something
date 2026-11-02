# Architecture

```
 audio device ──► AudioCaptureWorker ──► RingBuffer (mono, absolute sample index, capture clock)
                  (mono mix, 20 Hz HPF)      │
                    ┌────────────────────────┴───────────────────────┐
                    ▼                                                ▼
        RealtimeWorker — every hop (~6 ms)               JobScheduler — latest-wins
        onsets, kicks, band levels,                      dynamics      thread            every 0.25 s, 2 s window
        beat tracker ◄──── consensus tempo ───────────── BPM (numpy)   "signal" pool     every 1 s,    8 s window
                    │                                    BPM (librosa) "librosa" pool    every 1 s,    8 s window
                    │                                    key           "signal" pool     every 2 s,    8 s window
                    ▼                                                │
                    └───────────────► FeatureCache ◄─────────────────┘
                                          │
                          GUI (polls, 20 Hz)   Local API (push, ≤ 60 Hz)
```

## Design rules

1. **One writer, one buffer.** Only the capture thread writes. Every reader
   asks for an exact span by absolute sample index, so it can use any window
   length, detect that it fell behind (the span was overwritten), and say
   which audio its result covers.
2. **Stateful work is sequential.** Spectral flux needs the previous frame,
   adaptive thresholds need history, and the beat tracker needs its phase.
   All of that runs in one thread, in stream order. Splitting chunks across
   threads would break it (an earlier version did, and scrambled the analysis).
3. **Parallelism is by task, not by chunk.** Each expensive analysis is a job
   with its own cadence and window, running beside the real-time path.
4. **Nothing queues up.** If a job is still running when its next tick comes,
   the tick is skipped: a slow job runs less often, it never builds a
   backlog. The real-time thread never blocks on consumers.
5. **Consumers read one store.** The GUI and the API only read the
   `FeatureCache`. Tk widgets are only touched from the Tk thread.

## Components

### Capture — `src/engine/capture_worker.py`
Pulls `AudioChunk`s from the source and does cheap, stateful conditioning:
mono mix, a 20 Hz high-pass whose filter state carries across chunks, and
optional quantization. It also passes the chunk's capture timestamp to the
ring buffer. On `stop()` it closes the source, so a blocking device read
returns.

### Live sources — `src/sources/live_audio.py`
`SoundDeviceSource` (and `AudioInputSource` / `ApplicationAudioSource`) wrap a
PortAudio input stream:

- The PortAudio callback only copies the block and its capture time into a
  queue.
- The stream is opened and closed by the reading (capture) thread, with COM
  initialized on it. WASAPI needs this, and fails with "Unanticipated host
  error" without it.
- `sounddevice` is imported lazily, so the job worker processes don't
  initialize PortAudio.
- `overflows` counts blocks the driver reported as dropped.

### Ring buffer — `src/engine/buffer.py`
A fixed-size mono float32 array: `MOSHPRO_BUFFER_CAPACITY_SECONDS` (12 s by
default), and never less than the longest job window plus 2 s of headroom. Readers wait on a condition variable for new
data. It also keeps a **capture clock**: a smoothed mapping from stream time
(samples ÷ sample rate) to Unix time, which latency compensation relies on
(see [06](06_BEAT_TRACKING_AND_LATENCY.md)).

### Real-time path — `src/engine/realtime.py`
`RealtimeWorker` walks the buffer one hop (256 samples) at a time, analyzing
a 1024-sample frame that ends at each hop:

- `RealtimeAnalyzer`: onsets (spectral flux), kicks (bass-band flux) with
  the attack located inside the hop, and band levels.
- `BeatTracker`: a phase-locked loop around the consensus tempo.
- Publishes `FastFeatures` + `MediumFeatures` to the cache on every hop, and
  `onset` / `beat` events to the callback.

A hop costs about 0.15 ms (about 3 % of real time at 48 kHz); `stats()["load"]`
reports the live figure. If the thread ever falls behind
by more than the buffer, it skips ahead and counts `hops_skipped`.

### Scheduler — `src/engine/scheduler.py`
An `AnalysisJob` declares `fn(window, sample_rate)`, an interval, a window
length and where it runs:

- `process_pool=None` runs it in the scheduler's thread pool.
- Otherwise it runs in a named, app-wide `ProcessPoolExecutor`:
  - **Process pools outlive pipelines.** Spawning a worker and importing
    librosa takes seconds, so it happens once. The GUI starts warming the
    pools at launch (`prewarm_job_processes()`).
  - **librosa gets its own pool** (`"librosa"`, 1 worker), so its slow first
    import never delays key detection or the numpy BPM detectors (`"signal"`,
    2 workers).
  - A broken pool (a crashed worker) is discarded and recreated.
- When a finite source ends, `AudioPipeline.wait()` lets in-flight jobs
  publish their final results before stopping the scheduler.

### Pipeline and cache — `src/engine/pipeline.py`
`AudioPipeline` wires everything together. It merges the results of the two
BPM jobs into one octave-aware consensus, feeds that tempo back to the beat
tracker as a prior, smooths key estimates, and assembles `SlowFeatures`
whenever any job reports. `FeatureCache` holds the latest of each group and
calls an optional update callback, which the API uses to push.

### Local API — `src/api/server.py`
aiohttp on its own event-loop thread, bound to 127.0.0.1. HTTP endpoints
return the cache. WebSocket clients get a snapshot on connect, then pushes
merged to at most 60 per second. See [04](04_API_REFERENCE.md).

## Threads and processes at run time

| Name | Kind | Does |
|---|---|---|
| PortAudio callback | driver thread | copies blocks into the source queue |
| `Capture` | thread | source → conditioning → ring buffer |
| `Realtime` | thread | per-hop analysis, beat tracking, events |
| `JobScheduler` | thread | ticks jobs, copies their windows |
| `job_*` | thread pool (2) | dynamics |
| `signal` pool | 2 processes | numpy BPM detectors, key |
| `librosa` pool | 1 process | librosa beat tracker |
| `AnalysisAPIServer` | thread + asyncio loop | HTTP/WebSocket |
| Tk main thread | GUI | polls the cache at 20 Hz, drains the UI queue |
