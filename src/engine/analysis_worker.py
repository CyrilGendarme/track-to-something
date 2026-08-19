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
        """Analyze audio features and separate EVENTS from CONTINUOUS SIGNALS.
        
        ═══════════════════════════════════════════════════════════════════════
        ARCHITECTURE: Events vs Continuous Signals
        ═══════════════════════════════════════════════════════════════════════
        
        CONTINUOUS SIGNALS (drive smooth animations):
        - bass_energy: 0.0-1.0 (bass intensity)
        - mid_energy: 0.0-1.0 (vocal/presence energy)
        - high_energy: 0.0-1.0 (brightness/air)
        - spectral_centroid: Hz (overall tone color)
        - overall_amplitude: 0.0-1.0 (volume)
        - rms, peak, dynamics: stability metrics
        
        EVENTS (instantaneous, time-bound):
        - onset_detected: bool (attack/transient)
        - beat_detected: bool (kick/bass peak)
        - tempo_stable: bool (BPM confidence)
        
        This separation allows:
        1. Events to drive quick, discrete visual effects
        2. Continuous values to drive smooth parameter changes
        3. Predictive animations ahead of actual beats
        """
        perf = get_performance_monitor()
        process_start = time.perf_counter()
        
        # 1. Extract CONTINUOUS SIGNALS
        with perf.timing_context("analysis:continuous_signals"):
            continuous_signals = {
                "bass": item.bass_energy,           # 0-1
                "mid": item.mid_energy,              # 0-1
                "high": item.high_energy,            # 0-1
                # REMOVED: spectral_centroid_hz (not used in visualization, 2-4ms saved)
                "amplitude": item.overall_amplitude, # 0-1 (volume envelope)
                "rms": item.rms,                     # 0-1 (smooth volume)
                "peak": item.peak,                   # 0-1 (transient spikes)
            }
        
        # 2. Detect EVENTS
        with perf.timing_context("analysis:event_detection"):
            events = []
            
            # Event: Onset (transient attack)
            if item.onset_detected:
                events.append({
                    "type": "onset",
                    "timestamp": item.timestamp_s,
                    "strength": item.peak,  # Use peak as intensity
                })
                self._record_event("onset", {"timestamp": item.timestamp_s})
                if self.event_callback:
                    self.event_callback("onset", {"timestamp": item.timestamp_s})
            
            # Event: Beat (bass/energy peak)
            if item.beat_detected and not self.prev_beat_detected:
                beat_event_data = {
                    "type": "beat",
                    "timestamp": item.timestamp_s,
                    "confidence": item.beat_confidence,
                }
                events.append(beat_event_data)
                self._record_event("beat", beat_event_data)
                self.beat_predictor.record_beat(item.timestamp_s)
                if self.event_callback:
                    self.event_callback("beat", beat_event_data)
            
            # Event: Tempo/BPM update (only when available)
            if item.bpm is not None:
                events.append({
                    "type": "tempo_update",
                    "timestamp": item.timestamp_s,
                    "bpm": item.bpm,
                })
        
        # 3. Beat Phase & Prediction (for smooth animation)
        with perf.timing_context("analysis:beat_prediction"):
            predicted_next_beat, prediction_confidence = self.beat_predictor.predict_next_beat(item.timestamp_s)
            beat_phase = self.beat_predictor.get_beat_phase(item.timestamp_s)
        
        # 4. Create RENDERING MESSAGE (combination of events + continuous)
        with perf.timing_context("analysis:render_message_creation"):
            # Brightness: derived from spectral centroid (REMOVED for performance)
            # Setting to fixed value based on high energy as approximation
            brightness = item.high_energy  # Use high energy as brightness proxy
            
            # Overall energy normalization
            overall_energy = max(item.bass_energy, item.mid_energy, item.high_energy)
            
            # Dynamics: RMS/Peak ratio (high when sound is compressed)
            dynamics = item.rms / (item.peak + 1e-10)
            
            # Rendering message with both CONTINUOUS and EVENT data
            render_msg = RenderingMessage(
                # CONTINUOUS SIGNALS (for smooth animation)
                timestamp_s=item.timestamp_s,
                bass=item.bass_energy,              # 0-1 (smooth)
                energy=overall_energy,              # 0-1 (smooth)
                brightness=brightness,              # 0-1 (spectral centroid)
                impact=item.overall_amplitude,      # 0-1 (volume)
                dynamics=min(1.0, dynamics),        # 0-1 (compression)
                
                # EVENTS (instantaneous detections)
                beat=item.beat_detected,
                beat_confidence=item.beat_confidence,
                onset=item.onset_detected,
                tempo_bpm=item.bpm,
                
                # PREDICTIVE BEAT SYNC
                beat_phase_0to1=beat_phase,         # 0=just beat, 1=next beat arriving
                predicted_beat_timestamp_s=predicted_next_beat,
                prediction_confidence=prediction_confidence,
            )
        
        with perf.timing_context("analysis:queue_put"):
            self.output_queue.put(render_msg)
        
        self.prev_beat_detected = item.beat_detected
        
        # Log timing periodically
        if not hasattr(self, '_item_count'):
            self._item_count = 0
        self._item_count += 1
        if self._item_count % 200 == 0:
            process_duration_ms = (time.perf_counter() - process_start) * 1000
            events_str = f", {len(events)} events" if events else ", no events"
            logger.debug(f"[{self.name}] Item {self._item_count}: {process_duration_ms:.2f}ms{events_str}")

    def _record_event(self, event_type: str, data: dict) -> None:
        """Record an event in history."""
        self.event_history.append((data.get("timestamp", 0.0), event_type))
