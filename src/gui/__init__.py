"""GUI components for audio analysis application.

The GUI runs with the lowest-latency profile by default, so this sets
``MOSHPRO_LATENCY_PROFILE`` before anything reads the settings. An explicit
``MOSHPRO_LATENCY_PROFILE`` (e.g. ``balanced`` on a weak machine) wins.
"""

import logging as _logging
import os as _os
import sys as _sys

GUI_DEFAULT_LATENCY_PROFILE = "crazy_ultra_amazing_waw"

if "src.config.settings" in _sys.modules and "MOSHPRO_LATENCY_PROFILE" not in _os.environ:
    _logging.getLogger(__name__).warning(
        "Settings were loaded before the GUI package; the GUI will not use its %s default profile",
        GUI_DEFAULT_LATENCY_PROFILE,
    )
_os.environ.setdefault("MOSHPRO_LATENCY_PROFILE", GUI_DEFAULT_LATENCY_PROFILE)

from .main_gui import AudioAnalysisGUI, launch_gui  # noqa: E402 - must follow the profile default
from .audio_devices import AudioDevice, get_available_audio_devices, get_running_applications  # noqa: E402
from .analysis_logger import AnalysisLogger, AnalysisResult  # noqa: E402

__all__ = [
    "AudioAnalysisGUI",
    "launch_gui",
    "AudioDevice",
    "get_available_audio_devices",
    "get_running_applications",
    "AnalysisLogger",
    "AnalysisResult",
]
