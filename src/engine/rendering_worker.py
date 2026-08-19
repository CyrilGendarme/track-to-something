"""Rendering worker - renders analysis results for display/game integration."""

from __future__ import annotations

import logging
import time
from queue import Queue

from src.engine.base import QueuedWorker
from src.engine.messages import RenderingMessage
from src.engine.performance import get_performance_monitor

logger = logging.getLogger(__name__)


class RenderingWorker(QueuedWorker):
    """Renders analysis results for display/game integration."""

    def __init__(
        self,
        name: str,
        input_queue: Queue,
        daemon: bool = False,
    ):
        """Initialize rendering worker.
        
        Args:
            name: Worker thread name
            input_queue: Queue receiving RenderingMessage
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, input_queue=input_queue, daemon=daemon)
        self.frame_count = 0
        self.last_log_time = 0.0

    def _process_item(self, item: RenderingMessage) -> None:
        """Process and render simplified audio data."""
        perf = get_performance_monitor()
        render_start = time.perf_counter()
        
        self.frame_count += 1
        
        with perf.timing_context("render:logging"):
            # Log periodic updates showing the rendering format + predictive sync
            if item.timestamp_s - self.last_log_time > 1.0:  # Log once per second
                beat_str = "♪ BEAT" if item.beat else "     "
                onset_str = "▲ ONSET" if item.onset else "       "
                
                # Display beat phase with visual progress bar
                phase_bar_length = int(item.beat_phase_0to1 * 10)
                phase_bar = "█" * phase_bar_length + "░" * (10 - phase_bar_length)
                
                # Show prediction if available
                pred_str = ""
                if item.predicted_beat_timestamp_s is not None:
                    pred_delta = item.predicted_beat_timestamp_s - item.timestamp_s
                    pred_str = f" | PRED: {pred_delta:+.2f}s (conf={item.prediction_confidence:.2f})"
                
                line = (
                    f"[{self.name}] {beat_str} {onset_str} [{phase_bar}] | "
                    f"bass={item.bass:.2f} energy={item.energy:.2f} brightness={item.brightness:.2f} impact={item.impact:.2f}"
                    f"{pred_str}"
                )
                try:
                    print(line)
                except UnicodeEncodeError:
                    # Some Windows consoles (cp1252) can't render the unicode
                    # note/block characters above - fall back to ASCII-safe output.
                    print(line.encode("ascii", errors="replace").decode("ascii"))
                self.last_log_time = item.timestamp_s
        
        # PREDICTIVE SYNC - Use beat phase for anticipatory rendering
        # Example: Trigger animation at phase=0.9 instead of waiting for beat=true
        # if item.beat_phase_0to1 > 0.9 and item.prediction_confidence > 0.7:
        #     game.pre_trigger_animation("kick")  # 100ms early
        
        # This is where you would integrate with:
        # - Game engines (update shader parameters, trigger animations)
        # - UI frameworks (update visualizers, progress indicators)
        # - Audio effects (modulate effects based on beat/energy)
        # - Network streaming (send normalized values to clients)
        # - File output (record feature timeseries)
        
        # Log timing every 500 frames
        if self.frame_count % 500 == 0:
            render_duration_ms = (time.perf_counter() - render_start) * 1000
            logger.debug(f"[{self.name}] Frame {self.frame_count}: {render_duration_ms:.2f}ms")
        # 
        # EXAMPLE 1: Game engine - Anticipatory animation
        # if item.beat_phase_0to1 > 0.85:  # ~150ms before next beat
        #     if item.prediction_confidence > 0.7:
        #         game.trigger_animation("jump")  # Triggers early, not late
        #
        # EXAMPLE 2: Shader parameters with beat prediction
        # shader.set_param("u_beat_phase", item.beat_phase_0to1)
        # shader.set_param("u_predicted_beat", item.predicted_beat_timestamp_s)
        #
        # EXAMPLE 3: Tight rhythm game sync
        # if item.beat_phase_0to1 > 0.95:  # ~50ms before beat
        #     if item.prediction_confidence > 0.8:
        #         game.expect_player_input()  # Prepare for input window
        #
        # EXAMPLE 4: Smooth interpolation between beats
        # progress = item.beat_phase_0to1  # 0 to 1 between beats
        # animation_progress = ease_in_out_cubic(progress)  # Smooth curve
        # object.position = lerp(start, end, animation_progress)
