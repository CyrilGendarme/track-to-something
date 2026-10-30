"""Feature dataclasses - the output contract of the analysis pipeline.

- FastFeatures / MediumFeatures: produced by the real-time path every hop
- SlowFeatures: assembled from the scheduled background jobs
"""

from .features import FastFeatures, MediumFeatures, SlowFeatures

__all__ = [
    "FastFeatures",
    "MediumFeatures",
    "SlowFeatures",
]
