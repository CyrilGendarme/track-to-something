"""Main GUI application for audio analysis."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import logging
import math
import queue
from threading import Thread
from typing import Optional, Callable

from src.config import AUDIO_BLOCK_SIZE, JOBS_USE_PROCESSES, API_HOST, API_PORT
from src.engine import AudioPipeline, FeatureCache, prewarm_job_processes
from src.sources import AudioInputSource, ApplicationAudioSource, AudioChunk
from src.gui.theme import apply_theme, BG, BG_PANEL, BG_CARD, FG, FG_DIM, ACCENT, ACCENT2, FONT_UI, FONT_BOLD, FONT_TITLE
from src.gui.audio_devices import get_available_audio_devices, get_running_applications, AudioDevice
from src.gui.analysis_logger import AnalysisLogger
from src.gui.metrics_display import RealTimeMetricsDisplay
from src.analysis.tiers.features import FastFeatures, MediumFeatures, SlowFeatures
from src.api import AnalysisAPIServer

logger = logging.getLogger(__name__)

# The Performance panel refreshes every this many display updates (~0.5 s)
PERF_REFRESH_TICKS = 10
# Input level warning threshold. Music normally sits around -30..-10 dBFS;
# near the silence gate (SILENCE_RMS, -60 dBFS) kicks are ignored, so there is
# no beat phase or lock and the level meters stay at their floor.
QUIET_DBFS = -45.0


class FrequencyRangeSelector(ttk.Frame):
    """Custom band picker: two log-scale sliders and an on/off switch.

    Calls ``on_change((low_hz, high_hz))`` when the band changes, or
    ``on_change(None)`` when it is switched off.
    """

    MIN_HZ = 20.0
    MAX_HZ = 20000.0
    MIN_RATIO = 1.1  # keep the band at least ~1/6 octave wide

    def __init__(
        self,
        parent: tk.Widget,
        on_change: Callable[[tuple[float, float] | None], None] | None = None,
        **kwargs,
    ):
        """Initialize the frequency range selector.

        Args:
            parent: Parent tkinter widget
            on_change: Callback with the new band, or None when disabled
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)
        self.on_change = on_change

        self.enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self, text="Track this band (Custom Band meter)", variable=self.enabled_var, command=self._notify
        ).pack(anchor=tk.W, padx=5, pady=(0, 3))

        # Defaults: the kick range, a common first choice
        self.min_var = tk.DoubleVar(value=self._to_pos(40.0))
        self.max_var = tk.DoubleVar(value=self._to_pos(120.0))
        self.min_label = self._slider_row("Min:", self.min_var, self._on_min_change)
        self.max_label = self._slider_row("Max:", self.max_var, self._on_max_change)
        self._refresh_labels()

    def _slider_row(self, text: str, var: tk.DoubleVar, command: Callable[[str], None]) -> ttk.Label:
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=10, pady=3)
        ttk.Label(row, text=text, width=6, font=FONT_UI).pack(side=tk.LEFT)
        ttk.Scale(row, from_=0.0, to=1.0, variable=var, orient=tk.HORIZONTAL, command=command).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=5
        )
        label = ttk.Label(row, width=9, font=FONT_UI)
        label.pack(side=tk.LEFT)
        return label

    # Slider position (0-1) <-> frequency, logarithmic like the ear
    @classmethod
    def _to_hz(cls, pos: float) -> float:
        return cls.MIN_HZ * (cls.MAX_HZ / cls.MIN_HZ) ** pos

    @classmethod
    def _to_pos(cls, hz: float) -> float:
        return math.log(hz / cls.MIN_HZ) / math.log(cls.MAX_HZ / cls.MIN_HZ)

    def _on_min_change(self, _value: str) -> None:
        low, high = self.get_range()
        if low * self.MIN_RATIO > high:
            self.min_var.set(self._to_pos(high / self.MIN_RATIO))
        self._changed()

    def _on_max_change(self, _value: str) -> None:
        low, high = self.get_range()
        if low * self.MIN_RATIO > high:
            self.max_var.set(self._to_pos(min(low * self.MIN_RATIO, self.MAX_HZ)))
        self._changed()

    def _changed(self) -> None:
        self._refresh_labels()
        if self.enabled_var.get():
            self._notify()

    def _refresh_labels(self) -> None:
        low, high = self.get_range()
        self.min_label.config(text=_format_hz(low))
        self.max_label.config(text=_format_hz(high))

    def _notify(self) -> None:
        if self.on_change:
            self.on_change(self.get_band())

    def get_range(self) -> tuple[float, float]:
        """The slider positions as (min_hz, max_hz), whether enabled or not."""
        return (self._to_hz(self.min_var.get()), self._to_hz(self.max_var.get()))

    def get_band(self) -> tuple[float, float] | None:
        """The selected band, or None when the custom band is switched off."""
        return self.get_range() if self.enabled_var.get() else None


def _format_hz(hz: float) -> str:
    return f"{hz / 1000:.1f} kHz" if hz >= 1000 else f"{hz:.0f} Hz"


class AudioInputSelector(ttk.Frame):
    """Widget for selecting an audio input device."""
    
    def __init__(self, parent: tk.Widget, on_selection_change: Callable[[AudioDevice], None] | None = None, **kwargs):
        """Initialize the audio input selector.
        
        Args:
            parent: Parent tkinter widget
            on_selection_change: Callback when selection changes
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)
        self.on_selection_change = on_selection_change
        self.selected_device: Optional[AudioDevice] = None
        
        # Title
        title_label = ttk.Label(self, text="Audio Input", font=FONT_BOLD)
        title_label.pack(anchor=tk.W, padx=5, pady=(5, 0))
        
        # Device dropdown frame
        dropdown_frame = ttk.Frame(self)
        dropdown_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Label
        ttk.Label(dropdown_frame, text="Device:", font=FONT_UI).pack(side=tk.LEFT, padx=(0, 5))
        
        # Combo box - lists audio devices AND running applications' audio sessions
        self.devices = self._load_devices()
        self.device_names = [str(d) for d in self.devices]
        
        self.combo = ttk.Combobox(
            dropdown_frame,
            values=self.device_names,
            state="readonly",
            width=50,
            font=FONT_UI,
        )
        self.combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.combo.bind("<<ComboboxSelected>>", self._on_selection)
        
        # Set default selection
        if self.devices:
            self.combo.current(0)
            self.selected_device = self.devices[0]
        
        # Refresh button
        refresh_btn = ttk.Button(dropdown_frame, text="🔄 Refresh", command=self._refresh_devices, width=12)
        refresh_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Device info frame
        info_frame = ttk.LabelFrame(self, text="Device Info", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.info_labels = {
            "channels": ttk.Label(info_frame, text="Channels: -", font=FONT_UI),
            "sample_rate": ttk.Label(info_frame, text="Sample Rate: -", font=FONT_UI),
            "type": ttk.Label(info_frame, text="Type: -", font=FONT_UI),
        }
        
        for label in self.info_labels.values():
            label.pack(anchor=tk.W, pady=2)
        
        # Update info for selected device
        self._update_device_info()
    
    def _load_devices(self) -> list[AudioDevice]:
        """List audio devices followed by running applications' audio sessions."""
        return get_available_audio_devices() + get_running_applications()
    
    def _on_selection(self, event) -> None:
        """Handle device selection change."""
        index = self.combo.current()
        if 0 <= index < len(self.devices):
            self.selected_device = self.devices[index]
            self._update_device_info()
            if self.on_selection_change:
                self.on_selection_change(self.selected_device)
    
    def _update_device_info(self) -> None:
        """Update device info labels."""
        if self.selected_device:
            self.info_labels["channels"].config(text=f"Channels: {self.selected_device.channels}")
            self.info_labels["sample_rate"].config(text=f"Sample Rate: {self.selected_device.sample_rate} Hz")
            self.info_labels["type"].config(text=f"Type: {self.selected_device.device_type.upper()}")
    
    def _refresh_devices(self) -> None:
        """Refresh the device list (audio devices + running applications)."""
        self.devices = self._load_devices()
        self.device_names = [str(d) for d in self.devices]
        self.combo.config(values=self.device_names)
        
        if self.devices:
            self.combo.current(0)
            self.selected_device = self.devices[0]
            self._update_device_info()
    
    def get_selected_device(self) -> Optional[AudioDevice]:
        """Get the currently selected device.
        
        Returns:
            Selected AudioDevice or None
        """
        return self.selected_device


class AnalysisControlPanel(ttk.Frame):
    """Control panel for analysis settings and pipeline control."""

    PERF_ROWS = {
        "input": "Input level",
        "uptime": "Uptime",
        "load": "Real-time load",
        "backlog": "Backlog (max)",
        "age": "Audio age",
        "overflows": "Driver overflows",
        "jobs": "Jobs",
    }
    
    def __init__(self, parent: tk.Widget, on_start: Callable | None = None, on_stop: Callable | None = None, **kwargs):
        """Initialize the control panel.
        
        Args:
            parent: Parent tkinter widget
            on_start: Callback when Start is clicked
            on_stop: Callback when Stop is clicked
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)
        self.on_start = on_start
        self.on_stop = on_stop
        self.pipeline_running = False
        
        # Title
        title_label = ttk.Label(self, text="Analysis Control", font=FONT_BOLD)
        title_label.pack(anchor=tk.W, padx=5, pady=(5, 0))
        
        # Button frame
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Status indicator
        self.status_var = tk.StringVar(value="● Idle")
        self.status_label = ttk.Label(
            button_frame,
            textvariable=self.status_var,
            font=FONT_UI,
            foreground="#3ddc97",
        )
        self.status_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Start button
        self.start_button = ttk.Button(
            button_frame,
            text="▶ Start Analysis",
            command=self._on_start_click,
            width=20,
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Stop button
        self.stop_button = ttk.Button(
            button_frame,
            text="⏹ Stop Analysis",
            command=self._on_stop_click,
            width=20,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Performance info frame (filled from AudioPipeline.stats())
        perf_frame = ttk.LabelFrame(self, text="Performance", padding=10)
        perf_frame.pack(fill=tk.X, padx=10, pady=5)

        self.perf_labels = {
            key: ttk.Label(perf_frame, text=f"{title}: -", font=FONT_UI)
            for key, title in self.PERF_ROWS.items()
        }
        for label in self.perf_labels.values():
            label.pack(anchor=tk.W, pady=1)

    def _on_start_click(self) -> None:
        """Handle Start button click."""
        self.pipeline_running = True
        self.status_var.set("● Running")
        self.status_label.config(foreground="#3ddc97")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        if self.on_start:
            self.on_start()
    
    def _on_stop_click(self) -> None:
        """Handle Stop button click."""
        self.pipeline_running = False
        self.status_var.set("● Idle")
        self.status_label.config(foreground="#f0a500")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        if self.on_stop:
            self.on_stop()
    
    def update_performance(self, stats: dict) -> None:
        """Show a snapshot from :meth:`AudioPipeline.stats`."""
        load = stats["load"]
        overflows = stats["overflows"]
        jobs = "  ".join(
            f"{name} {job['last_compute_s'] * 1000:.0f}ms" + (f" ({job['skipped']} skipped)" if job["skipped"] else "")
            for name, job in stats["jobs"].items() if job["runs"]
        )
        hops = f"{stats['hops_processed']} hops"
        if stats["hops_skipped"]:
            hops += f", {stats['hops_skipped']} skipped"
        input_dbfs = stats["input_dbfs"]
        input_note = "  (very quiet: is the music reaching this input?)" if input_dbfs < QUIET_DBFS else ""
        rows = {
            "input": f"{input_dbfs:.0f} dBFS{input_note}",
            "uptime": f"{stats['uptime_s']:.0f} s  ({hops})",
            "load": f"{load * 100:.1f}% of real time" + ("  (too slow!)" if load > 0.8 else ""),
            "backlog": f"{stats['backlog_s'] * 1000:.0f} ms  ({stats['max_backlog_s'] * 1000:.0f} ms)",
            "age": f"{stats['audio_age_s'] * 1000:.0f} ms",
            "overflows": "-" if overflows is None else str(overflows),
            "jobs": jobs or "waiting for audio",
        }
        for key, text in rows.items():
            self.perf_labels[key].config(text=f"{self.PERF_ROWS[key]}: {text}")
        self.perf_labels["input"].config(foreground="#e05555" if input_note else FG)


class LocalApiPanel(ttk.Frame):
    """Toggle for the local HTTP/WebSocket API - independent of analysis start/stop.

    Other local apps can read the same analysis data the GUI displays,
    whether or not the audio pipeline itself is currently running.
    """

    def __init__(
        self,
        parent: tk.Widget,
        on_toggle: Callable[[bool], str | None] | None = None,
        host: str = API_HOST,
        port: int = API_PORT,
        **kwargs,
    ):
        """Initialize the local API panel.

        Args:
            parent: Parent tkinter widget
            on_toggle: Callback(enabled) -> error message, or None on success
            host: API host to display
            port: API port to display
        """
        super().__init__(parent, **kwargs)
        self.on_toggle = on_toggle
        self.host = host
        self.port = port

        title_label = ttk.Label(self, text="Local API", font=FONT_BOLD)
        title_label.pack(anchor=tk.W, padx=5, pady=(5, 0))

        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=10, pady=5)

        self.enabled_var = tk.BooleanVar(value=False)
        self.checkbox = ttk.Checkbutton(
            row, text="Enable Local API", variable=self.enabled_var, command=self._on_toggle
        )
        self.checkbox.pack(side=tk.LEFT, padx=(0, 10))

        self.status_label = ttk.Label(row, text="Disabled", font=FONT_UI, foreground=FG_DIM)
        self.status_label.pack(side=tk.LEFT)

        url_label = ttk.Label(
            self,
            text=f"http://{host}:{port}  (GET /features, /features/bpm, WS /ws)",
            font=FONT_UI,
            foreground=FG_DIM,
        )
        url_label.pack(anchor=tk.W, padx=10, pady=(0, 5))

    def _on_toggle(self) -> None:
        enabled = self.enabled_var.get()
        error = self.on_toggle(enabled) if self.on_toggle else None
        if error:
            self.enabled_var.set(not enabled)
            self.status_label.config(text=f"Error: {error}", foreground="#e05555")
            return
        if enabled:
            self.status_label.config(text=f"Running on {self.host}:{self.port}", foreground=ACCENT)
        else:
            self.status_label.config(text="Disabled", foreground=FG_DIM)



class AudioAnalysisGUI(tk.Tk):
    """Main GUI application for audio analysis."""
    
    def __init__(self):
        """Initialize the main GUI window."""
        super().__init__()
        
        self.title("Audio Analysis Monitor - MoshPro")
        self.geometry("1400x900")
        self.minsize(1000, 700)
        
        # Apply theme
        apply_theme(self)
        
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Main container
        main_frame = ttk.Frame(self)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="🎵 Real-Time Audio Analysis Pipeline",
            font=FONT_TITLE,
        )
        title_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        # Left panel (controls)
        left_panel = ttk.Frame(main_frame)
        left_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        left_panel.grid_rowconfigure(3, weight=1)
        
        # Audio input selector
        self.audio_selector = AudioInputSelector(
            left_panel,
            on_selection_change=self._on_audio_device_change,
        )
        self.audio_selector.pack(fill=tk.X, padx=0, pady=(0, 10))
        
        # Frequency range selector
        freq_frame = ttk.LabelFrame(left_panel, text="Custom Frequency Range", padding=10)
        freq_frame.pack(fill=tk.X, padx=0, pady=(0, 10))
        
        self.freq_range_selector = FrequencyRangeSelector(freq_frame, on_change=self._on_custom_band_change)
        self.freq_range_selector.pack(fill=tk.X)
        
        # Control panel
        self.control_panel = AnalysisControlPanel(
            left_panel,
            on_start=self._on_start_analysis,
            on_stop=self._on_stop_analysis,
        )
        self.control_panel.pack(fill=tk.X, padx=0)
        
        # Local API toggle (independent of analysis start/stop)
        self.api_panel = LocalApiPanel(left_panel, on_toggle=self._on_toggle_api)
        self.api_panel.pack(fill=tk.X, padx=0, pady=(10, 0))
        
        # Right panel (analysis results)
        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=1, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=2)
        right_panel.grid_columnconfigure(0, weight=1)
        
        # Metrics display (real-time metrics)
        self.metrics_display = RealTimeMetricsDisplay(right_panel)
        self.metrics_display.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 5))
        
        # Analysis logger (latency log)
        self.analysis_logger = AnalysisLogger(right_panel)
        self.analysis_logger.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        
        # Pipeline state
        self.pipeline: Optional[AudioPipeline] = None
        self.pipeline_thread: Optional[Thread] = None
        self.selected_device: Optional[AudioDevice] = None
        
        # Start the BPM/key worker processes now: their first-time startup
        # (librosa import) then overlaps with the user picking a device.
        if JOBS_USE_PROCESSES:
            prewarm_job_processes()
        
        # Persistent feature cache: outlives individual pipeline start/stop
        # cycles so the local API can keep serving the latest data regardless
        # of whether analysis is currently running.
        self.feature_cache = FeatureCache()
        self.api_server = AnalysisAPIServer(self.feature_cache)
        
        # Feature tracking
        self.last_fast_features: Optional[FastFeatures] = None
        self.last_medium_features: Optional[MediumFeatures] = None
        self.last_slow_features: Optional[SlowFeatures] = None
        self.last_bpm_estimates: dict = {}
        
        # Work posted by pipeline threads, run on the Tk thread by the
        # periodic update loop (Tk widgets must only be touched from here)
        self._ui_queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self.event_count = 0
        self._perf_tick = 0
        
        # Start periodic metrics update
        self._update_metrics_display()
    
    def _on_toggle_api(self, enabled: bool) -> Optional[str]:
        """Start or stop the local API server.
        
        Args:
            enabled: True to start the server, False to stop it
            
        Returns:
            An error message on failure, or None on success
        """
        try:
            if enabled:
                self.api_server.start()
            else:
                self.api_server.stop()
            return None
        except Exception as e:
            logger.error(f"Error toggling local API: {e}")
            return str(e)
    
    def _on_custom_band_change(self, band: tuple[float, float] | None) -> None:
        """Apply the custom band to the running pipeline (the next start uses it too)."""
        if self.pipeline is not None:
            self.pipeline.set_custom_band(*(band or (None, None)))

    def _on_audio_device_change(self, device: AudioDevice) -> None:
        """Handle audio device selection change.
        
        Args:
            device: The selected AudioDevice
        """
        self.selected_device = device
        self.analysis_logger.log_result(
            operation="Device Changed",
            value=device.device_id,
            latency_ms=0.0,
            frequency_range="--",
        )
    
    def _on_start_analysis(self) -> None:
        """Start the audio analysis pipeline."""
        if not self.selected_device:
            logger.error("No audio device selected")
            return
        
        try:
            # Create audio source: a running application uses whole-system
            # loopback (see ApplicationAudioSource), everything else is a
            # regular input/loopback device.
            if self.selected_device.device_type == "application":
                audio_source = ApplicationAudioSource(
                    application_name=self.selected_device.application_name,
                    sample_rate=self.selected_device.sample_rate,
                    block_size=AUDIO_BLOCK_SIZE,
                )
            else:
                audio_source = AudioInputSource(
                    device=self.selected_device.device_id,
                    sample_rate=self.selected_device.sample_rate,
                    block_size=AUDIO_BLOCK_SIZE,
                )
            
            # Create pipeline (shares the persistent feature_cache so the
            # local API keeps serving data across start/stop cycles)
            self.pipeline = AudioPipeline(
                audio_source=lambda: audio_source,
                sample_rate=self.selected_device.sample_rate,
                event_callback=self._on_pipeline_event,
                feature_cache=self.feature_cache,
                custom_band_hz=self.freq_range_selector.get_band(),
            )
            
            # Start pipeline in separate thread
            self.pipeline_thread = Thread(target=self._run_pipeline, daemon=True)
            self.pipeline_thread.start()
            
            self.analysis_logger.log_result(
                operation="Pipeline Started",
                value=1.0,
                latency_ms=0.0,
                frequency_range="--",
            )
            
        except Exception as e:
            logger.error(f"Error starting analysis: {e}")
            self.analysis_logger.log_result(
                operation="Pipeline Error",
                value=0.0,
                latency_ms=0.0,
                frequency_range="--",
            )
            self.control_panel._on_stop_click()
    
    def _run_pipeline(self) -> None:
        """Run the pipeline (called in separate thread)."""
        pipeline = self.pipeline
        try:
            pipeline.start()
            pipeline.wait()
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
        finally:
            # Reset the controls on the Tk thread, unless the user already
            # stopped (or restarted) analysis
            def on_ended() -> None:
                if self.pipeline is pipeline:
                    self.control_panel._on_stop_click()
            self._ui_queue.put(on_ended)
    
    def _on_stop_analysis(self) -> None:
        """Stop the audio analysis pipeline."""
        if self.pipeline:
            self.pipeline.stop()
            self.pipeline = None
            
            self.analysis_logger.log_result(
                operation="Pipeline Stopped",
                value=0.0,
                latency_ms=0.0,
                frequency_range="--",
            )
    
    def _update_metrics_display(self) -> None:
        """Periodically update metrics display with latest features from pipeline."""
        self._drain_ui_queue()
        if self.pipeline and self.pipeline.is_running():
            # Get latest features from pipeline cache (thread-safe)
            fast, medium, slow = self.pipeline.feature_cache.get_all()
            
            if fast or medium or slow:
                self.last_fast_features = fast
                self.last_medium_features = medium
                self.last_slow_features = slow
            
            bpm_estimates = self.pipeline.feature_cache.get_bpm_estimates()
            if bpm_estimates:
                self.last_bpm_estimates = bpm_estimates

            self._perf_tick = (self._perf_tick + 1) % PERF_REFRESH_TICKS
            if self._perf_tick == 0:
                self.control_panel.update_performance(self.pipeline.stats())
        
        # Update the metrics display
        self.metrics_display.update_features(
            self.last_fast_features,
            self.last_medium_features,
            self.last_slow_features,
        )
        self.metrics_display.update_bpm_estimates(self.last_bpm_estimates)
        
        # Schedule next update (every 50ms = ~20 FPS)
        self.after(50, self._update_metrics_display)
    
    def _drain_ui_queue(self) -> None:
        """Run work posted by pipeline threads (on the Tk thread)."""
        while True:
            try:
                task = self._ui_queue.get_nowait()
            except queue.Empty:
                return
            try:
                task()
            except Exception:  # noqa: BLE001 - keep the update loop alive
                logger.exception("UI task failed")
    
    def _on_pipeline_event(self, event_type: str, data: dict) -> None:
        """Handle events from the pipeline (called from the real-time thread).
        
        Args:
            event_type: Type of event
            data: Event data dictionary
        """
        def log() -> None:
            self.event_count += 1
            self.analysis_logger.log_event(event_type, data)
        self._ui_queue.put(log)


def launch_gui() -> None:
    """Launch the audio analysis GUI application."""
    app = AudioAnalysisGUI()
    app.mainloop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    launch_gui()
