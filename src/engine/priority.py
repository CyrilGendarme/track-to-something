"""Windows timer resolution and scheduling priority (no-ops elsewhere).

By default Windows wakes sleeping threads on a ~15.6 ms clock: a 4 ms
``asyncio.sleep``, ``Event.wait`` or Tk ``after`` really takes about 16 ms,
which caps API pushes and GUI refreshes near 64 Hz. ``timeBeginPeriod(1)``
raises the resolution to 1 ms for the whole process.
"""

from __future__ import annotations

import logging
import sys
import threading

logger = logging.getLogger(__name__)

_HIGH_PRIORITY_CLASS = 0x00000080
_THREAD_PRIORITY_TIME_CRITICAL = 15

_lock = threading.Lock()
_timer_enabled = False
_process_boosted = False


def _kernel32():
    """kernel32 with pointer-sized handle types (the default int would truncate them)."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentThread.restype = wintypes.HANDLE
    kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetPriorityClass.restype = wintypes.BOOL
    kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
    kernel32.SetThreadPriority.restype = wintypes.BOOL
    kernel32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetProcessInformation.restype = wintypes.BOOL
    return kernel32


def enable_high_resolution_timer() -> bool:
    """Raise the Windows timer resolution to 1 ms (once per process)."""
    global _timer_enabled
    if sys.platform != "win32":
        return False
    with _lock:
        if not _timer_enabled:
            import ctypes

            _opt_out_of_timer_throttling()
            _timer_enabled = ctypes.windll.winmm.timeBeginPeriod(1) == 0  # TIMERR_NOERROR
            if not _timer_enabled:
                logger.warning("Could not raise the Windows timer resolution")
    return _timer_enabled


def _opt_out_of_timer_throttling() -> None:
    """Keep the 1 ms timer when Windows 11 considers the process in the background.

    Windows 11 may otherwise ignore ``timeBeginPeriod`` for processes without a
    visible window (e.g. a console script, or the GUI while minimized).
    """
    import ctypes
    from ctypes import wintypes

    class PowerThrottlingState(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

    process_power_throttling = 4  # PROCESS_INFORMATION_CLASS
    ignore_timer_resolution = 0x4
    kernel32 = _kernel32()
    # Control the flag, with its state off: "do not ignore my timer resolution"
    state = PowerThrottlingState(1, ignore_timer_resolution, 0)
    if not kernel32.SetProcessInformation(kernel32.GetCurrentProcess(), process_power_throttling,
                                          ctypes.byref(state), ctypes.sizeof(state)):
        logger.debug("Power throttling opt-out failed (error %d)", ctypes.get_last_error())


def boost_process() -> bool:
    """Run the process in the HIGH priority class (once per process)."""
    global _process_boosted
    if sys.platform != "win32":
        return False
    with _lock:
        if not _process_boosted:
            kernel32 = _kernel32()
            _process_boosted = bool(kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), _HIGH_PRIORITY_CLASS))
            if not _process_boosted:
                logger.warning("Could not raise the process priority")
    return _process_boosted


def boost_current_thread() -> bool:
    """Give the calling thread time-critical priority."""
    if sys.platform != "win32":
        return False
    kernel32 = _kernel32()
    ok = bool(kernel32.SetThreadPriority(kernel32.GetCurrentThread(), _THREAD_PRIORITY_TIME_CRITICAL))
    if not ok:
        logger.warning("Could not raise the priority of thread %s", threading.current_thread().name)
    return ok
