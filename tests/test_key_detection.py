"""Tests for musical key detection and smoothing."""

from __future__ import annotations

import numpy as np
import pytest

from src.analysis.key_detection import (
    MAJOR_PROFILE,
    MINOR_PROFILE,
    PITCH_CLASSES,
    KeyEstimate,
    KeySmoother,
    detect_key,
)

SR = 22050


def _tone(midi: int, t: np.ndarray, amp: float = 1.0) -> np.ndarray:
    f = 440.0 * 2 ** ((midi - 69) / 12)
    return amp * sum(np.sin(2 * np.pi * f * h * t) / h for h in (1, 2, 3))


@pytest.mark.parametrize("mode", ["major", "minor"])
@pytest.mark.parametrize("tonic", range(12))
def test_detects_every_key_from_its_profile(tonic: int, mode: str) -> None:
    """Notes weighted by the key profile must come back as exactly that key
    (guards the template rotation direction)."""
    t = np.arange(int(SR * 3)) / SR
    profile = MAJOR_PROFILE if mode == "major" else MINOR_PROFILE
    y = sum(_tone(48 + tonic + i, t, profile[i]) + _tone(60 + tonic + i, t, profile[i]) for i in range(12))
    expected = PITCH_CLASSES[tonic] + ("" if mode == "major" else "m")
    assert detect_key(y, SR).key == expected


@pytest.mark.parametrize("tonic", [0, 2, 7, 9])
def test_detects_key_of_cadence(tonic: int) -> None:
    """I-IV-V-I chord progression."""
    t = np.arange(int(SR * 1.5)) / SR
    root = 60 + tonic

    def chord(r):
        return sum(_tone(r + i, t) for i in (0, 4, 7))

    y = np.concatenate([chord(root), chord(root + 5), chord(root + 7), chord(root)])
    estimate = detect_key(y, SR)
    assert estimate.key == PITCH_CLASSES[tonic]
    assert estimate.confidence > 0.3


def test_silence_has_no_key() -> None:
    estimate = detect_key(np.zeros(SR * 2), SR)
    assert estimate.key is None
    assert estimate.confidence == 0.0


def test_smoother_votes_by_confidence() -> None:
    smoother = KeySmoother(history_size=4)
    smoother.update(KeyEstimate("C", 0.9))
    smoother.update(KeyEstimate("Am", 0.2))
    key, confidence = smoother.update(KeyEstimate("Am", 0.2))
    assert key == "C"
    assert 0.0 < confidence < 0.9
    for _ in range(4):
        key, _ = smoother.update(KeyEstimate("G", 0.8))
    assert key == "G"  # old estimates aged out
