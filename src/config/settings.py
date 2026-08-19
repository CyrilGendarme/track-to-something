"""Centralized configuration and settings for the audio engine.

All hardcoded configuration values should be defined here for easy adjustment
without modifying code files.
"""

from __future__ import annotations

import os
from typing import Final

# ────────────────────────────────────────────────────────────────────────────
# AUDIO CAPTURE & PROCESSING
# ────────────────────────────────────────────────────────────────────────────

# Default sample rate for audio capture and processing (Hz)
# Common values: 44100 (CD quality), 48000 (video/professional)
DEFAULT_SAMPLE_RATE: Final[int] = int(os.getenv("MOSHPRO_SAMPLE_RATE", "44100"))

# Audio chunk size for capture workers (samples per chunk)
# Affects latency (smaller = lower latency, higher CPU)
# ~2048 samples @ 44.1kHz = ~46ms capture latency
AUDIO_CHUNK_SIZE: Final[int] = int(os.getenv("MOSHPRO_CHUNK_SIZE", "2048"))

# ────────────────────────────────────────────────────────────────────────────
# CIRCULAR BUFFER (shared between analyzer tiers)
# ────────────────────────────────────────────────────────────────────────────

# Circular buffer capacity in seconds
# Holds audio history for multi-window analysis
# 5.0s is large enough for slow (250ms) window to look back on history
BUFFER_CAPACITY_SECONDS: Final[float] = float(
    os.getenv("MOSHPRO_BUFFER_CAPACITY_SECONDS", "5.0")
)

# ────────────────────────────────────────────────────────────────────────────
# TIERED ANALYSIS WINDOWS
# ────────────────────────────────────────────────────────────────────────────

# Fast analyzer window (for transient detection)
# Latency: 5-10ms
# Use for: Kick/snare detection, onset detection, immediate effects
FAST_WINDOW_MS: Final[float] = float(os.getenv("MOSHPRO_FAST_WINDOW_MS", "10.0"))

# Medium analyzer window (for energy tracking)
# Latency: 20-50ms
# Use for: Spectral analysis, smooth animation, energy tracking
MEDIUM_WINDOW_MS: Final[float] = float(os.getenv("MOSHPRO_MEDIUM_WINDOW_MS", "32.0"))

# Slow analyzer window (for overall metrics)
# Latency: 100-500ms
# Use for: Tempo tracking, scene changes, stability metrics
SLOW_WINDOW_MS: Final[float] = float(os.getenv("MOSHPRO_SLOW_WINDOW_MS", "250.0"))

# Max beat history for tempo/BPM estimation
# More history = more stable tempo but slower adaptation
BEAT_HISTORY_SIZE: Final[int] = int(os.getenv("MOSHPRO_BEAT_HISTORY_SIZE", "10"))

# ────────────────────────────────────────────────────────────────────────────
# SPECTRAL ANALYSIS (STFT)
# ────────────────────────────────────────────────────────────────────────────

# STFT FFT size (number of points)
# Larger = better frequency resolution, worse time resolution
# 2048 @ 44.1kHz = 46.4ms, ~21.5Hz per bin (good balance)
STFT_FFT_SIZE: Final[int] = int(os.getenv("MOSHPRO_STFT_FFT_SIZE", "2048"))

# STFT hop length (samples between frames)
# hop_length = fft_size / 4 gives 75% overlap, 25% new data per frame
# 512 @ 44.1kHz = 11.6ms between STFT frames
STFT_HOP_LENGTH: Final[int] = int(os.getenv("MOSHPRO_STFT_HOP_LENGTH", "512"))

# STFT window function
STFT_WINDOW: Final[str] = os.getenv("MOSHPRO_STFT_WINDOW", "hann")

# ────────────────────────────────────────────────────────────────────────────
# FREQUENCY BANDS (for spectral analysis)
# ────────────────────────────────────────────────────────────────────────────

# Bass frequency band (Hz)
FREQ_BAND_BASS_MIN: Final[float] = 20.0
FREQ_BAND_BASS_MAX: Final[float] = 250.0

# Mid frequency band (Hz)
FREQ_BAND_MID_MIN: Final[float] = 250.0
FREQ_BAND_MID_MAX: Final[float] = 4000.0

# High frequency band (Hz)
FREQ_BAND_HIGH_MIN: Final[float] = 4000.0
FREQ_BAND_HIGH_MAX: Final[float] = 20000.0

# ────────────────────────────────────────────────────────────────────────────
# PIPELINE THREADING
# ────────────────────────────────────────────────────────────────────────────

# Number of parallel audio processing workers
# More workers = higher CPU but better parallelization
# Typical: 2-4 for low-power, 4-8 for high-power
NUM_PROCESSING_WORKERS: Final[int] = int(
    os.getenv("MOSHPRO_PROCESSING_WORKERS", "4")
)

# Output queue maximum size
# Larger = more buffering, higher latency tolerance
OUTPUT_QUEUE_MAXSIZE: Final[int] = int(os.getenv("MOSHPRO_QUEUE_MAXSIZE", "10"))

# ────────────────────────────────────────────────────────────────────────────
# AUDIO INPUT DEFAULTS
# ────────────────────────────────────────────────────────────────────────────

# Default sample rate for USB audio input
USB_DEFAULT_SAMPLE_RATE: Final[int] = int(os.getenv("MOSHPRO_USB_SAMPLE_RATE", "48000"))

# Default sample rate for loopback/stereo mix
LOOPBACK_DEFAULT_SAMPLE_RATE: Final[int] = int(
    os.getenv("MOSHPRO_LOOPBACK_SAMPLE_RATE", "44100")
)

# ────────────────────────────────────────────────────────────────────────────
# ONSET & BEAT DETECTION THRESHOLDS
# ────────────────────────────────────────────────────────────────────────────

# Energy rise threshold for onset detection (0-1 normalized)
# How much energy rise counts as an "onset"
ONSET_THRESHOLD: Final[float] = float(os.getenv("MOSHPRO_ONSET_THRESHOLD", "0.3"))

# Beat confidence threshold (0-1)
# How confident we need to be before reporting a beat
BEAT_CONFIDENCE_THRESHOLD: Final[float] = float(
    os.getenv("MOSHPRO_BEAT_CONFIDENCE_THRESHOLD", "0.6")
)

# Silence threshold (0-1 normalized energy)
# Energy below this is considered silence
SILENCE_THRESHOLD: Final[float] = float(os.getenv("MOSHPRO_SILENCE_THRESHOLD", "0.05"))

# ────────────────────────────────────────────────────────────────────────────
# LOGGING & DEBUG
# ────────────────────────────────────────────────────────────────────────────

# Default logging level
LOG_LEVEL: Final[str] = os.getenv("MOSHPRO_LOG_LEVEL", "INFO")

# Enable debug logging for workers
DEBUG_WORKERS: Final[bool] = os.getenv("MOSHPRO_DEBUG_WORKERS", "").lower() == "true"

# Enable debug logging for analysis
DEBUG_ANALYSIS: Final[bool] = os.getenv("MOSHPRO_DEBUG_ANALYSIS", "").lower() == "true"


# ────────────────────────────────────────────────────────────────────────────
# COMPUTED VALUES (derived from settings above)
# ────────────────────────────────────────────────────────────────────────────
# Note: Conversion helpers removed as they were unused. Use the constants directly
# and calculate: samples = int(window_ms * sample_rate / 1000)
