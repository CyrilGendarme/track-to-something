"""Diagnostic tools for debugging audio pipeline and worker behavior."""

import sys


def utf8_stdout() -> None:
    """Print UTF-8 even when piped or redirected on Windows.

    Python then defaults to the legacy code page (cp1252), which can't encode
    the box-drawing characters in the reports or many device names.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # not a regular text stream (e.g. replaced by a test harness)
