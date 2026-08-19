#!/usr/bin/env python
"""List all audio devices for debugging."""

from src.gui.audio_devices import get_available_audio_devices

devices = get_available_audio_devices()
print(f"\nTotal devices: {len(devices)}\n")
print("Index | ID   | Device Name                              | Ch | Sample Rate | Type")
print("─" * 85)

for i, device in enumerate(devices):
    print(f"{i:5d} | {device.device_id:4d} | {device.name:40s} | {device.channels:2d} | {device.sample_rate:11d} | {device.device_type}")
