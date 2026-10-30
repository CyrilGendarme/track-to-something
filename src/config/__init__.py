"""Configuration and settings module.

All configurable values are centralized here. Settings can be overridden
via environment variables (MOSHPRO_* prefix).

Example:
    export MOSHPRO_SAMPLE_RATE=48000
    export MOSHPRO_BPM_INTERVAL_S=2.0
"""

from .settings import (
    # Audio capture
    DEFAULT_SAMPLE_RATE,
    AUDIO_BLOCK_SIZE,
    AUDIO_BIT_DEPTH,
    AUDIO_APPLY_HPF,
    # Buffer
    BUFFER_CAPACITY_SECONDS,
    # Real-time path
    REALTIME_HOP_SIZE,
    REALTIME_FFT_SIZE,
    ONSET_MIN_INTERVAL_S,
    KICK_MIN_INTERVAL_S,
    ONSET_THRESHOLD_K,
    SILENCE_RMS,
    # Background jobs
    DYNAMICS_INTERVAL_S,
    DYNAMICS_WINDOW_S,
    BPM_INTERVAL_S,
    BPM_WINDOW_S,
    KEY_INTERVAL_S,
    KEY_WINDOW_S,
    KEY_HISTORY_SIZE,
    JOBS_USE_PROCESSES,
    # Frequency bands
    FREQ_BAND_BASS_MIN,
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_MID_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_HIGH_MIN,
    FREQ_BAND_HIGH_MAX,
    # Offline analysis
    STFT_FFT_SIZE,
    STFT_HOP_LENGTH,
    # Logging
    LOG_LEVEL,
    # Local API
    API_HOST,
    API_PORT,
    API_MAX_PUSH_HZ,
)

__all__ = [
    "DEFAULT_SAMPLE_RATE",
    "AUDIO_BLOCK_SIZE",
    "AUDIO_BIT_DEPTH",
    "AUDIO_APPLY_HPF",
    "BUFFER_CAPACITY_SECONDS",
    "REALTIME_HOP_SIZE",
    "REALTIME_FFT_SIZE",
    "ONSET_MIN_INTERVAL_S",
    "KICK_MIN_INTERVAL_S",
    "ONSET_THRESHOLD_K",
    "SILENCE_RMS",
    "DYNAMICS_INTERVAL_S",
    "DYNAMICS_WINDOW_S",
    "BPM_INTERVAL_S",
    "BPM_WINDOW_S",
    "KEY_INTERVAL_S",
    "KEY_WINDOW_S",
    "KEY_HISTORY_SIZE",
    "JOBS_USE_PROCESSES",
    "FREQ_BAND_BASS_MIN",
    "FREQ_BAND_BASS_MAX",
    "FREQ_BAND_MID_MIN",
    "FREQ_BAND_MID_MAX",
    "FREQ_BAND_HIGH_MIN",
    "FREQ_BAND_HIGH_MAX",
    "STFT_FFT_SIZE",
    "STFT_HOP_LENGTH",
    "LOG_LEVEL",
    "API_HOST",
    "API_PORT",
    "API_MAX_PUSH_HZ",
]
