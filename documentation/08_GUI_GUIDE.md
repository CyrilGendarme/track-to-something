# GUI guide

```bash
python -m src.gui.main_gui
```

At launch, the GUI starts warming the BPM/key worker processes in the
background, so the first estimates arrive within seconds of pressing Start.

The GUI runs with the lowest-latency profile, `crazy_ultra_amazing_waw`, by
default: high priority audio threads, WASAPI exclusive input, a 125 Hz
display. It uses more CPU and, while analysis runs, no other app can record
from the selected WASAPI input. For a lighter setup:

```powershell
$env:MOSHPRO_LATENCY_PROFILE = "balanced"   # or low / ultra
python -m src.gui.main_gui
```

See [09](09_CONFIGURATION_AND_DIAGNOSTICS.md#latency-profiles).

## Left panel

**Audio Input.** The **Device** dropdown lists:

- input devices: microphones (including the laptop's built-in microphone
  array), interfaces, virtual cable outputs, Stereo Mix;
- **🔊 output devices** ("what's playing"): records what a speaker or headset
  plays, through WASAPI loopback (needs `soundcard`);
- **🎧 running applications** that have a Windows audio session (needs
  `pycaw`).

An application entry checks the app is running, then records the default
output device: you get that app's sound **mixed with anything else playing
on the same device** (Windows doesn't separate apps there). For one app
alone, route it to its own output, e.g. the VB-Audio cable in Windows'
*App volume and device preferences*, and select *CABLE Output*. **🔄 Refresh**
re-scans.

Built-in microphones: in shared mode Windows applies its voice processing
(noise suppression), which removes music. The default profile opens WASAPI
inputs in exclusive mode, which records the raw microphone. With other
profiles, turn off *Audio enhancements* for the microphone in Windows' sound
settings.

Loopback entries can't read the device's timestamps, so their *Audio age*
reads lower than it really is (by the device's buffering, ~10–20 ms); add it
to `MOSHPRO_BEAT_LEAD_S` if beats must be exact.
**Device Info** shows the channels, sample rate and type; the pipeline runs
at the device's sample rate. Each entry also names its driver (MME, WASAPI,
...). With the default profile, WASAPI inputs come first and the first one is
preselected: pick the one your music is routed to (e.g. *CABLE Output*).

**Custom Frequency Range.** Tick **Track this band** to follow one extra
band of your choice, e.g. 40–120 Hz for the kick or 2–5 kHz for vocals and
snares. Its level appears as **Custom Band** in the MEDIUM tab and as
`custom_energy` in the API. The sliders are logarithmic (20 Hz–20 kHz), and
the band always stays at least about 1/6 octave wide. Changes apply
immediately, even while analysis is running. The fixed bands (bass 20–250 Hz,
mid 250–4000 Hz, high 4000–20000 Hz) are unaffected.

**Analysis Control.** **▶ Start Analysis** and **⏹ Stop Analysis**. Stop
closes the device; Start opens it again. If the device fails to open, the
error is logged and the controls reset.

**Performance** (refreshed twice a second while running, from
`AudioPipeline.stats()`):

| Row | Meaning | Healthy |
|---|---|---|
| Input level | input RMS over the last second | about −30 to −10 dBFS for music; flagged red below −45 |
| Uptime | time since Start, hops analyzed (and skipped, if any) | no skipped hops |
| Real-time load | analysis time per hop as a share of the hop's duration | a few %; above 80 % it's flagged as too slow |
| Backlog (max) | how far analysis trails the newest audio (worst so far) | under ~50 ms |
| Audio age | how old the audio is when analyzed (device buffering included) | 10–40 ms on WASAPI |
| Driver overflows | blocks the audio driver reported as dropped | 0 |
| Jobs | last compute time of each background job; skipped runs if any | well under each job's interval |

**Local API.** **Enable Local API** serves the data on
`http://127.0.0.1:8768`. It's independent of Start/Stop and keeps serving
the last values while analysis is stopped. See [07](07_INTEGRATION.md).

## Right panel

**Metrics tabs** (refreshed at 20 Hz):

| Tab | Shows |
|---|---|
| FAST | raw energy, onset strength, kick strength, beat phase, beat lock, tracked tempo, beat count, audio age |
| MEDIUM | bass/mid/high levels, bass delta, custom band |
| SLOW | amplitude, RMS, peak, spectral densities, key and confidence, BPM and stability, energy trend/average/variance |
| BPM METHODS | each detector's BPM and confidence, plus the consensus |

**Analysis Results & Latency Log** lists pipeline start/stop, device changes
and every onset/beat event. It keeps the last 1000 lines. **Pause** freezes
it and **Clear Log** empties it.

## Tips

- Expect a few seconds before BPM and key appear: the jobs need at least
  2 s of audio, and the estimates settle over about 8 s.
- `beat_confidence` (Beat Lock) above ~0.8 means the tracker is following
  the kicks. Low values on tracks without a steady kick are expected.
- If BPM stays empty, check the BPM METHODS tab for per-method errors.
