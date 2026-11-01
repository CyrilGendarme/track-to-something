# Beat tracking and latency

## The problem

Anything that reacts to sound is late. The audio first crosses the capture
path (device buffers, the 512-sample block), then the analysis window, and
only then can a kick be detected. Visuals that flash when a kick is
*detected* trail the music by tens of milliseconds, and that's visible.

## The beat tracker

`BeatTracker` (`src/engine/realtime.py`) is a phase-locked loop:

- **Flywheel.** It runs at the consensus tempo from the BPM jobs. Before the
  first BPM result, it uses the median interval between kicks.
- **Correction.** Each kick within ±20 % of a period of a predicted beat
  nudges the phase by 30 % of the error, and adds 5 % of the error to a
  learned tempo offset (an alpha-beta / type-2 loop). The offset stays within
  ±2 % of the prior, and resets if the prior moves by more than 2 %. A
  slightly wrong prior, such as 127.5 vs 128 BPM, therefore doesn't leave a
  steady lag.
- **Lock.** `beat_confidence` rises with each matching kick, falls with
  off-grid kicks, and decays for every predicted beat that gets no kick.
- **Breakdowns.** The flywheel keeps beating through gaps. After 8 s without
  a matching kick it lets go and waits for the next one.

## Emitting beats on time

Beats come from the prediction, never from a detection. Each beat is emitted
ahead of its predicted time by:

```
lookahead = ½ hop  +  audio age  +  MOSHPRO_BEAT_LEAD_S
```

- **½ hop**: the hop grid is 5.8 ms, so emitting on the nearest hop averages
  the quantization out.
- **Audio age**: how old the audio being analyzed is, measured live from the
  capture clock (about 24 ms on WASAPI with 512-sample blocks), capped at
  300 ms.
- **`MOSHPRO_BEAT_LEAD_S`**: latency the engine can't see (below).

The event's `timestamp` / `time_unix` is the exact predicted beat time, not
the moment it was emitted.

### The capture clock

Sources timestamp each block with its capture time. PortAudio's ADC
timestamp is used only when it's plausible: on WASAPI it is reported several
ms *in the future*, so instead the source uses the callback arrival time
minus the block duration and the stream's declared input latency. The ring
buffer turns these timestamps into a smoothed stream-time → Unix-time
mapping:

- an EMA absorbs callback jitter;
- a jump over 100 ms (e.g. a device stall) resynchronizes it.

File and synthetic sources have no capture clock. There `audio_age_s` is 0
and the Unix times are `None`.

### What `MOSHPRO_BEAT_LEAD_S` is for

The engine can only measure from the moment its input captured the audio.
Two kinds of latency fall outside that:

- **Upstream**: the music reaches the audience before it reaches the
  analyzer input, e.g. through a virtual cable's internal buffer, or a
  mixer feeding an interface.
- **Downstream**: after the event, the frame still has to be rendered and
  shown (OBS, encoder, projector or LED processor often add 30–100 ms).

Set the lead to the sum of those. For the upstream part, the loopback test
measures it and suggests a value:

```bash
python -m src.diagnostics.loopback_test --out "CABLE Input" --in "CABLE Output"
```

Measured through VB-Audio Virtual Cable (WASAPI, 48 kHz):

| | Kick reached output → event delivered |
|---|---|
| onset events (reactive) | about +85 to +93 ms |
| beat events, no lead | about +63 ms (audio age compensated) |
| beat events, 63 ms lead | about −8 ms (p5 −14, p95 −3) |

The cable itself accounts for most of that path. Downstream latency has to be
measured separately, e.g. by filming a click and the screen together.

## Consuming beats

- **In process**: the `"beat"` callback event, which arrives on time if
  the lead is right.
- **Sampling** (GUI, WebSocket): watch `beat_count` change, or better,
  schedule on `predicted_next_beat_unix_s`. That's the Unix time of the
  next beat, independent of how often you sample.
- **Smooth animation**: `beat_phase` (0 at the beat → 1). Combine it with
  `predicted_next_beat_unix_s` if your frame rate is low.
- **Gate on lock**: ignore beats while `beat_confidence` is below ~0.5.
