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
# Bass-heavy / Electronic Music (recommended for you?) -> 22050
# 2️Balanced (vocals, acoustic) -> 32000
#  Full fidelity (classical, orchestral) -> 44100
DEFAULT_SAMPLE_RATE: Final[int] = int(os.getenv("MOSHPRO_SAMPLE_RATE", "22050"))

# Audio chunk size for capture workers (samples per chunk)
# Affects latency (smaller = lower latency, higher CPU)
# ~2048 samples @ 44.1kHz = ~46ms capture latency
# A lower DEFAULT_SAMPLE_RATE allows for smaller chunk sizes without increasing CPU load.
# ~256 samples @ 22.05kHz = ~11.6ms capture latency
AUDIO_CHUNK_SIZE: Final[int] = int(os.getenv("MOSHPRO_CHUNK_SIZE", "256"))

# ────────────────────────────────────────────────────────────────────────────
# CIRCULAR BUFFER (shared between analyzer tiers)
# ────────────────────────────────────────────────────────────────────────────

# Circular buffer capacity in seconds
# Holds audio history for multi-window analysis
# 0.5s is sufficient for video effects (real-time lighting needs <500ms lookback)
# Reduced from 5.0s for lower memory footprint and latency
BUFFER_CAPACITY_SECONDS: Final[float] = float(
    os.getenv("MOSHPRO_BUFFER_CAPACITY_SECONDS", "0.5")
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
# Latency: 50-150ms (reduced from 250ms for video sync responsiveness)
# Use for: Tempo tracking, scene changes, stability metrics
# Note: 250ms lag is perceptible on screen; video effects need <100ms
SLOW_WINDOW_MS: Final[float] = float(os.getenv("MOSHPRO_SLOW_WINDOW_MS", "100.0"))

# Max beat history for tempo/BPM estimation
# More history = more stable tempo but slower adaptation
# Reduced from 10 to 6: video effects need quick tempo adaptation over perfect stability
BEAT_HISTORY_SIZE: Final[int] = int(os.getenv("MOSHPRO_BEAT_HISTORY_SIZE", "6"))

# ────────────────────────────────────────────────────────────────────────────
# ANALYSIS TIER DECIMATION FACTORS
# ────────────────────────────────────────────────────────────────────────────
# Only do expensive analyses every N chunks to reduce CPU load
# FAST (every chunk): amplitude, beat, onset → ~5-10ms
# MEDIUM (every 2-3 chunks): spectral analysis, bands → ~20-50ms
# SLOW (every 8+ chunks): tempo estimation → ~300-700ms

# Spectral analysis (STFT, centroid, frequency bands) every N chunks
# Reduced from 4 to 2: run STFT every 2 chunks (~23ms latency) for snappy video response
# Trade: ~50% higher CPU for STFT, but lighting effects sync better to music transients
SPECTRAL_ANALYSIS_DECIMATION: Final[int] = int(os.getenv("MOSHPRO_SPECTRAL_DECIMATION", "2"))

# Tempo estimation every N chunks (avoid constantly recalculating BPM)
# Default: 8 = run every 8 chunks (~370ms latency, stable estimation)
TEMPO_ANALYSIS_DECIMATION: Final[int] = int(os.getenv("MOSHPRO_TEMPO_DECIMATION", "8"))

# ────────────────────────────────────────────────────────────────────────────
# SPECTRAL ANALYSIS (STFT)
# ────────────────────────────────────────────────────────────────────────────

# STFT FFT size (number of points)
# Reduced from 1024 to 512 for 2x faster FFT computation
# 512 @ 22.05kHz = ~23ms, 86Hz per bin (sufficient for electronic music bass/mid/high bands)
# Trade: Less frequency detail (86 Hz/bin vs 43 Hz/bin) for 30% faster STFT
STFT_FFT_SIZE: Final[int] = int(os.getenv("MOSHPRO_STFT_FFT_SIZE", "512"))

# STFT hop length (samples between frames)
# Reduced from 512 to 256 to maintain 50% overlap with new FFT_SIZE=512
# 256 @ 22.05kHz = 11.6ms between STFT frames (same temporal resolution as before)
# Ensures smooth spectral tracking without extra CPU cost from increased hop
STFT_HOP_LENGTH: Final[int] = int(os.getenv("MOSHPRO_STFT_HOP_LENGTH", "256"))

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
# Changed from 20000 to 11000: Nyquist frequency @ 22050 Hz is 11025 Hz (max analyzable)
# Audio above 11025 Hz doesn't exist in signal; capped at 11000 for safety
FREQ_BAND_HIGH_MIN: Final[float] = 4000.0
FREQ_BAND_HIGH_MAX: Final[float] = 11000.0

# ────────────────────────────────────────────────────────────────────────────
# PIPELINE THREADING
# ────────────────────────────────────────────────────────────────────────────

# Number of parallel audio processing workers
# More workers = higher CPU but worse GIL contention with tiered analysis
# With TIERED ANALYSIS decimation, 1-2 workers handles most load efficiently
# Reduced from 3 to 2: with decimation strategy, 3 workers cause GIL contention
# Each worker handles FAST/MEDIUM/SLOW tiers with 2-8x decimation
NUM_PROCESSING_WORKERS: Final[int] = int(
    os.getenv("MOSHPRO_PROCESSING_WORKERS", "2")
)

# Output queue maximum size
# Reduced from 10 to 5: less buffering = faster response for video effects
# Queuing many frames adds latency; prefer dropping frames over lag
OUTPUT_QUEUE_MAXSIZE: Final[int] = int(os.getenv("MOSHPRO_QUEUE_MAXSIZE", "5"))



# ────────────────────────────────────────────────────────────────────────────
# ONSET & BEAT DETECTION THRESHOLDS
# ────────────────────────────────────────────────────────────────────────────

# Energy rise threshold for onset detection (0-1 normalized)
# Reduced from 0.5 to 0.35: catch quieter transients for snappier beat detection
# Electronic music has varied dynamic range; lower threshold catches more kick/synth hits
ONSET_THRESHOLD: Final[float] = float(os.getenv("MOSHPRO_ONSET_THRESHOLD", "0.35"))

# Beat confidence threshold (0-1)
# How confident we need to be before reporting a beat
BEAT_CONFIDENCE_THRESHOLD: Final[float] = float(
    os.getenv("MOSHPRO_BEAT_CONFIDENCE_THRESHOLD", "0.6")
)

# Silence threshold (0-1 normalized energy)
# Energy below this is considered silence
SILENCE_THRESHOLD: Final[float] = float(os.getenv("MOSHPRO_SILENCE_THRESHOLD", "0.1"))

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
