#!/usr/bin/env python3
"""Test WebSocket client for the Analysis API Server."""

import asyncio
import json
import logging

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Install with: pip install websockets")
    exit(1)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_websocket():
    """Connect to the WebSocket endpoint and print incoming messages."""
    uri = "ws://127.0.0.1:8768/ws"
    logger.info(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("✓ Connected! Waiting for messages (Ctrl+C to stop)...")
            message_count = 0
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    message_count += 1
                    data = json.loads(message)
                    logger.info(f"[{message_count}] Received: fast={data.get('fast') is not None}, "
                               f"medium={data.get('medium') is not None}, slow={data.get('slow') is not None}")
                except asyncio.TimeoutError:
                    logger.warning("No message received for 5 seconds (server may not be broadcasting)")
    except ConnectionRefusedError:
        logger.error(f"✗ Connection refused. Is the server running on {uri}?")
    except Exception as e:
        logger.error(f"✗ Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test_websocket())
