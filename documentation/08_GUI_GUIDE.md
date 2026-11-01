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

**Custom Frequency Range.** The Min/Max sliders are not connected to the
analysis yet; changing them has no effect. The analysis uses the fixed bands
bass 20–250 Hz, mid 250–4000 Hz and high 4000–20000 Hz.

**Analysis Control.** **▶ Start Analysis** and **⏹ Stop Analysis**. Stop
closes the device; Start opens it again. If the device fails to open, the
error is logged and the controls reset. The **Performance** labels (chunks,
latency, uptime) are not updated by the current engine; use the FAST tab's
*Audio Age* or the diagnostics tools instead.

**Local API.** **Enable Local API** serves the data on
`http://127.0.0.1:8768`. It's independent of Start/Stop and keeps serving
the last values while analysis is stopped. See [07](07_INTEGRATION.md).

## Right panel

**Metrics tabs** (refreshed at 20 Hz):

| Tab | Shows |
|---|---|
| FAST | raw energy, onset strength, kick strength, beat phase, beat lock, tracked tempo, beat count, audio age |
| MEDIUM | bass/mid/high levels, bass delta |
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
