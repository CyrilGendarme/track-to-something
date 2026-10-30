"""Dynamics job: levels, spectral balance and energy trend over a few seconds.

Pure function of an audio window so it can run in any executor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as scipy_signal

from src.config import (
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_BASS_MIN,
    FREQ_BAND_HIGH_MAX,
    FREQ_BAND_HIGH_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_MID_MIN,
)

ENVELOPE_POINTS = 20


@dataclass(frozen=True)
class DynamicsResult:
    """Window-level loudness and spectral balance."""

    overall_amplitude: float
    rms: float
    peak: float
    spectral_density_low: float
    spectral_density_mid: float
    spectral_density_high: float
    energy_variance: float
    energy_trend: float
    band_bass_envelope: tuple[float, ...]
    band_mid_envelope: tuple[float, ...]
    band_high_envelope: tuple[float, ...]


def _resample_envelope(values: np.ndarray, points: int) -> tuple[float, ...]:
    """Average ``values`` into ``points`` equal groups."""
    if values.size == 0:
        return tuple(0.0 for _ in range(points))
    groups = np.array_split(values, min(points, values.size))
    return tuple(float(g.mean()) for g in groups)


def analyze_dynamics(waveform: np.ndarray, sample_rate: int) -> DynamicsResult:
    """Analyze a mono window (typically ~2s)."""
    y = np.asarray(waveform, dtype=np.float64).reshape(-1)
    peak = float(min(1.0, np.max(np.abs(y)))) if y.size else 0.0
    rms = float(min(1.0, np.sqrt(np.mean(y ** 2)))) if y.size else 0.0

    nperseg = min(2048, max(16, y.size))
    freqs, _, spec = scipy_signal.stft(y, fs=sample_rate, nperseg=nperseg, noverlap=nperseg // 2)
    power = np.abs(spec) ** 2  # (freq, frame)

    nyquist = sample_rate / 2.0
    masks = (
        (freqs >= FREQ_BAND_BASS_MIN) & (freqs < FREQ_BAND_BASS_MAX),
        (freqs >= FREQ_BAND_MID_MIN) & (freqs < FREQ_BAND_MID_MAX),
        (freqs >= FREQ_BAND_HIGH_MIN) & (freqs < min(FREQ_BAND_HIGH_MAX, nyquist)),
    )
    band_power = np.stack([power[m].sum(axis=0) for m in masks])  # (3, frame)
    total = float(band_power.sum())
    if total > 1e-12:
        density = band_power.sum(axis=1) / total
    else:
        density = np.full(3, 1.0 / 3.0)

    # Band envelopes over the window, normalized to the loudest point of any band.
    band_amp = np.sqrt(band_power)
    norm = float(band_amp.max()) if band_amp.size and band_amp.max() > 0 else 1.0
    envelopes = [_resample_envelope(band_amp[i] / norm, ENVELOPE_POINTS) for i in range(3)]

    # Frame loudness: variation and trend (relative change per second).
    frame_rms = np.sqrt(power.sum(axis=0))
    mean_rms = float(frame_rms.mean()) if frame_rms.size else 0.0
    if frame_rms.size > 2 and mean_rms > 1e-9:
        energy_variance = float(min(1.0, frame_rms.std() / mean_rms))
        frame_times = np.arange(frame_rms.size) * (nperseg // 2) / sample_rate
        slope = float(np.polyfit(frame_times, frame_rms / mean_rms, 1)[0])
        energy_trend = float(np.clip(slope, -1.0, 1.0))
    else:
        energy_variance = 0.0
        energy_trend = 0.0

    return DynamicsResult(
        overall_amplitude=peak,
        rms=rms,
        peak=peak,
        spectral_density_low=float(density[0]),
        spectral_density_mid=float(density[1]),
        spectral_density_high=float(density[2]),
        energy_variance=energy_variance,
        energy_trend=energy_trend,
        band_bass_envelope=envelopes[0],
        band_mid_envelope=envelopes[1],
        band_high_envelope=envelopes[2],
    )
