"""Real-time audio analysis engine.

Capture thread -> ring buffer -> real-time thread (every hop) + scheduled
background jobs (dynamics, BPM, key) -> FeatureCache -> GUI / local API.
"""

from .pipeline import AudioPipeline, FeatureCache, prewarm_job_processes
from .base import Worker
from .buffer import RingBuffer
from .capture_worker import AudioCaptureWorker
from .realtime import BeatTracker, RealtimeAnalyzer, RealtimeWorker
from .scheduler import AnalysisJob, JobScheduler, ProcessPoolSpec
from .performance import PerformanceMonitor, get_performance_monitor, timer
from src.analysis import FastFeatures, MediumFeatures, SlowFeatures
from .tiered_rendering import (
    TieredRenderingMessage,
    combine_features,
)
from .events import (
    EventType,
    AudioEvent,
    ContinuousSignals,
    AudioFrame,
    merge_frames,
)

__all__ = [
    "AudioPipeline",
    "FeatureCache",
    "prewarm_job_processes",
    "Worker",
    "RingBuffer",
    "AudioCaptureWorker",
    "RealtimeAnalyzer",
    "RealtimeWorker",
    "BeatTracker",
    "AnalysisJob",
    "JobScheduler",
    "ProcessPoolSpec",
    "PerformanceMonitor",
    "get_performance_monitor",
    "timer",
    "FastFeatures",
    "MediumFeatures",
    "SlowFeatures",
    "TieredRenderingMessage",
    "combine_features",
    "EventType",
    "AudioEvent",
    "ContinuousSignals",
    "AudioFrame",
    "merge_frames",
]
