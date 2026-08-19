"""Local models mapped from the Rekordbox DataBridge models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CuePoint:
    """A cue point copied from a DataBridge track."""

    position_ms: int
    color: int | None = None
    kind: int | None = None


@dataclass(frozen=True)
class Track:
    """Application representation of ``rekordbox_data_pooling.TrackInfo``."""

    track_id: int | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    label: str | None = None
    comment: str | None = None
    file_path: str | None = None
    duration_ms: int | None = None
    last_played_at: str | None = None
    history_rank: int | None = None
    bpm: float | None = None
    key: str | None = None
    rating: int | None = None
    cue_points: tuple[CuePoint, ...] = field(default_factory=tuple)

    @classmethod
    def from_databridge(cls, track: Any) -> "Track":
        """Copy a DataBridge ``TrackInfo`` without importing the submodule."""
        cue_points = tuple(
            CuePoint(
                position_ms=int(cue.get("position_ms", cue.get("InMsec", 0))),
                color=cue.get("color", cue.get("Color")),
                kind=cue.get("kind", cue.get("Kind")),
            )
            if isinstance(cue, dict)
            else CuePoint(position_ms=int(getattr(cue, "position_ms", 0)))
            for cue in (getattr(track, "cue_points", None) or [])
        )
        values = {
            name: getattr(track, name, None)
            for name in (
                "track_id", "title", "artist", "album", "genre", "label",
                "comment", "file_path", "duration_ms", "last_played_at",
                "history_rank", "bpm", "key", "rating",
            )
        }
        return cls(**values, cue_points=cue_points)


@dataclass(frozen=True)
class RekordboxSession:
    """Immutable copy of a DataBridge session."""

    started_at: Any
    ended_at: Any = None

    @classmethod
    def from_bridge(cls, session: Any) -> "RekordboxSession":
        """Create from DataBridge session object."""
        return cls(started_at=session.started_at, ended_at=session.ended_at)
