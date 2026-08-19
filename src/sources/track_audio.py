"""Load audio files when the DataBridge reports a newly loaded track."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import soundfile as sf

from src.models import Track
from .audio_source import AudioChunk


class TrackAudioSource:
    """Read the current track file as analysis-sized PCM chunks."""

    def __init__(self, *, block_size: int = 4096, audio_roots: tuple[Path, ...] = ()):
        self.block_size = block_size
        self.audio_roots = audio_roots
        self.track: Track | None = None
        self._file: sf.SoundFile | None = None

    def poll(self, events: list[tuple[str, object]]) -> bool:
        """Handle bridge events; return whether a new file was opened."""
        for event_name, databridge_track in events:
            if event_name != "track_loaded":
                continue
            self._open_track(Track.from_databridge(databridge_track))
            return True
        return False

    def _open_track(self, track: Track) -> None:
        self.close()
        if not track.file_path:
            raise FileNotFoundError(f"Track {track.track_id!r} has no audio file path")
        path = self._resolve_path(track.file_path)
        self.track = track
        self._file = sf.SoundFile(path, mode="r")

    def _resolve_path(self, file_path: str) -> Path:
        path = Path(file_path).expanduser()
        if path.is_file():
            return path

        relative_path = Path(file_path.lstrip("\\/"))
        for root in self.audio_roots:
            candidate = root / relative_path
            if candidate.is_file():
                return candidate
            # Search up to 4 levels deep in the root to avoid hangs on large collections.
            for depth in range(1, 5):
                pattern = "/".join(["*"] * depth) + f"/{path.name}"
                matches = tuple(root.glob(pattern))
                if matches:
                    return matches[0]
        raise FileNotFoundError(path)

    def __iter__(self) -> Iterator[AudioChunk]:
        if self._file is None:
            return
        while True:
            samples = self._file.read(self.block_size, dtype="float32", always_2d=True)
            if len(samples) == 0:
                break
            yield AudioChunk(samples=samples, sample_rate=self._file.samplerate)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None