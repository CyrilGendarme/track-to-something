"""Real-time audio analysis engine with multi-threaded pipeline."""

from .pipeline import AudioPipeline, FeatureCache
from .base import Worker, QueuedWorker
from .messages import AudioChunkMessage, AudioFeaturesMessage, RenderingMessage
from .buffer import CircularAudioBuffer
from .capture_worker import AudioCaptureWorker
from .processing_worker import AudioProcessingWorker, BeatPredictor
from .analysis_worker import AnalysisWorker
from .rendering_worker import RenderingWorker
from .bpm_worker import BPMAnalysisWorker
from .performance import PerformanceMonitor, get_performance_monitor, timer
from src.analysis import (
    FastAnalyzer,
    MediumAnalyzer,
    SlowAnalyzer,
    MultiWindowAudioAnalyzer,
    FastFeatures,
    MediumFeatures,
    SlowFeatures,
)
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
    "AudioCaptureWorker",
    "AudioProcessingWorker",
    "AnalysisWorker",
    "RenderingWorker",
    "BPMAnalysisWorker",
    "BeatPredictor",
    "CircularAudioBuffer",
    "AudioChunkMessage",
    "AudioFeaturesMessage",
    "RenderingMessage",
    "Worker",
    "QueuedWorker",
    "PerformanceMonitor",
    "get_performance_monitor",
    "timer",
    "FastAnalyzer",
    "MediumAnalyzer",
    "SlowAnalyzer",
    "MultiWindowAudioAnalyzer",
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

