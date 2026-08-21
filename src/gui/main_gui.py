"""Main GUI application for audio analysis."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import logging
from threading import Thread
from typing import Optional, Callable

from src.config import DEFAULT_SAMPLE_RATE, FREQ_BAND_BASS_MIN, FREQ_BAND_BASS_MAX, FREQ_BAND_HIGH_MAX, API_HOST, API_PORT
from src.engine import AudioPipeline, FeatureCache, get_performance_monitor
from src.sources import AudioInputSource, ApplicationAudioSource, AudioChunk
from src.gui.theme import apply_theme, BG, BG_PANEL, BG_CARD, FG, FG_DIM, ACCENT, ACCENT2, FONT_UI, FONT_BOLD, FONT_TITLE
from src.gui.audio_devices import get_available_audio_devices, get_running_applications, AudioDevice
from src.gui.analysis_logger import AnalysisLogger
from src.gui.metrics_display import RealTimeMetricsDisplay
from src.analysis.tiers.features import FastFeatures, MediumFeatures, SlowFeatures
from src.api import AnalysisAPIServer

logger = logging.getLogger(__name__)


class FrequencyRangeSelector(ttk.Frame):
    """Widget for selecting a frequency range with sliders."""
    
    def __init__(self, parent: tk.Widget, title: str = "Frequency Range", **kwargs):
        """Initialize the frequency range selector.
        
        Args:
            parent: Parent tkinter widget
            title: Label for this selector
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)
        self.title = title
        self.min_hz = 20
        self.max_hz = 20000
        
        # Title
        title_label = ttk.Label(self, text=title, font=FONT_BOLD)
        title_label.pack(anchor=tk.W, padx=5, pady=(5, 0))
        
        # Min frequency
        min_frame = ttk.Frame(self)
        min_frame.pack(fill=tk.X, padx=10, pady=3)
        
        ttk.Label(min_frame, text="Min (Hz):", width=12, font=FONT_UI).pack(side=tk.LEFT)
        
        self.min_var = tk.DoubleVar(value=FREQ_BAND_BASS_MIN)
        self.min_scale = ttk.Scale(
            min_frame,
            from_=20,
            to=10000,
            variable=self.min_var,
            orient=tk.HORIZONTAL,
            command=self._on_min_change,
        )
        self.min_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.min_label = ttk.Label(min_frame, text=f"{self.min_var.get():.0f} Hz", width=10, font=FONT_UI)
        self.min_label.pack(side=tk.LEFT)
        
        # Max frequency
        max_frame = ttk.Frame(self)
        max_frame.pack(fill=tk.X, padx=10, pady=3)
        
        ttk.Label(max_frame, text="Max (Hz):", width=12, font=FONT_UI).pack(side=tk.LEFT)
        
        self.max_var = tk.DoubleVar(value=FREQ_BAND_HIGH_MAX)
        self.max_scale = ttk.Scale(
            max_frame,
            from_=100,
            to=20000,
            variable=self.max_var,
            orient=tk.HORIZONTAL,
            command=self._on_max_change,
        )
        self.max_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.max_label = ttk.Label(max_frame, text=f"{self.max_var.get():.0f} Hz", width=10, font=FONT_UI)
        self.max_label.pack(side=tk.LEFT)
        
        # Range info
        info_frame = ttk.Frame(self)
        info_frame.pack(fill=tk.X, padx=10, pady=3)
        
        self.range_label = ttk.Label(
            info_frame,
            text=f"Range: {self.min_var.get():.0f} - {self.max_var.get():.0f} Hz",
            font=FONT_UI,
            foreground=FG_DIM,
        )
        self.range_label.pack(anchor=tk.W)
    
    def _on_min_change(self, value):
        """Handle minimum frequency slider change."""
        min_val = float(value)
        max_val = self.max_var.get()
        
        # Ensure min < max
        if min_val >= max_val:
            self.min_var.set(max_val - 100)
            min_val = self.min_var.get()
        
        self.min_label.config(text=f"{min_val:.0f} Hz")
        self.range_label.config(text=f"Range: {min_val:.0f} - {max_val:.0f} Hz")
    
    def _on_max_change(self, value):
        """Handle maximum frequency slider change."""
        max_val = float(value)
        min_val = self.min_var.get()
        
        # Ensure max > min
        if max_val <= min_val:
            self.max_var.set(min_val + 100)
            max_val = self.max_var.get()
        
        self.max_label.config(text=f"{max_val:.0f} Hz")
        self.range_label.config(text=f"Range: {min_val:.0f} - {max_val:.0f} Hz")
    
    def get_range(self) -> tuple[float, float]:
        """Get the selected frequency range.
        
        Returns:
            (min_hz, max_hz) tuple
        """
        return (self.min_var.get(), self.max_var.get())


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
        
        # Performance info frame
        perf_frame = ttk.LabelFrame(self, text="Performance", padding=10)
        perf_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.perf_labels = {
            "chunks": ttk.Label(perf_frame, text="Chunks Processed: 0", font=FONT_UI),
            "latency": ttk.Label(perf_frame, text="Avg Latency: 0.0ms", font=FONT_UI),
            "uptime": ttk.Label(perf_frame, text="Uptime: 0.0s", font=FONT_UI),
        }
        
        for label in self.perf_labels.values():
            label.pack(anchor=tk.W, pady=2)
    
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
    
    def update_performance(self, chunks: int, avg_latency_ms: float, uptime_s: float) -> None:
        """Update performance metrics.
        
        Args:
            chunks: Number of chunks processed
            avg_latency_ms: Average latency in milliseconds
            uptime_s: Pipeline uptime in seconds
        """
        self.perf_labels["chunks"].config(text=f"Chunks Processed: {chunks}")
        self.perf_labels["latency"].config(text=f"Avg Latency: {avg_latency_ms:.2f}ms")
        self.perf_labels["uptime"].config(text=f"Uptime: {uptime_s:.1f}s")


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
        
        self.freq_range_selector = FrequencyRangeSelector(freq_frame)
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
        
        # Start periodic metrics update
        self._update_metrics_display()
        
        # Event callback for pipeline
        self.event_count = 0
        self.chunk_count = 0
    
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
                    block_size=2048,
                )
            else:
                audio_source = AudioInputSource(
                    device=self.selected_device.device_id,
                    sample_rate=self.selected_device.sample_rate,
                    block_size=2048,
                )
            
            # Create pipeline (shares the persistent feature_cache so the
            # local API keeps serving data across start/stop cycles)
            self.pipeline = AudioPipeline(
                audio_source=lambda: audio_source,
                n_processing_workers=4,
                sample_rate=self.selected_device.sample_rate,
                event_callback=self._on_pipeline_event,
                feature_cache=self.feature_cache,
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
        try:
            self.pipeline.start()
            self.pipeline.wait()
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
        finally:
            self.control_panel._on_stop_click()
    
    def _on_stop_analysis(self) -> None:
        """Stop the audio analysis pipeline."""
        if self.pipeline:
            self.pipeline.stop()
            self.pipeline = None
            
            # Show performance summary
            perf = get_performance_monitor()
            self.analysis_logger.log_result(
                operation="Pipeline Stopped",
                value=0.0,
                latency_ms=0.0,
                frequency_range="--",
            )
    
    def _update_metrics_display(self) -> None:
        """Periodically update metrics display with latest features from pipeline."""
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
        
        # Update the metrics display
        self.metrics_display.update_features(
            self.last_fast_features,
            self.last_medium_features,
            self.last_slow_features,
        )
        self.metrics_display.update_bpm_estimates(self.last_bpm_estimates)
        
        # Schedule next update (every 100ms = ~10 FPS)
        self.after(100, self._update_metrics_display)
    
    def _on_pipeline_event(self, event_type: str, data: dict) -> None:
        """Handle events from the pipeline.
        
        Args:
            event_type: Type of event
            data: Event data dictionary
        """
        self.event_count += 1
        self.analysis_logger.log_event(event_type, data)


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
