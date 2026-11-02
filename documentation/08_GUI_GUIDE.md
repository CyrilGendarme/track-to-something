# GUI guide

```bash
python -m src.gui.main_gui
```

At launch, the GUI starts warming the BPM/key worker processes in the
background, so the first estimates arrive within seconds of pressing Start.

## Left panel

**Audio Input.** The **Device** dropdown lists:

- input devices: microphones, interfaces, virtual cable outputs, Stereo Mix;
- running applications that have a Windows audio session (needs `pycaw`).

An application entry checks the app is running, then captures the **whole
system** loopback; it is not isolated to that app. **🔄 Refresh** re-scans.
**Device Info** shows the channels, sample rate and type; the pipeline runs
at the device's sample rate.

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
