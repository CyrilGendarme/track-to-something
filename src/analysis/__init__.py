"""Audio feature extraction for sources exposed by :mod:`src.sources`."""

from .audio_analyzer import AudioAnalysis, AudioAnalyzer, FrequencyBandFeatures
from .multi_window_analyzer import (
    FastAnalyzer,
    MediumAnalyzer,
    SlowAnalyzer,
    MultiWindowAudioAnalyzer,
    FastFeatures,
    MediumFeatures,
    SlowFeatures,
)
from .bpm_detectors import BPMEstimate, MultiMethodBPMAnalyzer, consensus_bpm

__all__ = [
    "AudioAnalysis",
    "AudioAnalyzer",
    "FrequencyBandFeatures",
    "FastAnalyzer",
    "MediumAnalyzer",
    "SlowAnalyzer",
    "MultiWindowAudioAnalyzer",
    "FastFeatures",
    "MediumFeatures",
    "SlowFeatures",
    "BPMEstimate",
    "MultiMethodBPMAnalyzer",
    "consensus_bpm",
]