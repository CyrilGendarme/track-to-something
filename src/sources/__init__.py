"""Audio sources exposed to later analysis stages."""

from .audio_input import AudioInputSource
from .audio_source import AudioChunk, AudioSource
from .application_audio import ApplicationAudioSource
from .system_loopback import SystemLoopbackSource
from .track_audio import TrackAudioSource

__all__ = [
    "AudioChunk",
    "AudioInputSource",
    "AudioSource",
    "ApplicationAudioSource",
    "SystemLoopbackSource",
    "TrackAudioSource",
]
