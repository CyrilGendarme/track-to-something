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
# Increased to 44100 for better frequency resolution and tonality detection
DEFAULT_SAMPLE_RATE: Final[int] = int(os.getenv("MOSHPRO_SAMPLE_RATE", "44100"))

# Audio chunk size for capture workers (samples per chunk)
# Affects latency (smaller = lower latency, higher CPU)
# ~2048 samples @ 44.1kHz = ~46ms capture latency
# Increased sample rate to 44100 Hz, chunk size adjusted for ~23ms latency
AUDIO_CHUNK_SIZE: Final[int] = int(os.getenv("MOSHPRO_CHUNK_SIZE", "64"))

# ────────────────────────────────────────────────────────────────────────────
# AUDIO QUALITY REDUCTION (for lightweight analysis)
# ────────────────────────────────────────────────────────────────────────────

# Audio bit depth for processing (12-bit is sufficient for beat detection)
# 16-bit: CD quality, 12-bit: good enough for analysis, 8-bit: only if desperate
# Reducing from 16 to 12 saves 25% memory with no analysis quality loss
AUDIO_BIT_DEPTH: Final[int] = int(os.getenv("MOSHPRO_BIT_DEPTH", "12"))

# Process mono (single channel) or stereo?
# Mono: 50% less memory, identical analysis results for beat/onset/spectral
# Stereo: Richer stereo imaging, but 2x memory and mixing overhead
# Recommended: 1 (mono) for low-latency video control
AUDIO_CHANNELS: Final[int] = int(os.getenv("MOSHPRO_CHANNELS", "1"))

# Apply high-pass filter to remove low-frequency rumble below 20 Hz?
# Recommended: True (removes DC offset, wind noise, low-freq vibration)
# CPU cost: Minimal (~0.1ms per chunk), quality benefit: high
AUDIO_APPLY_HPF: Final[bool] = os.getenv("MOSHPRO_APPLY_HPF", "true").lower() == "true"

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
# Latency: ~150ms (increased from 100ms for better tonality/tempo stability)
# Use for: Tempo tracking, scene changes, stability metrics
# More history helps tonality detection converge to true key without jitter
SLOW_WINDOW_MS: Final[float] = float(os.getenv("MOSHPRO_SLOW_WINDOW_MS", "150.0"))

# Beat/Tempo analysis window (for BPM calculation)
# CRITICAL: Must be MUCH LONGER than other windows to capture multiple beats
# At 120 BPM: beats every ~500ms → need 2+ seconds for 4+ beats
# At 100 BPM: beats every ~600ms → need 2.4+ seconds for 4+ beats
# 5000ms (5 seconds) = ~10 beats at 120 BPM = excellent BPM stability
# Separate from SLOW_WINDOW_MS because beat patterns span multiple STFT windows
BEAT_ANALYSIS_WINDOW_MS: Final[float] = float(os.getenv("MOSHPRO_BEAT_ANALYSIS_WINDOW_MS", "5000.0"))

# Tonality detection history size (number of detected keys to smooth)
# Higher = more stable but slower to adapt to key changes
# 12 detected keys = ~500-700ms of smoothing at 20Hz update rate
# Best range: 10-15 for music with stable keys
TONALITY_HISTORY_SIZE: Final[int] = int(os.getenv("MOSHPRO_TONALITY_HISTORY_SIZE", "12"))

# ────────────────────────────────────────────────────────────────────────────
# ANALYSIS TIER DECIMATION FACTORS
# ────────────────────────────────────────────────────────────────────────────
# Only do expensive analyses every N chunks to reduce CPU load
# FAST (every chunk): amplitude, beat, onset → ~5-10ms
# MEDIUM (every 2-3 chunks): spectral analysis, bands → ~20-50ms
# SLOW (every 8+ chunks): tempo estimation → ~300-700ms

# Spectral analysis (STFT, centroid, frequency bands) every N chunks
# Set to 1: run STFT on every chunk for maximum tonality accuracy
# CPU cost is acceptable; better key detection is worth it
SPECTRAL_ANALYSIS_DECIMATION: Final[int] = int(os.getenv("MOSHPRO_SPECTRAL_DECIMATION", "1"))

# Tempo estimation every N chunks (avoid constantly recalculating BPM)
# Set to 4: run every 4 chunks for more frequent tempo/key analysis
# Better tonality smoothing with more frequent updates
TEMPO_ANALYSIS_DECIMATION: Final[int] = int(os.getenv("MOSHPRO_TEMPO_DECIMATION", "4"))

# ────────────────────────────────────────────────────────────────────────────
# SPECTRAL ANALYSIS (STFT)
# ────────────────────────────────────────────────────────────────────────────

# STFT FFT size (number of points)
# Increased to 1024 for better frequency resolution
# 1024 @ 44.1kHz = ~23ms, 43Hz per bin (excellent for tonality detection and frequency bands)
# Better frequency detail for accurate key detection with minimal latency cost
STFT_FFT_SIZE: Final[int] = int(os.getenv("MOSHPRO_STFT_FFT_SIZE", "1024"))

# STFT hop length (samples between frames)
# Set to 512 (50% overlap with new FFT_SIZE=1024)
# 512 @ 44.1kHz = ~11.6ms between STFT frames (same temporal resolution)
# Maintains smooth spectral tracking with better frequency detail
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
# Restored to 20000: With sample rate @ 44100 Hz, Nyquist is 22050 Hz
# Full frequency range available for accurate analysis
FREQ_BAND_HIGH_MIN: Final[float] = 4000.0
FREQ_BAND_HIGH_MAX: Final[float] = 20000.0

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
# TONALITY ANALYSIS (Musical Key Detection)
# ────────────────────────────────────────────────────────────────────────────

# Number of previous tonality detections to keep for smoothing
# Higher = more stable key (less jitter) but slower response to key changes
# Default 15 = ~0.5-1s of history (with ~30-40ms analysis updates)
TONALITY_HISTORY_SIZE: Final[int] = int(os.getenv("MOSHPRO_TONALITY_HISTORY_SIZE", "15"))

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
# LOCAL ANALYSIS API (HTTP + WebSocket for other local apps to consume data)
# ────────────────────────────────────────────────────────────────────────────

# Bind address for the local API server. Defaults to loopback-only so the
# analysis data isn't exposed to the network unless explicitly reconfigured.
API_HOST: Final[str] = os.getenv("MOSHPRO_API_HOST", "127.0.0.1")

# Port for the local API server (HTTP GET endpoints + /ws WebSocket stream)
API_PORT: Final[int] = int(os.getenv("MOSHPRO_API_PORT", "8765"))

# How often the WebSocket endpoint broadcasts the latest snapshot (seconds)
API_BROADCAST_INTERVAL_S: Final[float] = float(os.getenv("MOSHPRO_API_BROADCAST_INTERVAL_S", "0.1"))


# ────────────────────────────────────────────────────────────────────────────
# COMPUTED VALUES (derived from settings above)
# ────────────────────────────────────────────────────────────────────────────
# Note: Conversion helpers removed as they were unused. Use the constants directly
# and calculate: samples = int(window_ms * sample_rate / 1000)
