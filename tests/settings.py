"""Local resources used by the audio integration tests.

Set these values in this file, or provide the matching environment variables.
No real paths or device identifiers are committed to the repository.
"""

from __future__ import annotations

import os
from pathlib import Path


def _path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser() if value else None


def _databridge_default_database() -> Path:
    """Return the same default path used by RekordboxDBReader."""
    databridge_src = Path(__file__).parents[1] / "submodules" / "rekordbox-databridge" / "src"
    import sys

    sys.path.insert(0, str(databridge_src))
    try:
        from rekordbox_data_pooling.db_reader import _default_db_path

        return _default_db_path()
    finally:
        sys.path.remove(str(databridge_src))


# A local audio file used to simulate a USB stream without requiring hardware.
USB_SIMULATION_FILE = Path(r"C:\Users\User\Desktop\musique\tracks\youtube_downloaded\acid_house\Le Loup - Focus & Elevate [DFR006].mp3")

# Windows application name, for example "Spotify" or "rekordbox".
APPLICATION_NAME = os.getenv("MOSHPRO_TEST_APPLICATION_NAME")

# Optional loopback endpoint. Leave unset to use the system default output.
APPLICATION_AUDIO_DEVICE = os.getenv("MOSHPRO_TEST_APPLICATION_DEVICE")

# Rekordbox master.db. The test reads the latest track-loaded event from it.
REKORDBOX_DATABASE = _path("MOSHPRO_TEST_REKORDBOX_DATABASE") or _databridge_default_database()

# Rekordbox can store FolderPath without the collection drive/root.
_default_audio_roots = [Path.home() / "Music"]
desktop_music = Path.home() / "Desktop" / "musique"
if desktop_music.is_dir():
    _default_audio_roots.insert(0, desktop_music)
REKORDBOX_AUDIO_ROOTS = tuple(
    Path(value).expanduser()
    for value in os.getenv(
        "MOSHPRO_TEST_REKORDBOX_AUDIO_ROOTS",
        os.pathsep.join(str(path) for path in _default_audio_roots),
    ).split(os.pathsep)
    if value
)

# Keep live integration tests short and deterministic.
CAPTURE_DURATION_SECONDS = float(os.getenv("MOSHPRO_TEST_CAPTURE_SECONDS", "5"))
BLOCK_SIZE = int(os.getenv("MOSHPRO_TEST_BLOCK_SIZE", "4096"))
SAMPLE_RATE = int(os.getenv("MOSHPRO_TEST_SAMPLE_RATE", "44100"))

# The suite reports both the whole track and this example frequency range.
FREQUENCY_BANDS = {
    "bass": (20.0, 250.0),
    "mid": (250.0, 2_000.0),
    "2-5khz": (2_000.0, 5_000.0),
}