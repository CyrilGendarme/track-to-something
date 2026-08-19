"""Real-time metrics display widget for audio analysis."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from typing import Optional
import threading

from src.analysis.tiers.features import FastFeatures, MediumFeatures, SlowFeatures
from src.gui.theme import BG, BG_PANEL, BG_CARD, FG, FG_DIM, ACCENT, ACCENT2, FONT_UI, FONT_BOLD


@dataclass
class MetricField:
    """Definition of a metric field to display."""
    label: str
    key: str
    category: str  # "fast", "medium", "slow"
    format_str: str = "{:.2f}"
    unit: str = ""
    show_bar: bool = False  # Show progress bar
    bar_max: float = 1.0


class RealTimeMetricsDisplay(ttk.Frame):
    """Display panel showing real-time audio analysis metrics."""
    
    def __init__(self, parent: tk.Widget, **kwargs):
        """Initialize metrics display.
        
        Args:
            parent: Parent tkinter widget
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)
        
        self.fast_features: Optional[FastFeatures] = None
        self.medium_features: Optional[MediumFeatures] = None
        self.slow_features: Optional[SlowFeatures] = None
        self.lock = threading.Lock()
        
        # Define all metrics to display
        self.metrics = {
            # FAST TIER (5-10ms)
            "fast_raw_energy": MetricField("Raw Energy", "raw_energy", "fast", "{:.3f}", "", True, 1.0),
            "fast_onset_strength": MetricField("Onset Strength", "onset_strength", "fast", "{:.3f}", "", True, 1.0),
            "fast_peak_strength": MetricField("Peak Strength", "percussive_peak_strength", "fast", "{:.3f}", "", True, 1.0),
            
            # MEDIUM TIER (20-50ms)
            "medium_bass": MetricField("Bass Energy", "bass_energy", "medium", "{:.3f}", "", True, 1.0),
            "medium_mid": MetricField("Mid Energy", "mid_energy", "medium", "{:.3f}", "", True, 1.0),
            "medium_high": MetricField("High Energy", "high_energy", "medium", "{:.3f}", "", True, 1.0),
            "medium_bass_delta": MetricField("Bass Delta", "bass_energy_delta", "medium", "{:+.3f}", ""),
            
            # SLOW TIER (100-500ms)
            "slow_amplitude": MetricField("Amplitude", "overall_amplitude", "slow", "{:.3f}", "", True, 1.0),
            "slow_rms": MetricField("RMS", "rms", "slow", "{:.3f}", "", True, 1.0),
            "slow_peak": MetricField("Peak", "peak", "slow", "{:.3f}", "", True, 1.0),
            "slow_density_bass": MetricField("Bass Density", "spectral_density_low", "slow", "{:.3f}", ""),
            "slow_density_mid": MetricField("Mid Density", "spectral_density_mid", "slow", "{:.3f}", ""),
            "slow_density_high": MetricField("High Density", "spectral_density_high", "slow", "{:.3f}", ""),
            "slow_key": MetricField("Detected Key", "detected_key", "slow", "{}", ""),
            "slow_key_conf": MetricField("Key Confidence", "key_confidence", "slow", "{:.3f}", "", True, 1.0),
            "slow_bpm": MetricField("Estimated BPM", "estimated_bpm", "slow", "{}", ""),
            "slow_beat_stability": MetricField("Beat Stability", "beat_stability", "slow", "{:.3f}", "", True, 1.0),
            "slow_energy_trend": MetricField("Energy Trend", "energy_trend", "slow", "{:+.3f}", ""),
            "slow_avg_energy": MetricField("Avg Energy", "average_energy", "slow", "{:.3f}", "", True, 1.0),
            "slow_energy_var": MetricField("Energy Variance", "energy_variance", "slow", "{:.3f}", ""),
        }
        
        # Create notebook with tabs for each tier
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.tabs = {}
        for tier in ["fast", "medium", "slow"]:
            tab = self._create_tier_tab(tier)
            self.tabs[tier] = tab
            self.notebook.add(tab, text=tier.upper())
        
        # Widget references for updating
        self.value_labels: dict[str, ttk.Label] = {}
        self.progress_bars: dict[str, ttk.Progressbar] = {}
        self.bool_indicators: dict[str, tk.Canvas] = {}
    
    def _create_tier_tab(self, tier: str) -> ttk.Frame:
        """Create a tab for displaying metrics from one tier.
        
        Args:
            tier: "fast", "medium", or "slow"
            
        Returns:
            Frame containing the tier metrics
        """
        tab_frame = ttk.Frame(self.notebook)
        tab_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a canvas with scrollbar for many metrics
        canvas = tk.Canvas(tab_frame, bg=BG_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Get metrics for this tier
        tier_metrics = {k: v for k, v in self.metrics.items() if v.category == tier}
        
        # Create metric rows
        for metric_key, metric_def in tier_metrics.items():
            self._create_metric_row(scrollable_frame, metric_key, metric_def)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        return tab_frame
    
    def _create_metric_row(self, parent: ttk.Frame, metric_key: str, metric_def: MetricField) -> None:
        """Create a row displaying one metric.
        
        Args:
            parent: Parent frame
            metric_key: Key for this metric
            metric_def: MetricField definition
        """
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Label (left)
        label = ttk.Label(row_frame, text=metric_def.label + ":", width=20, font=FONT_UI)
        label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Value container
        value_container = ttk.Frame(row_frame)
        value_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Progress bar (if enabled)
        if metric_def.show_bar:
            progress = ttk.Progressbar(
                value_container,
                length=150,
                maximum=100,
                mode='determinate',
            )
            progress.pack(side=tk.LEFT, padx=(0, 10))
            self.progress_bars[metric_key] = progress
        
        # Value label
        value_label = ttk.Label(
            value_container,
            text="—",
            width=15,
            font=("Courier", 10),
            foreground=ACCENT,
        )
        value_label.pack(side=tk.LEFT)
        self.value_labels[metric_key] = value_label
        
        # Unit label
        if metric_def.unit:
            unit_label = ttk.Label(value_container, text=metric_def.unit, font=FONT_UI, foreground=FG_DIM)
            unit_label.pack(side=tk.LEFT, padx=(5, 0))
    
    def update_features(self, fast: Optional[FastFeatures], medium: Optional[MediumFeatures], slow: Optional[SlowFeatures]) -> None:
        """Update displayed metrics with new feature data.
        
        Args:
            fast: FastFeatures or None
            medium: MediumFeatures or None
            slow: SlowFeatures or None
        """
        with self.lock:
            self.fast_features = fast
            self.medium_features = medium
            self.slow_features = slow
        
        # Schedule GUI update on main thread
        self.after(0, self._update_display)
    
    def _update_display(self) -> None:
        """Update all displayed values (called on main thread)."""
        with self.lock:
            fast = self.fast_features
            medium = self.medium_features
            slow = self.slow_features
        
        if not (fast or medium or slow):
            return
        
        for metric_key, metric_def in self.metrics.items():
            self._update_metric_display(metric_key, metric_def, fast, medium, slow)
    
    def _update_metric_display(
        self,
        metric_key: str,
        metric_def: MetricField,
        fast: Optional[FastFeatures],
        medium: Optional[MediumFeatures],
        slow: Optional[SlowFeatures],
    ) -> None:
        """Update display for a single metric.
        
        Args:
            metric_key: Key for this metric
            metric_def: MetricField definition
            fast: FastFeatures or None
            medium: MediumFeatures or None
            slow: SlowFeatures or None
        """
        # Select feature set
        features = None
        if metric_def.category == "fast" and fast:
            features = fast
        elif metric_def.category == "medium" and medium:
            features = medium
        elif metric_def.category == "slow" and slow:
            features = slow
        
        if features is None:
            return
        
        # Get value
        try:
            value = getattr(features, metric_def.key)
        except AttributeError:
            return
        
        # Format value
        if value is None:
            display_text = "—"
        else:
            if isinstance(value, bool):
                display_text = "✓ YES" if value else "✗ NO"
            elif isinstance(value, str):
                display_text = value
            else:
                try:
                    display_text = metric_def.format_str.format(value)
                except (ValueError, TypeError):
                    display_text = str(value)
        
        # Update label
        if metric_key in self.value_labels:
            self.value_labels[metric_key].config(text=display_text)
        
        # Update progress bar (if enabled)
        if metric_key in self.progress_bars and isinstance(value, (int, float)) and value is not None:
            progress_value = min(100, max(0, (value / metric_def.bar_max) * 100))
            self.progress_bars[metric_key].config(value=progress_value)
    
    def pack(self, **kwargs):
        """Override pack to also pack the frame."""
        super().pack(**kwargs)
        return self
