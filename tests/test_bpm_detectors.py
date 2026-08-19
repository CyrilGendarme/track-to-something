"""Correctness tests for the multi-method BPM detectors.

Uses synthetic signals (band-limited kick pulses at a known, exact BPM) so
the expected answer is unambiguous. Only the always-available methods are
checked for accuracy; optional third-party methods are checked only for
graceful "unavailable" degradation.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.analysis.bpm_detectors import (
    AUBIO_AVAILABLE,
    ESSENTIA_AVAILABLE,
    MADMOM_AVAILABLE,
    BPMEstimate,
    MultiMethodBPMAnalyzer,
    consensus_bpm,
    detect_comb_filter_bank,
    detect_dynamic_kick_band,
    detect_kick_band_autocorrelation,
    detect_librosa_beat_track,
    detect_librosa_onset_tempogram,
)

SAMPLE_RATE = 22050


def _make_click_track(bpm: float, duration_s: float = 10.0, sr: int = SAMPLE_RATE, kick_hz: float = 60.0) -> np.ndarray:
    """Synthesize a perfectly steady click track: short decaying sine bursts
    at ``kick_hz`` (typical kick fundamental), spaced exactly at ``bpm``.
    """
    n_samples = int(duration_s * sr)
    y = np.zeros(n_samples, dtype=np.float64)
    interval_s = 60.0 / bpm
    burst_len = int(0.08 * sr)  # 80ms decaying burst
    t_burst = np.arange(burst_len) / sr
    envelope = np.exp(-t_burst * 40.0)
    burst = np.sin(2 * np.pi * kick_hz * t_burst) * envelope

    beat_time = 0.0
    while beat_time < duration_s:
        start = int(beat_time * sr)
        end = min(n_samples, start + burst_len)
        y[start:end] += burst[: end - start]
        beat_time += interval_s

    # A little broadband noise so envelopes aren't degenerate constant signals.
    rng = np.random.default_rng(42)
    y += rng.normal(scale=0.01, size=n_samples)
    return y.astype(np.float32)


@pytest.mark.parametrize("true_bpm", [100.0, 128.0, 174.0])
def test_kick_band_autocorrelation_matches_known_bpm(true_bpm: float) -> None:
    y = _make_click_track(true_bpm)
    estimate = detect_kick_band_autocorrelation(y, SAMPLE_RATE)
    assert estimate.bpm is not None, estimate.error
    assert abs(estimate.bpm - true_bpm) < 2.0


@pytest.mark.parametrize("true_bpm", [100.0, 128.0, 174.0])
def test_dynamic_kick_band_matches_known_bpm(true_bpm: float) -> None:
    y = _make_click_track(true_bpm)
    estimate = detect_dynamic_kick_band(y, SAMPLE_RATE)
    assert estimate.bpm is not None, estimate.error
    assert abs(estimate.bpm - true_bpm) < 2.0
    assert abs(estimate.extra["kick_frequency_hz"] - 60.0) < 15.0


@pytest.mark.parametrize("true_bpm", [100.0, 128.0, 174.0])
def test_comb_filter_bank_matches_known_bpm(true_bpm: float) -> None:
    y = _make_click_track(true_bpm)
    estimate = detect_comb_filter_bank(y, SAMPLE_RATE)
    assert estimate.bpm is not None, estimate.error
    assert abs(estimate.bpm - true_bpm) < 1.0


@pytest.mark.parametrize("true_bpm", [100.0, 128.0, 174.0])
def test_librosa_beat_track_matches_known_bpm(true_bpm: float) -> None:
    y = _make_click_track(true_bpm)
    estimate = detect_librosa_beat_track(y, SAMPLE_RATE)
    assert estimate.bpm is not None, estimate.error
    # librosa's beat tracker occasionally locks onto a half/double tempo.
    ratio = estimate.bpm / true_bpm
    closest_octave_error = min(abs(ratio - 1.0), abs(ratio - 0.5), abs(ratio - 2.0))
    assert closest_octave_error < 0.05


@pytest.mark.parametrize("true_bpm", [100.0, 128.0, 174.0])
def test_librosa_onset_tempogram_matches_known_bpm(true_bpm: float) -> None:
    y = _make_click_track(true_bpm)
    estimate = detect_librosa_onset_tempogram(y, SAMPLE_RATE)
    assert estimate.bpm is not None, estimate.error
    ratio = estimate.bpm / true_bpm
    closest_octave_error = min(abs(ratio - 1.0), abs(ratio - 0.5), abs(ratio - 2.0))
    assert closest_octave_error < 0.05


def test_optional_detectors_report_unavailable_when_not_installed() -> None:
    from src.analysis.bpm_detectors import detect_aubio_tempo, detect_essentia_rhythm_extractor, detect_madmom_dbn

    y = _make_click_track(128.0, duration_s=3.0)
    if not AUBIO_AVAILABLE:
        estimate = detect_aubio_tempo(y, SAMPLE_RATE)
        assert estimate.available is False
    if not MADMOM_AVAILABLE:
        estimate = detect_madmom_dbn(y, SAMPLE_RATE)
        assert estimate.available is False
    if not ESSENTIA_AVAILABLE:
        estimate = detect_essentia_rhythm_extractor(y, SAMPLE_RATE)
        assert estimate.available is False


def test_multi_method_analyzer_runs_all_detectors_in_parallel() -> None:
    y = _make_click_track(128.0)
    analyzer = MultiMethodBPMAnalyzer()
    try:
        results = analyzer.analyze(y, SAMPLE_RATE)
        assert "kick_band_autocorr" in results
        assert "librosa_beat_track" in results
        assert all(name in results for name in analyzer.detectors)
    finally:
        analyzer.shutdown()


def test_consensus_bpm_combines_available_estimates() -> None:
    y = _make_click_track(128.0)
    analyzer = MultiMethodBPMAnalyzer()
    try:
        results = analyzer.analyze(y, SAMPLE_RATE)
        bpm, confidence = consensus_bpm(results)
        assert bpm is not None
        assert 100.0 < bpm < 160.0
        assert 0.0 <= confidence <= 1.0
    finally:
        analyzer.shutdown()


def _estimate(method: str, bpm: float, confidence: float) -> BPMEstimate:
    return BPMEstimate(method=method, bpm=bpm, confidence=confidence)


def test_consensus_bpm_takes_single_high_confidence_estimate() -> None:
    estimates = {
        "a": _estimate("a", 128.0, 0.97),
        "b": _estimate("b", 90.0, 0.4),
        "c": _estimate("c", 174.0, 0.2),
    }
    bpm, confidence = consensus_bpm(estimates)
    assert bpm == pytest.approx(128.0)
    assert confidence == pytest.approx(0.97)


def test_consensus_bpm_averages_multiple_high_confidence_estimates() -> None:
    estimates = {
        "a": _estimate("a", 128.0, 0.96),
        "b": _estimate("b", 130.0, 0.99),
        "c": _estimate("c", 60.0, 0.1),
    }
    bpm, confidence = consensus_bpm(estimates)
    assert bpm == pytest.approx(129.0)
    assert confidence == pytest.approx(0.975)


def test_consensus_bpm_relaxes_threshold_when_nothing_meets_it() -> None:
    estimates = {
        "a": _estimate("a", 128.0, 0.88),
        "b": _estimate("b", 90.0, 0.3),
    }
    # Nothing clears 0.95 or 0.90, first match is at threshold 0.85.
    bpm, confidence = consensus_bpm(estimates)
    assert bpm == pytest.approx(128.0)
    assert confidence == pytest.approx(0.88)


def test_consensus_bpm_returns_none_when_no_estimates_available() -> None:
    estimates = {
        "a": BPMEstimate(method="a", bpm=None, confidence=0.0, available=False, error="not installed"),
    }
    bpm, confidence = consensus_bpm(estimates)
    assert bpm is None
    assert confidence == 0.0
