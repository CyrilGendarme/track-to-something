#!/usr/bin/env python
"""Test filtered audio devices with logging."""

import logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

from src.gui.audio_devices import get_available_audio_devices

print("\n" + "=" * 90)
devices = get_available_audio_devices()
print("=" * 90)
print(f"\n✓ Final filtered list: {len(devices)} devices\n")

print("Index | ID   | Device Name                              | Ch | SR     | Type")
print("─" * 85)
for i, device in enumerate(devices):
    print(f"{i:5d} | {device.device_id:4d} | {device.name:40s} | {device.channels:2d} | {device.sample_rate:6d} | {device.device_type}")
