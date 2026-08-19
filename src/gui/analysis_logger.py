"""Analysis results logging and display widget."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Single analysis result entry."""
    timestamp: str
    operation: str
    value: float
    latency_ms: float
    frequency_range: str = "all"
    
    def as_row(self) -> str:
        """Format as a log row."""
        return f"[{self.timestamp}] {self.operation:30s} | {self.value:10.4f} | {self.latency_ms:7.2f}ms | {self.frequency_range}"


class AnalysisLogger:
    """Widget for displaying analysis results with latency tracking."""
    
    def __init__(
        self,
        parent: tk.Widget,
        max_entries: int = 1000,
        **kwargs
    ):
        """Initialize the analysis logger.
        
        Args:
            parent: Parent tkinter widget
            max_entries: Maximum number of log entries to keep in memory
            **kwargs: Additional arguments for the frame
        """
        self.frame = ttk.Frame(parent, **kwargs)
        self.max_entries = max_entries
        self.entries: deque[AnalysisResult] = deque(maxlen=max_entries)
        
        # Header
        header_frame = ttk.Frame(self.frame)
        header_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        title_label = ttk.Label(header_frame, text="Analysis Results & Latency Log")
        title_label.pack(side=tk.LEFT)
        
        # Button frame
        button_frame = ttk.Frame(header_frame)
        button_frame.pack(side=tk.RIGHT)
        
        self.clear_button = ttk.Button(button_frame, text="Clear Log", command=self.clear)
        self.clear_button.pack(side=tk.LEFT, padx=2)
        
        self.pause_button = ttk.Button(button_frame, text="Pause", command=self._toggle_pause)
        self.pause_button.pack(side=tk.LEFT, padx=2)
        
        self._paused = False
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(self.frame)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.text_widget = tk.Text(
            text_frame,
            height=15,
            width=120,
            bg="#1e1e2e",
            fg="#e8e8f0",
            font=("Consolas", 9),
            yscrollcommand=scrollbar.set,
            state=tk.DISABLED,
            wrap=tk.NONE,
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text_widget.yview)
        
        # Configure tags for highlighting
        self.text_widget.tag_config("header", foreground="#7c6af7", font=("Consolas", 9, "bold"))
        self.text_widget.tag_config("warning", foreground="#f0a500")
        self.text_widget.tag_config("critical", foreground="#e05c6a")
        self.text_widget.tag_config("success", foreground="#3ddc97")
        self.text_widget.tag_config("dim", foreground="#7878a0")
        
        # Header line
        self._add_header_line()
    
    def _add_header_line(self) -> None:
        """Add the column header line."""
        header = "Time             | Operation                      | Value      | Latency  | Frequency Range"
        separator = "─" * len(header)
        
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, header + "\n", "header")
        self.text_widget.insert(tk.END, separator + "\n", "dim")
        self.text_widget.config(state=tk.DISABLED)
    
    def log_result(
        self,
        operation: str,
        value: float,
        latency_ms: float,
        frequency_range: str = "all",
    ) -> None:
        """Log an analysis result.
        
        Args:
            operation: Name of the analysis operation
            value: The result value
            latency_ms: Time taken in milliseconds
            frequency_range: Frequency range analyzed (e.g., "bass", "mid", "high")
        """
        if self._paused:
            return
        
        # Highlight if latency is high
        if latency_ms > 30:
            tag = "critical"
        elif latency_ms > 15:
            tag = "warning"
        else:
            tag = None
        
        result = AnalysisResult(
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            operation=operation,
            value=value,
            latency_ms=latency_ms,
            frequency_range=frequency_range,
        )
        
        self.entries.append(result)
        
        # Update text widget
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, result.as_row() + "\n", tag)
        self.text_widget.see(tk.END)  # Auto-scroll to bottom
        self.text_widget.config(state=tk.DISABLED)
    
    def log_event(self, event_type: str, data: dict) -> None:
        """Log a detected event.
        
        Args:
            event_type: Type of event (e.g., "beat_detected", "onset")
            data: Event data dictionary
        """
        if self._paused:
            return
        
        message = f">>> EVENT: {event_type} | {data}\n"
        
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, message, "success")
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)
    
    def clear(self) -> None:
        """Clear all log entries."""
        self.entries.clear()
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete(1.0, tk.END)
        self._add_header_line()
        self.text_widget.config(state=tk.DISABLED)
    
    def _toggle_pause(self) -> None:
        """Toggle pause state."""
        self._paused = not self._paused
        self.pause_button.config(text="Resume" if self._paused else "Pause")
    
    def pack(self, **kwargs) -> None:
        """Pack the frame."""
        self.frame.pack(**kwargs)
    
    def grid(self, **kwargs) -> None:
        """Grid the frame."""
        self.frame.grid(**kwargs)
    
    def get_widget(self) -> tk.Widget:
        """Get the underlying frame widget."""
        return self.frame
