"""Latency profiles: settings resolution, small-hop analysis, WASAPI fallback."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import numpy as np
import pytest

from src.engine.realtime import RealtimeAnalyzer
from src.sources.live_audio import SoundDeviceSource
from tests.synthetic import kick_track

SR = 48000


def _settings(**env: str) -> dict:
    """Resolve the settings in a fresh interpreter (they are read at import)."""
    code = ("import json; from src import config as c; print(json.dumps({k: getattr(c, k) for k in "
            "('LATENCY_PROFILE', 'AUDIO_BLOCK_SIZE', 'DEVICE_LATENCY', 'WASAPI_EXCLUSIVE', "
            "'REALTIME_HOP_SIZE', 'ONSET_THRESHOLD_K', 'KICK_THRESHOLD_K', 'GUI_REFRESH_MS', "
            "'HIGH_RES_TIMER', 'REALTIME_BOOST')}))")
    clean = {k: v for k, v in os.environ.items() if not k.startswith("MOSHPRO_")}
    result = subprocess.run([sys.executable, "-c", code], env={**clean, **env},
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def test_profiles_set_defaults_and_variables_still_override() -> None:
    balanced = _settings()
    assert balanced["LATENCY_PROFILE"] == "balanced"
    assert (balanced["AUDIO_BLOCK_SIZE"], balanced["REALTIME_HOP_SIZE"], balanced["DEVICE_LATENCY"]) == (512, 256, "high")

    ultra = _settings(MOSHPRO_LATENCY_PROFILE="ultra")
    assert (ultra["AUDIO_BLOCK_SIZE"], ultra["REALTIME_HOP_SIZE"], ultra["DEVICE_LATENCY"]) == (128, 64, "low")
    assert ultra["WASAPI_EXCLUSIVE"] is True
    assert ultra["KICK_THRESHOLD_K"] == 2.0  # kicks keep their threshold

    crazy = _settings(MOSHPRO_LATENCY_PROFILE="crazy_ultra_amazing_waw")
    assert (crazy["AUDIO_BLOCK_SIZE"], crazy["REALTIME_HOP_SIZE"], crazy["DEVICE_LATENCY"]) == (64, 64, 0.0)
    assert crazy["GUI_REFRESH_MS"] == 8 and crazy["HIGH_RES_TIMER"] and crazy["REALTIME_BOOST"]
    assert not balanced["HIGH_RES_TIMER"] and not balanced["REALTIME_BOOST"]

    custom = _settings(MOSHPRO_LATENCY_PROFILE="Low", MOSHPRO_REALTIME_HOP_SIZE="64", MOSHPRO_DEVICE_LATENCY="0.01")
    assert custom["AUDIO_BLOCK_SIZE"] == 256 and custom["REALTIME_HOP_SIZE"] == 64
    assert custom["DEVICE_LATENCY"] == 0.01


def test_unknown_profile_is_an_error() -> None:
    with pytest.raises(RuntimeError, match="MOSHPRO_LATENCY_PROFILE"):
        _settings(MOSHPRO_LATENCY_PROFILE="fastest")


def _kick_delays(hop: int) -> np.ndarray:
    period = 60.0 / 128
    y = kick_track(128.0, 12.0, SR)
    analyzer = RealtimeAnalyzer(SR, fft_size=1024, hop_size=hop)
    padded = np.concatenate([np.zeros(1024, dtype=np.float32), y])
    detected = np.array([(end - 1024) / SR for end in range(1024 + hop, padded.size + 1, hop)
                         if analyzer.process(padded[end - 1024:end], (end - 1024) / SR).kick])
    kicks = np.arange(2 * period, 12.0, period)
    return np.array([detected[(detected >= k) & (detected < k + 0.03)][0] - k for k in kicks])


def test_smaller_hops_detect_every_kick_sooner() -> None:
    reference = _kick_delays(256)
    for hop in (128, 64, 32):
        delays = _kick_delays(hop)  # raises IndexError if a kick was missed
        assert len(delays) == len(reference)
        assert np.median(delays) < np.median(reference)


class _FakePortAudioError(Exception):
    pass


class _FakeSoundDevice:
    """Just enough of sounddevice for SoundDeviceSource._open_stream."""

    PortAudioError = _FakePortAudioError

    def __init__(self, host_api: str, refuse_exclusive: bool):
        self.host_api = host_api
        self.refuse_exclusive = refuse_exclusive
        self.opened: list[dict] = []

    def WasapiSettings(self, exclusive: bool):  # noqa: N802 - mirrors sounddevice
        return {"exclusive": exclusive}

    def query_devices(self, device, kind):
        return {"hostapi": 0}

    def query_hostapis(self, index):
        return {"name": self.host_api}

    def InputStream(self, **kwargs):  # noqa: N802 - mirrors sounddevice
        if kwargs["extra_settings"] and self.refuse_exclusive:
            raise _FakePortAudioError("device in use")
        self.opened.append(kwargs)
        return kwargs


@pytest.mark.parametrize(
    ("host_api", "refuse", "expect_exclusive"),
    [("Windows WASAPI", False, True), ("Windows WASAPI", True, False), ("MME", False, False)],
)
def test_wasapi_exclusive_only_where_supported_with_fallback(host_api, refuse, expect_exclusive) -> None:
    sd = _FakeSoundDevice(host_api, refuse)
    source = SoundDeviceSource(device=3, latency="low", wasapi_exclusive=True)
    stream = source._open_stream(sd, 3)
    assert source.exclusive is expect_exclusive
    assert (stream["extra_settings"] is not None) is expect_exclusive
    assert stream["latency"] == "low"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows scheduling APIs")
def test_high_resolution_timer_makes_short_sleeps_short() -> None:
    import asyncio
    import time

    from src.engine.priority import boost_current_thread, enable_high_resolution_timer

    assert enable_high_resolution_timer()

    async def sleeps() -> float:
        started = time.perf_counter()
        for _ in range(20):
            await asyncio.sleep(0.004)
        return (time.perf_counter() - started) / 20

    assert asyncio.run(sleeps()) < 0.010  # ~16 ms without the 1 ms timer

    result: list[bool] = []
    thread = threading.Thread(target=lambda: result.append(boost_current_thread()))
    thread.start()
    thread.join()
    assert result == [True]
