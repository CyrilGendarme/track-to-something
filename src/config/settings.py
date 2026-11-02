"""Centralized configuration and settings for the audio engine.

All hardcoded configuration values should be defined here for easy adjustment
without modifying code files. Every value can be overridden with the matching
``MOSHPRO_*`` environment variable.
"""

from __future__ import annotations

import os
from typing import Final

# ────────────────────────────────────────────────────────────────────────────
# LATENCY PROFILE
# ────────────────────────────────────────────────────────────────────────────

# Picks the defaults of the latency-related settings below. Any individual
# MOSHPRO_* variable still overrides its profile value.
#   balanced  the reference setup: lowest CPU, robust on any driver
#   low       ~2x the real-time CPU; smaller device buffers, finer analysis
#             steps, faster job/GUI/API refresh
#   ultra     ~4x the real-time CPU (about 10% of one core); smallest
#             buffers and WASAPI exclusive mode where available
LATENCY_PROFILES: Final[dict[str, dict[str, str]]] = {
    "balanced": {
        "BLOCK_SIZE": "512",
        "DEVICE_LATENCY": "high",
        "WASAPI_EXCLUSIVE": "false",
        "REALTIME_HOP_SIZE": "256",
        "ONSET_THRESHOLD_K": "2.0",
        "DYNAMICS_INTERVAL_S": "0.25",
        "BPM_INTERVAL_S": "1.0",
        "KEY_INTERVAL_S": "2.0",
        "SCHEDULER_TICK_S": "0.02",
        "GUI_REFRESH_MS": "50",
        "API_MAX_PUSH_HZ": "60",
    },
    "low": {
        "BLOCK_SIZE": "256",
        "DEVICE_LATENCY": "low",
        "WASAPI_EXCLUSIVE": "false",
        "REALTIME_HOP_SIZE": "128",
        "ONSET_THRESHOLD_K": "2.3",
        "DYNAMICS_INTERVAL_S": "0.1",
        "BPM_INTERVAL_S": "0.5",
        "KEY_INTERVAL_S": "1.0",
        "SCHEDULER_TICK_S": "0.01",
        "GUI_REFRESH_MS": "16",
        "API_MAX_PUSH_HZ": "120",
    },
    "ultra": {
        "BLOCK_SIZE": "128",
        "DEVICE_LATENCY": "low",
        "WASAPI_EXCLUSIVE": "true",
        "REALTIME_HOP_SIZE": "64",
        "ONSET_THRESHOLD_K": "2.5",
        "DYNAMICS_INTERVAL_S": "0.05",
        "BPM_INTERVAL_S": "0.5",
        "KEY_INTERVAL_S": "1.0",
        "SCHEDULER_TICK_S": "0.005",
        "GUI_REFRESH_MS": "16",
        "API_MAX_PUSH_HZ": "240",
    },
}

LATENCY_PROFILE: Final[str] = os.getenv("MOSHPRO_LATENCY_PROFILE", "balanced").strip().lower()
if LATENCY_PROFILE not in LATENCY_PROFILES:
    raise ValueError(
        f"MOSHPRO_LATENCY_PROFILE={LATENCY_PROFILE!r}; expected one of {', '.join(LATENCY_PROFILES)}"
    )


def _profiled(name: str) -> str:
    """``MOSHPRO_<name>`` if set, else the active latency profile's value."""
    return os.getenv(f"MOSHPRO_{name}", LATENCY_PROFILES[LATENCY_PROFILE][name])


def _device_latency(value: str) -> str | float:
    value = value.strip().lower()
    return value if value in ("low", "high") else float(value)

# ────────────────────────────────────────────────────────────────────────────
# AUDIO CAPTURE
# ────────────────────────────────────────────────────────────────────────────

# Default sample rate for audio capture and processing (Hz)
DEFAULT_SAMPLE_RATE: Final[int] = int(os.getenv("MOSHPRO_SAMPLE_RATE", "44100"))

# Block size requested from live audio devices (samples per callback).
# This bounds capture latency: 512 @ 44.1kHz = ~11.6ms. The real-time analyzer
# works in its own hop size, so this does not change analysis resolution.
AUDIO_BLOCK_SIZE: Final[int] = int(_profiled("BLOCK_SIZE"))

# Buffering requested from the audio driver: "low", "high" (PortAudio's
# suggested values) or seconds. MME: "low" saves ~12 ms; WASAPI shared mode
# is fixed by Windows (~20 ms) whatever this says.
DEVICE_LATENCY: Final[str | float] = _device_latency(_profiled("DEVICE_LATENCY"))

# Open WASAPI inputs in exclusive mode: bypasses the Windows mixer (e.g.
# 22 ms -> 5 ms with 128-sample blocks), but no other app can record from that
# input meanwhile. Falls back to shared mode if the device refuses.
WASAPI_EXCLUSIVE: Final[bool] = _profiled("WASAPI_EXCLUSIVE").lower() == "true"

# Quantize captured audio to this bit depth (>= 16 disables quantization).
AUDIO_BIT_DEPTH: Final[int] = int(os.getenv("MOSHPRO_BIT_DEPTH", "16"))

# Apply a 20 Hz high-pass filter (removes DC offset and sub-sonic rumble).
AUDIO_APPLY_HPF: Final[bool] = os.getenv("MOSHPRO_APPLY_HPF", "true").lower() == "true"

# ────────────────────────────────────────────────────────────────────────────
# RING BUFFER (single writer: capture thread; many readers)
# ────────────────────────────────────────────────────────────────────────────

# Minimum ring buffer capacity in seconds. The pipeline always enlarges it to
# fit the longest background job window (plus headroom).
BUFFER_CAPACITY_SECONDS: Final[float] = float(
    os.getenv("MOSHPRO_BUFFER_CAPACITY_SECONDS", "12.0")
)

# ────────────────────────────────────────────────────────────────────────────
# REAL-TIME PATH (runs on every hop, sequentially, in one thread)
# ────────────────────────────────────────────────────────────────────────────

# Hop between real-time analysis frames (samples). 256 @ 44.1kHz = ~5.8ms.
# Smaller hops detect transients sooner (kicks: 4.7 / 3.5 / 2.8 ms at 256 /
# 128 / 64 @ 48 kHz) at proportionally more CPU.
REALTIME_HOP_SIZE: Final[int] = int(_profiled("REALTIME_HOP_SIZE"))

# FFT window for the real-time frame (samples). 1024 @ 44.1kHz = ~23ms window,
# ~43Hz per bin - enough to separate the bass band from the rest. Not part of
# the latency profiles: 512 is too coarse in the bass and breaks kick detection.
REALTIME_FFT_SIZE: Final[int] = int(os.getenv("MOSHPRO_REALTIME_FFT_SIZE", "1024"))

# Minimum time between two onsets / two kicks (refractory period, seconds).
ONSET_MIN_INTERVAL_S: Final[float] = float(os.getenv("MOSHPRO_ONSET_MIN_INTERVAL_S", "0.08"))
KICK_MIN_INTERVAL_S: Final[float] = float(os.getenv("MOSHPRO_KICK_MIN_INTERVAL_S", "0.2"))

# Extra lead for beat events (seconds), on top of the automatically measured
# capture latency. Use it for latency the engine can't see: upstream (e.g. a
# virtual cable's buffer, mixer -> interface) and downstream (OBS / video
# pipeline / projector). Beats are then emitted that much earlier.
BEAT_LEAD_S: Final[float] = float(os.getenv("MOSHPRO_BEAT_LEAD_S", "0.0"))

# Adaptive onset threshold: mean + K * std of recent spectral flux. Smaller
# hops give more chances per second to cross it, so the profiles raise K to
# keep the onset rate comparable.
ONSET_THRESHOLD_K: Final[float] = float(_profiled("ONSET_THRESHOLD_K"))

# Same for kicks (bass-band flux).
KICK_THRESHOLD_K: Final[float] = float(os.getenv("MOSHPRO_KICK_THRESHOLD_K", "2.0"))

# Frames whose RMS is below this (linear, 0-1) never produce onsets (~-60 dBFS).
SILENCE_RMS: Final[float] = float(os.getenv("MOSHPRO_SILENCE_RMS", "0.001"))

# ────────────────────────────────────────────────────────────────────────────
# BACKGROUND JOBS (scheduled; each reads its own window from the ring buffer)
# ────────────────────────────────────────────────────────────────────────────

# Dynamics (levels, spectral balance, energy trend) - cheap, runs in a thread.
DYNAMICS_INTERVAL_S: Final[float] = float(_profiled("DYNAMICS_INTERVAL_S"))
DYNAMICS_WINDOW_S: Final[float] = float(os.getenv("MOSHPRO_DYNAMICS_WINDOW_S", "2.0"))

# Multi-method BPM - expensive, runs in a separate process.
BPM_INTERVAL_S: Final[float] = float(_profiled("BPM_INTERVAL_S"))
BPM_WINDOW_S: Final[float] = float(os.getenv("MOSHPRO_BPM_WINDOW_S", "8.0"))

# Musical key - expensive, runs in a separate process.
KEY_INTERVAL_S: Final[float] = float(_profiled("KEY_INTERVAL_S"))
KEY_WINDOW_S: Final[float] = float(os.getenv("MOSHPRO_KEY_WINDOW_S", "8.0"))

# Number of recent key estimates used for the confidence-weighted vote
# (4 estimates x 2s interval = ~8s of smoothing).
KEY_HISTORY_SIZE: Final[int] = int(os.getenv("MOSHPRO_KEY_HISTORY_SIZE", "4"))

# How often the scheduler checks whether a job is due (seconds).
SCHEDULER_TICK_S: Final[float] = float(_profiled("SCHEDULER_TICK_S"))

# Run heavy jobs in worker processes (true parallelism, no GIL contention with
# the real-time thread). Set to "false" to use threads (e.g. for debugging).
JOBS_USE_PROCESSES: Final[bool] = os.getenv("MOSHPRO_JOBS_USE_PROCESSES", "true").lower() == "true"

# ────────────────────────────────────────────────────────────────────────────
# FREQUENCY BANDS (Hz)
# ────────────────────────────────────────────────────────────────────────────

FREQ_BAND_BASS_MIN: Final[float] = 20.0
FREQ_BAND_BASS_MAX: Final[float] = 250.0

FREQ_BAND_MID_MIN: Final[float] = 250.0
FREQ_BAND_MID_MAX: Final[float] = 4000.0

FREQ_BAND_HIGH_MIN: Final[float] = 4000.0
FREQ_BAND_HIGH_MAX: Final[float] = 20000.0

# ────────────────────────────────────────────────────────────────────────────
# OFFLINE ANALYSIS (src.analysis.audio_analyzer)
# ────────────────────────────────────────────────────────────────────────────

STFT_FFT_SIZE: Final[int] = int(os.getenv("MOSHPRO_STFT_FFT_SIZE", "2048"))
STFT_HOP_LENGTH: Final[int] = int(os.getenv("MOSHPRO_STFT_HOP_LENGTH", "512"))

# ────────────────────────────────────────────────────────────────────────────
# LOGGING & DEBUG
# ────────────────────────────────────────────────────────────────────────────

LOG_LEVEL: Final[str] = os.getenv("MOSHPRO_LOG_LEVEL", "INFO")

# GUI metrics refresh period (milliseconds).
GUI_REFRESH_MS: Final[int] = int(_profiled("GUI_REFRESH_MS"))

# ────────────────────────────────────────────────────────────────────────────
# LOCAL ANALYSIS API (HTTP + WebSocket for other local apps to consume data)
# ────────────────────────────────────────────────────────────────────────────

# Bind address for the local API server. Defaults to loopback-only so the
# analysis data isn't exposed to the network unless explicitly reconfigured.
API_HOST: Final[str] = os.getenv("MOSHPRO_API_HOST", "127.0.0.1")

# Port for the local API server (HTTP GET endpoints + /ws WebSocket stream)
API_PORT: Final[int] = int(os.getenv("MOSHPRO_API_PORT", "8768"))

# Maximum WebSocket push rate (messages per second per client).
API_MAX_PUSH_HZ: Final[float] = float(_profiled("API_MAX_PUSH_HZ"))
