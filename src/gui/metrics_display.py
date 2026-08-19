"""Real-time metrics display widget for audio analysis."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from typing import Optional
import threading

from src.analysis.tiers.features import FastFeatures, MediumFeatures, SlowFeatures
from src.analysis.bpm_detectors import BPMEstimate, consensus_bpm
from src.gui.theme import BG, BG_PANEL, BG_CARD, FG, FG_DIM, ACCENT, ACCENT2, FONT_UI, FONT_BOLD

logger = logging.getLogger(__name__)

# Human-friendly labels for each BPM detector method (see src/analysis/bpm_detectors.py)
BPM_METHOD_LABELS: dict[str, str] = {
    "kick_band_autocorr": "Kick Band (40-120Hz) Autocorr",
    "dynamic_kick_band": "Dynamic Kick Band Autocorr",
    "comb_filter_bank": "Comb Filter Bank",
    "librosa_beat_track": "Librosa Beat Track",
    "librosa_onset_tempogram": "Librosa Onset Tempogram",
    "aubio_tempo": "Aubio Tempo",
    "madmom_dbn": "Madmom DBN Beat Tracker",
    "essentia_rhythm_extractor": "Essentia Rhythm Extractor",
}


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
        self.bpm_estimates: dict[str, BPMEstimate] = {}
        self.lock = threading.Lock()
        
        # Track last BPM to avoid logging every update
        self.last_bpm_value: Optional[float] = None
        
        # Initialize widget references FIRST (before tab creation)
        self.value_labels: dict[str, ttk.Label] = {}
        self.progress_bars: dict[str, ttk.Progressbar] = {}
        self.bool_indicators: dict[str, tk.Canvas] = {}
        
        # Per-method BPM rows, created lazily as methods are first reported
        self.bpm_rows_frame: Optional[ttk.Frame] = None
        self.bpm_value_labels: dict[str, ttk.Label] = {}
        self.bpm_conf_bars: dict[str, ttk.Progressbar] = {}
        self.bpm_consensus_label: Optional[ttk.Label] = None
        
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
            "slow_bpm": MetricField("Estimated BPM", "estimated_bpm", "slow", "{:.1f}", ""),
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
        
        # Dedicated tab showing every BPM detection method side by side
        bpm_tab = self._create_bpm_tab()
        self.tabs["bpm"] = bpm_tab
        self.notebook.add(bpm_tab, text="BPM METHODS")
    
    def _create_bpm_tab(self) -> ttk.Frame:
        """Create the tab listing each BPM detection method's estimate.
        
        Rows are created lazily per-method the first time a result for that
        method is received (see ``update_bpm_estimates``), since which
        optional detectors (aubio/madmom/essentia) are available isn't known
        until the first analysis pass completes.
        """
        tab_frame = ttk.Frame(self.notebook)
        tab_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(tab_frame, bg=BG_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Consensus row (confidence-weighted average of all methods) up top
        consensus_row = ttk.Frame(scrollable_frame)
        consensus_row.pack(fill=tk.X, padx=10, pady=(5, 10))
        ttk.Label(consensus_row, text="Consensus BPM:", width=28, font=FONT_BOLD).pack(side=tk.LEFT, padx=(0, 10))
        self.bpm_consensus_label = ttk.Label(
            consensus_row, text="—", width=20, font=("Courier", 11, "bold"), foreground=ACCENT2
        )
        self.bpm_consensus_label.pack(side=tk.LEFT)
        
        self.bpm_rows_frame = scrollable_frame
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        return tab_frame
    
    def _ensure_bpm_row(self, method: str) -> None:
        """Create the display row for ``method`` the first time it's seen."""
        if method in self.bpm_value_labels or self.bpm_rows_frame is None:
            return
        
        row_frame = ttk.Frame(self.bpm_rows_frame)
        row_frame.pack(fill=tk.X, padx=10, pady=4)
        
        label_text = BPM_METHOD_LABELS.get(method, method.replace("_", " ").title())
        ttk.Label(row_frame, text=label_text + ":", width=28, font=FONT_UI).pack(side=tk.LEFT, padx=(0, 10))
        
        value_container = ttk.Frame(row_frame)
        value_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        confidence_bar = ttk.Progressbar(value_container, length=100, maximum=100, mode="determinate")
        confidence_bar.pack(side=tk.LEFT, padx=(0, 10))
        self.bpm_conf_bars[method] = confidence_bar
        
        value_label = ttk.Label(value_container, text="—", width=22, font=("Courier", 10), foreground=ACCENT)
        value_label.pack(side=tk.LEFT)
        self.bpm_value_labels[method] = value_label
    
    def update_bpm_estimates(self, estimates: dict[str, BPMEstimate]) -> None:
        """Update displayed values with the latest per-method BPM estimates.
        
        Args:
            estimates: {method_name: BPMEstimate}, as produced by
                ``MultiMethodBPMAnalyzer.analyze``.
        """
        with self.lock:
            self.bpm_estimates = estimates
        self.after(0, self._update_bpm_display)
    
    def _update_bpm_display(self) -> None:
        """Update the BPM methods tab (called on main thread)."""
        with self.lock:
            estimates = dict(self.bpm_estimates)
        
        if not estimates:
            return
        
        for method, estimate in estimates.items():
            self._ensure_bpm_row(method)
            value_label = self.bpm_value_labels.get(method)
            conf_bar = self.bpm_conf_bars.get(method)
            
            if not estimate.available:
                text = "N/A (not installed)"
            elif estimate.bpm is None:
                text = f"— ({estimate.error})" if estimate.error else "—"
            else:
                text = f"{estimate.bpm:6.1f} BPM  (conf {estimate.confidence:.2f})"
            
            if value_label is not None:
                value_label.config(text=text)
            if conf_bar is not None:
                conf_bar.config(value=estimate.confidence * 100 if estimate.available else 0)
        
        if self.bpm_consensus_label is not None:
            bpm, confidence = consensus_bpm(estimates)
            if bpm is None:
                self.bpm_consensus_label.config(text="—")
            else:
                self.bpm_consensus_label.config(text=f"{bpm:6.1f} BPM  (conf {confidence:.2f})")
    
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
            if metric_key == "slow_bpm":
                logger.warning(f"[GUI] BPM: slow features missing attribute '{metric_def.key}'")
            return
        
        # Debug log for BPM (only on change)
        if metric_key == "slow_bpm" and value is not None:
            current_bpm = float(value) if value is not None else None
            # Only log if BPM changed significantly (more than 1 BPM difference)
            if self.last_bpm_value is None or abs(current_bpm - self.last_bpm_value) > 1.0:
                logger.info(f"[GUI] BPM changed: {current_bpm:.1f} BPM")
                self.last_bpm_value = current_bpm
        
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
                except (ValueError, TypeError) as e:
                    display_text = str(value)
                    if metric_key == "slow_bpm":
                        logger.error(f"[GUI] BPM format error: {e}")
        
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
