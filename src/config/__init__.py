"""Configuration and settings module.

All configurable values are centralized here. Settings can be overridden
via environment variables (MOSHPRO_* prefix).

Example:
    export MOSHPRO_SAMPLE_RATE=48000
    export MOSHPRO_BUFFER_CAPACITY_SECONDS=10.0
"""

from .settings import (
    # Audio capture & processing
    DEFAULT_SAMPLE_RATE,
    AUDIO_CHUNK_SIZE,
    AUDIO_BIT_DEPTH,
    AUDIO_CHANNELS,
    AUDIO_APPLY_HPF,
    # Buffer
    BUFFER_CAPACITY_SECONDS,
    # Analysis windows
    FAST_WINDOW_MS,
    MEDIUM_WINDOW_MS,
    SLOW_WINDOW_MS,
    BEAT_HISTORY_SIZE,
    # Tiered analysis decimation
    SPECTRAL_ANALYSIS_DECIMATION,
    TEMPO_ANALYSIS_DECIMATION,
    # STFT
    STFT_FFT_SIZE,
    STFT_HOP_LENGTH,
    STFT_WINDOW,
    # Frequency bands
    FREQ_BAND_BASS_MIN,
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_MID_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_HIGH_MIN,
    FREQ_BAND_HIGH_MAX,
    # Threading
    NUM_PROCESSING_WORKERS,
    OUTPUT_QUEUE_MAXSIZE,
    # Detection thresholds
    ONSET_THRESHOLD,
    BEAT_CONFIDENCE_THRESHOLD,
    SILENCE_THRESHOLD,
    # Logging
    LOG_LEVEL,
    DEBUG_WORKERS,
    DEBUG_ANALYSIS,
)

__all__ = [
    # Audio capture & processing
    "DEFAULT_SAMPLE_RATE",
    "AUDIO_CHUNK_SIZE",
    "AUDIO_BIT_DEPTH",
    "AUDIO_CHANNELS",
    "AUDIO_APPLY_HPF",
    # Buffer
    "BUFFER_CAPACITY_SECONDS",
    # Analysis windows
    "FAST_WINDOW_MS",
    "MEDIUM_WINDOW_MS",
    "SLOW_WINDOW_MS",
    "BEAT_HISTORY_SIZE",
    # Tiered analysis decimation
    "SPECTRAL_ANALYSIS_DECIMATION",
    "TEMPO_ANALYSIS_DECIMATION",
    # STFT
    "STFT_FFT_SIZE",
    "STFT_HOP_LENGTH",
    "STFT_WINDOW",
    # Frequency bands
    "FREQ_BAND_BASS_MIN",
    "FREQ_BAND_BASS_MAX",
    "FREQ_BAND_MID_MIN",
    "FREQ_BAND_MID_MAX",
    "FREQ_BAND_HIGH_MIN",
    "FREQ_BAND_HIGH_MAX",
    # Threading
    "NUM_PROCESSING_WORKERS",
    "OUTPUT_QUEUE_MAXSIZE",
    # Detection thresholds
    "ONSET_THRESHOLD",
    "BEAT_CONFIDENCE_THRESHOLD",
    "SILENCE_THRESHOLD",
    # Logging
    "LOG_LEVEL",
    "DEBUG_WORKERS",
    "DEBUG_ANALYSIS",
]
