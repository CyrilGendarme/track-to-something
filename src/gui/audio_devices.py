"""Audio device and input management."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Represents an available audio device."""
    device_id: int
    name: str
    channels: int
    sample_rate: int
    device_type: str  # "input", "output", "loopback"
    
    def __str__(self) -> str:
        return f"{self.name} ({self.device_type}, {self.channels}ch, {self.sample_rate}Hz)"


def _filter_duplicate_devices(devices: list[AudioDevice]) -> list[AudioDevice]:
    """Filter and deduplicate audio devices.
    
    Filtering rules:
    1. Keep only 44100Hz sample rate devices
    2. Keep only one VB-Audio device (prefer the first one found)
    3. For duplicate devices with 1-2 channels, keep only the mono (1-channel) version
    
    Args:
        devices: List of discovered audio devices
        
    Returns:
        Filtered list of devices
    """
    if not devices:
        return devices

    # Rule 1: Filter out "well know" trash devices
    trash_name_regex = [
        # "Microphone Array (AMD Audio Dev",
                        "Microphone (Realtek HD Audio Mic"
                        "Input (VB-Audio)"]
    devices = [d for d in devices if all(trash not in d.name for trash in trash_name_regex)]
    
    
    # Rule 2: Filter to 44100Hz only
    devices = [d for d in devices if d.sample_rate == 44100]
    logger.info(f"After 44100Hz filter: {len(devices)})")
    
    # Rule 3: Keep only one VB-Audio device
    vb_audio_seen = False
    filtered = []
    for device in devices:
        if "vb-audio" in device.name.lower():
            if not vb_audio_seen:
                filtered.append(device)
                vb_audio_seen = True
                logger.info(f"Keeping VB-Audio: {device.name}")
            else:
                logger.info(f"Removing VB-Audio duplicate: {device.name}")
        else:
            filtered.append(device)
    
    
    return filtered
    
    # # Rule 3: For duplicates with same base name, prefer 1-channel (mono) over 2-channel (stereo)
    # # Group by device name prefix (before parentheses or special identifiers)
    # name_groups: dict[str, list[AudioDevice]] = {}
    # for device in filtered:
    #     # Extract base name (everything before parentheses or special markers)
    #     base_name = device.name.split('(')[0].strip()
    #     if base_name not in name_groups:
    #         name_groups[base_name] = []
    #     name_groups[base_name].append(device)
    
    # final_devices = []
    # for base_name, group in name_groups.items():
    #     if len(group) > 1:
    #         # Multiple devices with same base name - prefer mono (1-channel)
    #         mono_devices = [d for d in group if d.channels == 1]
    #         if mono_devices:
    #             # Keep mono version
    #             final_devices.extend(mono_devices)
    #             stereo_removed = [d.name for d in group if d.channels != 1]
    #             logger.info(f"Keeping mono version of '{base_name}', removed stereo: {stereo_removed}")
    #         else:
    #             # No mono version, keep first occurrence
    #             final_devices.append(group[0])
    #             removed = [d.name for d in group[1:]]
    #             logger.info(f"Removed duplicate '{base_name}' variants: {removed}")
    #     else:
    #         # Only one device with this name
    #         final_devices.extend(group)
    
    # logger.info(f"After deduplication: {len(final_devices)} devices")
    # return final_devices


def get_available_audio_devices() -> list[AudioDevice]:
    """Discover available audio input devices on the system.
    
    Returns list of available audio input devices.
    Attempts to use sounddevice if available, otherwise provides fallback options.
    
    Filtering applied:
    - Only 44100Hz sample rate
    - Only one VB-Audio device
    - For duplicates with 1-2 channels, keep mono (1-channel) version
    """
    devices = []
    
    try:
        import sounddevice as sd
        
        # Get all devices
        for i, device_info in enumerate(sd.query_devices()):
            if device_info['max_input_channels'] > 0:
                # Determine device type
                name = device_info['name']
                if 'stereo mix' in name.lower() or 'loopback' in name.lower():
                    device_type = "loopback"
                else:
                    device_type = "input"
                
                devices.append(AudioDevice(
                    device_id=i,
                    name=name,
                    channels=device_info['max_input_channels'],
                    sample_rate=int(device_info['default_samplerate']),
                    device_type=device_type,
                ))
        
        logger.info(f"Found {len(devices)} audio input devices (before filtering)")
        
        # Apply filtering rules
        devices = _filter_duplicate_devices(devices)
            
    except ImportError:
        logger.warning("sounddevice not available, using fallback audio devices")
        # Provide some common fallback options for Windows
        devices = [
            AudioDevice(
                device_id=0,
                name="Default Audio Input",
                channels=2,
                sample_rate=44100,
                device_type="input",
            ),
            AudioDevice(
                device_id=1,
                name="Stereo Mix (Loopback)",
                channels=2,
                sample_rate=44100,
                device_type="loopback",
            ),
        ]
        logger.info("Using fallback audio devices")
    except Exception as e:
        logger.error(f"Error querying audio devices: {e}")
        devices = [
            AudioDevice(
                device_id=0,
                name="Default Audio Input",
                channels=2,
                sample_rate=44100,
                device_type="input",
            ),
        ]
    
    return devices if devices else [
        AudioDevice(
            device_id=0,
            name="Default Audio Input",
            channels=2,
            sample_rate=44100,
            device_type="input",
        ),
    ]


def get_device_by_id(device_id: int) -> Optional[AudioDevice]:
    """Get a specific device by ID.
    
    Args:
        device_id: The device ID to retrieve
        
    Returns:
        AudioDevice if found, None otherwise
    """
    devices = get_available_audio_devices()
    for device in devices:
        if device.device_id == device_id:
            return device
    return None
