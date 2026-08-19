"""Analysis worker - interprets audio features and detects events."""

from __future__ import annotations

import logging
import time
from collections import deque
from queue import Queue
from typing import Callable, Deque

from src.engine.base import QueuedWorker
from src.engine.messages import AudioFeaturesMessage, RenderingMessage
from src.engine.processing_worker import BeatPredictor
from src.engine.performance import get_performance_monitor

logger = logging.getLogger(__name__)


class AnalysisWorker(QueuedWorker):
    """Interprets audio features and detects events."""

    def __init__(
        self,
        name: str,
        input_queue: Queue,
        output_queue: Queue,
        event_callback: Callable[[str, dict], None] | None = None,
        daemon: bool = False,
    ):
        """Initialize analysis worker.
        
        Args:
            name: Worker thread name
            input_queue: Queue receiving AudioFeaturesMessage
            output_queue: Queue to send analysis results to
            event_callback: Callback for detected events (event_type, data)
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, input_queue=input_queue, daemon=daemon)
        self.output_queue = output_queue
        self.event_callback = event_callback
        self.prev_beat_detected = False
        self.event_history: Deque[tuple[float, str]] = deque(maxlen=100)
        self.beat_predictor = BeatPredictor(max_history=10)  # For predictive sync

    def _process_item(self, item: AudioFeaturesMessage) -> None:
        """Analyze audio features, detect events, and create rendering message."""
        perf = get_performance_monitor()
        process_start = time.perf_counter()
        
        # 1. Detect beat transitions
        with perf.timing_context("analysis:beat_detection"):
            beat_event = item.beat_detected and not self.prev_beat_detected
            if beat_event:
                self._record_event("beat", {"timestamp": item.timestamp_s, "confidence": item.beat_confidence})
                # Feed beat to predictor for future anticipation
                self.beat_predictor.record_beat(item.timestamp_s)
                if self.event_callback:
                    self.event_callback("beat", {"timestamp": item.timestamp_s, "confidence": item.beat_confidence})
        
        # 2. Detect onsets/attacks
        with perf.timing_context("analysis:onset_detection"):
            if item.onset_detected:
                self._record_event("onset", {"timestamp": item.timestamp_s})
                if self.event_callback:
                    self.event_callback("onset", {"timestamp": item.timestamp_s})
        
        # 3. Detect transients (loud peaks)
        with perf.timing_context("analysis:transient_detection"):
            if item.peak > 0.8:
                self._record_event("transient", {"timestamp": item.timestamp_s, "peak": item.peak})
                if self.event_callback:
                    self.event_callback("transient", {"timestamp": item.timestamp_s, "peak": item.peak})
        
        # 4. PREDICTIVE BEAT SYNCHRONIZATION
        # Instead of just reacting to beats, predict when the next one arrives
        with perf.timing_context("analysis:beat_prediction"):
            predicted_next_beat, prediction_confidence = self.beat_predictor.predict_next_beat(item.timestamp_s)
            beat_phase = self.beat_predictor.get_beat_phase(item.timestamp_s)
        
        # 5. Create simplified rendering message
        with perf.timing_context("analysis:render_message_creation"):
            # Normalize spectral centroid to 0-1 (20Hz to 20kHz is typical range)
            brightness = 0.0
            if item.spectral_centroid_hz is not None:
                # Map 20-20000 Hz to 0-1
                brightness = max(0.0, min(1.0, (item.spectral_centroid_hz - 20) / (20000 - 20)))
            
            # Overall energy normalization
            overall_energy = max(item.bass_energy, item.mid_energy, item.high_energy)
            
            # Dynamics: RMS/Peak ratio (high when sound is compressed)
            dynamics = item.rms / (item.peak + 1e-10)
            
            # Rendering message with normalized values + predictive beat sync
            render_msg = RenderingMessage(
                timestamp_s=item.timestamp_s,
                bass=item.bass_energy,  # 0-1
                energy=overall_energy,  # 0-1
                brightness=brightness,  # 0-1 (spectral centroid)
                impact=item.overall_amplitude,  # 0-1 (peak amplitude)
                beat=item.beat_detected,
                beat_confidence=item.beat_confidence,
                onset=item.onset_detected,
                tempo_bpm=item.bpm,
                dynamics=min(1.0, dynamics),  # 0-1
                # PREDICTIVE SYNC FIELDS
                beat_phase_0to1=beat_phase,  # 0=just beat, 1=next beat arriving
                predicted_beat_timestamp_s=predicted_next_beat,
                prediction_confidence=prediction_confidence,
            )
        
        with perf.timing_context("analysis:queue_put"):
            self.output_queue.put(render_msg)
        
        self.prev_beat_detected = item.beat_detected
        
        # Log timing every 100 items
        if not hasattr(self, '_item_count'):
            self._item_count = 0
        self._item_count += 1
        if self._item_count % 100 == 0:
            process_duration_ms = (time.perf_counter() - process_start) * 1000
            logger.debug(f"[{self.name}] Item {self._item_count}: {process_duration_ms:.2f}ms")

    def _record_event(self, event_type: str, data: dict) -> None:
        """Record an event in history."""
        self.event_history.append((data.get("timestamp", 0.0), event_type))
