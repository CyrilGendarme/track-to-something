"""Test main GUI initialization without running the pipeline."""

import tkinter as tk
import logging

logging.basicConfig(level=logging.INFO)

from src.gui.main_gui import AudioAnalysisGUI

print("Creating GUI...")
app = AudioAnalysisGUI()

print("✅ GUI created successfully!")
print("Verifying metrics display exists...")
assert hasattr(app, 'metrics_display'), "metrics_display attribute missing"
print(f"✅ Metrics display widget: {app.metrics_display}")

print("Closing GUI...")
app.quit()
app.destroy()

print("✅ GUI initialization and cleanup successful!")
