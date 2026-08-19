"""Tests for the local analysis API server (HTTP + WebSocket)."""

from __future__ import annotations

import asyncio
import json

import aiohttp
import pytest

from src.analysis.bpm_detectors import BPMEstimate
from src.analysis.tiers.features import FastFeatures
from src.api import AnalysisAPIServer
from src.engine import FeatureCache


@pytest.fixture
def api_server():
    cache = FeatureCache()
    server = AnalysisAPIServer(cache, host="127.0.0.1", port=18765)
    server.start()
    yield server, cache
    server.stop()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_health_endpoint(api_server) -> None:
    server, _ = api_server

    async def check():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{server.port}/health") as resp:
                assert resp.status == 200
                assert await resp.json() == {"status": "ok"}

    _run(check())


def test_features_endpoint_reflects_cache(api_server) -> None:
    server, cache = api_server
    fast = FastFeatures(
        timestamp_s=1.0,
        onset_detected=True,
        onset_strength=0.9,
        is_percussive_peak=True,
        percussive_peak_strength=0.5,
        raw_energy=0.3,
    )
    cache.update(fast=fast)

    async def check():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{server.port}/features") as resp:
                data = await resp.json()
                assert data["fast"]["onset_strength"] == pytest.approx(0.9)
                assert data["medium"] is None
                assert data["slow"] is None

            async with session.get(f"http://127.0.0.1:{server.port}/features/fast") as resp:
                data = await resp.json()
                assert data["raw_energy"] == pytest.approx(0.3)

    _run(check())


def test_bpm_endpoint_reflects_estimates(api_server) -> None:
    server, cache = api_server
    cache.update_bpm_estimates({
        "librosa_beat_track": BPMEstimate(method="librosa_beat_track", bpm=128.0, confidence=0.97),
    })

    async def check():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{server.port}/features/bpm") as resp:
                data = await resp.json()
                assert data["estimates"]["librosa_beat_track"]["bpm"] == pytest.approx(128.0)
                assert data["consensus"]["bpm"] == pytest.approx(128.0)

    _run(check())


def test_websocket_pushes_snapshot(api_server) -> None:
    server, cache = api_server
    cache.update_bpm_estimates({
        "librosa_beat_track": BPMEstimate(method="librosa_beat_track", bpm=140.0, confidence=0.99),
    })

    async def check():
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"http://127.0.0.1:{server.port}/ws") as ws:
                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                payload = json.loads(msg.data)
                assert payload["bpm_consensus"]["bpm"] == pytest.approx(140.0)

    _run(check())
