"""Implementações in-memory dos repositórios para uso em testes."""

from __future__ import annotations

from collections import Counter

from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus


class InMemoryVideoRepository:
    def __init__(self, videos: list[Video] | None = None) -> None:
        self._videos: dict[str, Video] = {v.video_id: v for v in (videos or [])}

    def get(self, video_id: str) -> Video | None:
        return self._videos.get(video_id)

    def get_all(self) -> list[Video]:
        return list(self._videos.values())

    def get_by_status(self, status: VideoStatus) -> list[Video]:
        return [v for v in self._videos.values() if v.status == status]

    def status_summary(self) -> dict[str, int]:
        return dict(Counter(v.status for v in self._videos.values()))

    def monthly_cost(self) -> float:
        return 0.0

    # helpers de teste
    def add(self, video: Video) -> None:
        self._videos[video.video_id] = video


class InMemoryClipRepository:
    def __init__(self, clips: list[Clip] | None = None) -> None:
        self._clips: dict[str, Clip] = {c.clip_id: c for c in (clips or [])}

    def get(self, clip_id: str) -> Clip | None:
        return self._clips.get(clip_id)

    def get_all(self) -> list[Clip]:
        return list(self._clips.values())

    def get_by_status(self, status: ClipStatus) -> list[Clip]:
        return [c for c in self._clips.values() if c.status == status]

    # helpers de teste
    def add(self, clip: Clip) -> None:
        self._clips[clip.clip_id] = clip
