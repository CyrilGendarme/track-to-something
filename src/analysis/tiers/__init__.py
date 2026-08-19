"""Tiered audio analysis - multiple overlapping analysis windows at different time scales.

This module provides:
- Fast analyzer: 5-10ms latency for immediate transient detection
- Medium analyzer: 20-50ms latency for smooth energy tracking
- Slow analyzer: 100-500ms latency for overall dynamics and tempo

Each analyzer produces typed feature objects suitable for different use cases.
"""

from .features import FastFeatures, MediumFeatures, SlowFeatures
from .fast import FastAnalyzer
from .medium import MediumAnalyzer
from .slow import SlowAnalyzer

__all__ = [
    # Feature dataclasses
    "FastFeatures",
    "MediumFeatures",
    "SlowFeatures",
    # Analyzer classes
    "FastAnalyzer",
    "MediumAnalyzer",
    "SlowAnalyzer",
]
