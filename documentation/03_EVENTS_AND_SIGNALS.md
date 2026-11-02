# Events and signals

The engine produces two kinds of output, and visuals usually want both.

| | Events | Continuous signals |
|---|---|---|
| What | something happened at an instant | a level that is always defined |
| Examples | onset, kick, beat | bass/mid/high level, beat phase, energy trend |
| Drive | triggers: flashes, cuts, strobes, particle bursts | parameters: brightness, scale, colour, speed |
| How to read | callback, counters, or the predicted beat time | read the latest value whenever you render |

## Events

| Event | Source | Meaning |
|---|---|---|
| `onset` | full-band spectral flux | any sharp attack (kick, snare, hat, stab) |
| kick | bass-band flux | a low-frequency hit; its attack time is located to about 1 ms |
| `beat` | beat tracker | the predicted beat, on the musical grid |

**Prefer `beat` to kick for anything rhythmic.** A beat comes from a
prediction locked to the tempo, so it arrives on time, continues through short
breakdowns, and isn't fooled by off-beat kicks. Kicks and onsets are
reactions: they can only arrive after the sound.

### Three ways to receive events

1. **Callback** (in-process): `AudioPipeline(event_callback=fn)` calls
   `fn("onset", {...})` and `fn("beat", {...})` from the real-time thread.
   Every event is delivered, so this is the most precise option, but keep it
   cheap and thread-safe.
2. **Counters** (any sampler: GUI poll, WebSocket push, HTTP poll):
   `FastFeatures.onset_count`, `kick_count` and `beat_count` only ever
   increase. If the value changed since your last read, that many events
   happened. Don't rely on `onset_detected` / `beat_detected` when sampling:
   they're true for a single ~6 ms hop and are usually missed.
3. **Scheduling** (best for beats): `predicted_next_beat_unix_s` says when
   the next beat lands in wall-clock time. Schedule your effect for then
   instead of reacting late (see [06](06_BEAT_TRACKING_AND_LATENCY.md)).

## Continuous signals

| Signal | Group | Range | Character |
|---|---|---|---|
| `raw_energy` | fast | 0–1 | RMS of the newest hop; jittery, best for meters |
| `bass_energy`, `mid_energy`, `high_energy` | medium | 0–1 | smoothed (10 ms attack, 150 ms release), relative to each band's recent peak |
| `custom_energy` | medium | 0–1 | the same, for a band you choose (`set_custom_band`, or the GUI sliders) |
| `beat_phase` | fast | 0→1 | sawtooth: 0 on the beat, ramps up to the next one. Great for pulsing and easing |
| `onset_strength` | fast | 0–1 | flux relative to the adaptive threshold (0.5 = at threshold) |
| `spectral_density_low/mid/high` | slow | 0–1, sum ≈ 1 | spectral balance over ~2 s; good for palettes |
| `energy_trend` | slow | −1…1 | relative loudness change per second: builds (+) and breakdowns (−) |
| `energy_variance` | slow | 0–1 | how much the loudness moves over ~2 s |
| `estimated_bpm`, `detected_key` | slow | — | change rarely; good for scene selection |

**Band levels are relative.** A `bass_energy` of 1.0 means "as loud as the
bass has been recently" (the peak decays over ~4 s), not "the bass is the
loudest band". A quiet track still swings the full range; silence stays near
0 thanks to an absolute floor.

## Example: one render frame

```python
fast, medium, slow = pipeline.feature_cache.get_all()

# Continuous: drive parameters every frame
scale = 1.0 + 0.3 * medium.bass_energy
pulse = (1.0 - fast.beat_phase) ** 3          # sharp hit on the beat, then decay
hue = 0.6 * slow.spectral_density_low + 0.1 if slow else 0.5

# Events: trigger on counter changes
if fast.beat_count != state.last_beat_count:
    state.last_beat_count = fast.beat_count
    trigger_flash(intensity=fast.beat_confidence)
```
