"""Local HTTP + WebSocket API exposing the latest audio analysis data.

Lets other local applications (OBS browser sources, lighting controllers,
scripts in any language) retrieve or subscribe to the same tiered analysis
data the GUI displays, without depending on the GUI itself.

- ``GET /health``          - liveness check
- ``GET /features``        - latest fast/medium/slow features + BPM estimates
- ``GET /features/fast``   - latest FastFeatures only
- ``GET /features/medium`` - latest MediumFeatures only
- ``GET /features/slow``   - latest SlowFeatures only
- ``GET /features/bpm``    - latest per-method BPM estimates + consensus
- ``WS /ws``                - pushes the same ``/features`` payload on an interval
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import threading
from typing import Any

from aiohttp import web

from src.analysis.bpm_detectors import consensus_bpm
from src.config import API_BROADCAST_INTERVAL_S, API_HOST, API_PORT
from src.engine.pipeline import FeatureCache

logger = logging.getLogger(__name__)


def _feature_snapshot(feature_cache: FeatureCache) -> dict[str, Any]:
    """Build a JSON-serializable snapshot of the latest cached analysis data."""
    fast, medium, slow = feature_cache.get_all()
    bpm_estimates = feature_cache.get_bpm_estimates()
    consensus, consensus_confidence = consensus_bpm(bpm_estimates)
    return {
        "fast": dataclasses.asdict(fast) if fast else None,
        "medium": dataclasses.asdict(medium) if medium else None,
        "slow": dataclasses.asdict(slow) if slow else None,
        "bpm_estimates": {name: dataclasses.asdict(estimate) for name, estimate in bpm_estimates.items()},
        "bpm_consensus": {"bpm": consensus, "confidence": consensus_confidence},
    }


@web.middleware
async def _cors_middleware(request: web.Request, handler) -> web.StreamResponse:
    """Allow any local page/app to fetch this API (loopback-only server anyway)."""
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


class AnalysisAPIServer:
    """Serves the latest tiered audio features over HTTP (poll) and WebSocket (push).

    Runs its own asyncio event loop in a background thread, independent of the
    Tkinter GUI's main loop and the audio pipeline's start/stop lifecycle -
    other local apps can connect at any time and will see the last known data
    (or nulls before analysis has ever produced any).
    """

    def __init__(self, feature_cache: FeatureCache, host: str = API_HOST, port: int = API_PORT):
        self.feature_cache = feature_cache
        self.host = host
        self.port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._runner: web.AppRunner | None = None
        self._websockets: set[web.WebSocketResponse] = set()
        self._ready = threading.Event()
        self._start_error: Exception | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the server in a background thread. Safe to call if already running."""
        if self.is_running:
            return
        self._ready.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._run_loop, name="AnalysisAPIServer", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("Timed out starting the local analysis API server")
        if self._start_error is not None:
            raise self._start_error

    def stop(self) -> None:
        """Stop the server and its event loop thread. Safe to call if not running."""
        if not self.is_running or self._loop is None:
            return
        loop = self._loop
        asyncio.run_coroutine_threadsafe(self._shutdown(), loop).result(timeout=5.0)
        loop.call_soon_threadsafe(loop.stop)
        self._thread.join(timeout=5.0)
        self._thread = None
        self._loop = None

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start_server())
        except Exception as exc:  # noqa: BLE001 - surfaced to the calling thread via start()
            self._start_error = exc
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()

    async def _start_server(self) -> None:
        app = web.Application(middlewares=[_cors_middleware])
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/features", self._handle_features)
        app.router.add_get("/features/fast", self._handle_features_fast)
        app.router.add_get("/features/medium", self._handle_features_medium)
        app.router.add_get("/features/slow", self._handle_features_slow)
        app.router.add_get("/features/bpm", self._handle_features_bpm)
        app.router.add_get("/ws", self._handle_ws)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        asyncio.ensure_future(self._broadcast_loop())
        logger.info(f"[AnalysisAPIServer] Listening on http://{self.host}:{self.port}")

    async def _shutdown(self) -> None:
        for ws in list(self._websockets):
            await ws.close()
        self._websockets.clear()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _handle_features(self, request: web.Request) -> web.Response:
        return web.json_response(_feature_snapshot(self.feature_cache))

    async def _handle_features_fast(self, request: web.Request) -> web.Response:
        fast, _, _ = self.feature_cache.get_all()
        return web.json_response(dataclasses.asdict(fast) if fast else None)

    async def _handle_features_medium(self, request: web.Request) -> web.Response:
        _, medium, _ = self.feature_cache.get_all()
        return web.json_response(dataclasses.asdict(medium) if medium else None)

    async def _handle_features_slow(self, request: web.Request) -> web.Response:
        _, _, slow = self.feature_cache.get_all()
        return web.json_response(dataclasses.asdict(slow) if slow else None)

    async def _handle_features_bpm(self, request: web.Request) -> web.Response:
        bpm_estimates = self.feature_cache.get_bpm_estimates()
        consensus, consensus_confidence = consensus_bpm(bpm_estimates)
        return web.json_response({
            "estimates": {name: dataclasses.asdict(estimate) for name, estimate in bpm_estimates.items()},
            "consensus": {"bpm": consensus, "confidence": consensus_confidence},
        })

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._websockets.add(ws)
        logger.debug(f"[AnalysisAPIServer] WebSocket client connected ({len(self._websockets)} total)")
        try:
            async for _ in ws:
                pass  # Push-only endpoint; client messages are ignored
        finally:
            self._websockets.discard(ws)
            logger.debug(f"[AnalysisAPIServer] WebSocket client disconnected ({len(self._websockets)} total)")
        return ws

    async def _broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(API_BROADCAST_INTERVAL_S)
            if not self._websockets:
                continue
            payload = json.dumps(_feature_snapshot(self.feature_cache))
            dead: set[web.WebSocketResponse] = set()
            for ws in list(self._websockets):
                try:
                    await ws.send_str(payload)
                except (ConnectionResetError, RuntimeError):
                    dead.add(ws)
            self._websockets -= dead
