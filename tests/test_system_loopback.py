"""Output loopback source and driver fallbacks, with fake device modules."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from src.sources.live_audio import SAFE_BLOCK_SIZE, SoundDeviceSource
from src.sources.system_loopback import SystemLoopbackSource


class _Recorder:
    def __init__(self, soundcard, blocksize):
        self.soundcard = soundcard
        self.blocksize = blocksize

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.soundcard.closed = True

    def record(self, numframes):
        self.soundcard.calls += 1
        if self.soundcard.calls in self.soundcard.discontinuous:
            import warnings
            warnings.warn("data discontinuity in recording", self.soundcard.SoundcardRuntimeWarning)
        return np.full((numframes, 2), 0.25, dtype=np.float32)


def _fake_soundcard(monkeypatch, discontinuous=()):
    sc = types.ModuleType("soundcard")
    sc.SoundcardRuntimeWarning = type("SoundcardRuntimeWarning", (RuntimeWarning,), {})
    sc.calls, sc.closed, sc.discontinuous = 0, False, set(discontinuous)
    speakers = [types.SimpleNamespace(id="{spk-1}", name="Speaker (Realtek(R) Audio)"),
                types.SimpleNamespace(id="{spk-2}", name="Headphones (USB)")]
    sc.all_speakers = lambda: speakers
    sc.default_speaker = lambda: speakers[0]
    sc.opened = []

    def get_microphone(speaker_id, include_loopback):
        assert include_loopback
        sc.opened.append(speaker_id)
        return types.SimpleNamespace(
            recorder=lambda samplerate, channels, blocksize: _Recorder(sc, blocksize))

    sc.get_microphone = get_microphone
    monkeypatch.setitem(sys.modules, "soundcard", sc)
    return sc


def test_loopback_streams_chunks_until_closed(monkeypatch) -> None:
    sc = _fake_soundcard(monkeypatch)
    source = SystemLoopbackSource(speaker="headphones", sample_rate=48000, block_size=128)
    chunks = []
    for chunk in source:
        chunks.append(chunk)
        if len(chunks) == 5:
            source.close()
    assert sc.opened == ["{spk-2}"] and source.speaker_name == "Headphones (USB)"
    assert len(chunks) == 5 and sc.closed
    assert all(c.samples.shape == (128, 2) and c.sample_rate == 48000 for c in chunks)
    times = [c.capture_time_s for c in chunks]
    assert times == sorted(times)


def test_loopback_defaults_to_default_speaker_and_rejects_unknown(monkeypatch) -> None:
    sc = _fake_soundcard(monkeypatch)
    source = SystemLoopbackSource()
    next(iter(source))
    assert sc.opened == ["{spk-1}"]
    with pytest.raises(ValueError, match="Output device not found"):
        next(iter(SystemLoopbackSource(speaker="nope")))


def test_loopback_counts_discontinuities_only_after_startup(monkeypatch) -> None:
    import src.sources.system_loopback as loopback

    _fake_soundcard(monkeypatch, discontinuous={1, 3})
    clock = iter([0.0, 0.1, 2.0, 2.1, 2.2])
    monkeypatch.setattr(loopback.time, "monotonic", lambda: next(clock))
    source = SystemLoopbackSource(block_size=64)
    for i, _ in enumerate(source):
        if i == 2:
            source.close()
    assert source.overflows == 1  # call 1 was during start-up, call 3 counts


class _FakePortAudioError(Exception):
    pass


class _FakeSoundDevice:
    PortAudioError = _FakePortAudioError

    def __init__(self, host_api, refuse_small=False):
        self.host_api = host_api
        self.refuse_small = refuse_small
        self.opened: list[dict] = []

    def WasapiSettings(self, exclusive):  # noqa: N802 - mirrors sounddevice
        return {"exclusive": exclusive}

    def query_devices(self, device, kind):
        return {"hostapi": 0}

    def query_hostapis(self, index):
        return {"name": self.host_api}

    def InputStream(self, **kwargs):  # noqa: N802 - mirrors sounddevice
        if self.refuse_small and kwargs["blocksize"] < SAFE_BLOCK_SIZE:
            raise _FakePortAudioError("Unanticipated host error")
        self.opened.append(kwargs)
        return kwargs


def test_zero_latency_means_low_outside_wasapi() -> None:
    sd = _FakeSoundDevice("Windows DirectSound")
    source = SoundDeviceSource(device=7, latency=0.0, wasapi_exclusive=True, block_size=64)
    stream = source._open_stream(sd, 7)
    assert stream["latency"] == "low" and not source.exclusive

    wasapi = _FakeSoundDevice("Windows WASAPI")
    assert SoundDeviceSource(device=17, latency=0.0, block_size=64)._open_stream(wasapi, 17)["latency"] == 0.0


def test_driver_refusing_small_blocks_falls_back_to_safe_settings() -> None:
    sd = _FakeSoundDevice("Windows WDM-KS", refuse_small=True)
    source = SoundDeviceSource(device=29, latency="low", block_size=64)
    stream = source._open_stream(sd, 29)
    assert (stream["blocksize"], stream["latency"]) == (SAFE_BLOCK_SIZE, "high")
    assert source.block_size == SAFE_BLOCK_SIZE  # reported in stats()
