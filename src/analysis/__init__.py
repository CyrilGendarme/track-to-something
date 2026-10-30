"""Audio feature extraction for sources exposed by :mod:`src.sources`."""

from .audio_analyzer import AudioAnalysis, AudioAnalyzer, FrequencyBandFeatures
from .tiers import FastFeatures, MediumFeatures, SlowFeatures
from .bpm_detectors import BPMEstimate, MultiMethodBPMAnalyzer, analyze_all_methods, consensus_bpm
from .dynamics import DynamicsResult, analyze_dynamics
from .key_detection import KeyEstimate, KeySmoother, detect_key

__all__ = [
    "AudioAnalysis",
    "AudioAnalyzer",
    "FrequencyBandFeatures",
    "FastFeatures",
    "MediumFeatures",
    "SlowFeatures",
    "BPMEstimate",
    "MultiMethodBPMAnalyzer",
    "analyze_all_methods",
    "consensus_bpm",
    "DynamicsResult",
    "analyze_dynamics",
    "KeyEstimate",
    "KeySmoother",
    "detect_key",
]
