# Documentation

Real-time audio analysis for audio-reactive visuals and lighting: capture a
live input, analyze it, and serve the results to the GUI and to other local
applications.

| Guide | Read it when you want to… |
|---|---|
| [01 Quick start](01_QUICK_START.md) | install, run the GUI, use the engine from Python |
| [02 Architecture](02_ARCHITECTURE.md) | understand the threads, the ring buffer and the job scheduler |
| [03 Events and signals](03_EVENTS_AND_SIGNALS.md) | decide which outputs to drive your visuals with |
| [04 API reference](04_API_REFERENCE.md) | look up a class, a feature field or an HTTP/WebSocket endpoint |
| [05 Analysis methods](05_ANALYSIS_METHODS.md) | know how each feature, the BPM and the key are computed |
| [06 Beat tracking and latency](06_BEAT_TRACKING_AND_LATENCY.md) | sync to the beat and tune `MOSHPRO_BEAT_LEAD_S` |
| [07 Integration](07_INTEGRATION.md) | consume the data from OBS, a browser, Python or another app |
| [08 GUI guide](08_GUI_GUIDE.md) | use the desktop application |
| [09 Configuration and diagnostics](09_CONFIGURATION_AND_DIAGNOSTICS.md) | change settings, test on real hardware, troubleshoot |

## In one paragraph

A capture thread writes mono audio into a ring buffer. A real-time thread
analyzes every ~6 ms hop of it in order (onsets, kicks, band levels, beat
tracking). Background jobs each read their own window from the same buffer at
their own pace: dynamics every 0.25 s, BPM every 1 s, key every 2 s, with the
heavy ones in worker processes. Every result lands in a `FeatureCache`,
which the GUI polls and the local API pushes to clients.
