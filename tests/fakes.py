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

    def update_status(self, video_id: str, new_status: str) -> None:
        if video_id in self._videos:
            self._videos[video_id] = self._videos[video_id].model_copy(update={"status": new_status})

    def reject(self, video_id: str) -> None:
        self.update_status(video_id, "triage_metadata_rejected")

    def reset_stuck(self, stuck_configs: list[tuple[str, int, str]]) -> int:
        return 0

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

    def update_text(
        self,
        clip_id: str,
        hook: str | None,
        payoff: str | None,
        title: str | None,
        youtube_publish_at: str | None,
    ) -> None:
        if clip_id not in self._clips:
            raise ValueError(f"Clip não encontrado no banco: {clip_id}")
        self._clips[clip_id] = self._clips[clip_id].model_copy(
            update={"hook": hook, "payoff": payoff, "title": title, "youtube_publish_at": youtube_publish_at}
        )

    def update_status(self, clip_id: str, new_status: str) -> None:
        if clip_id in self._clips:
            self._clips[clip_id] = self._clips[clip_id].model_copy(update={"status": new_status})

    def reject(self, clip_id: str, reason: str) -> None:
        if clip_id in self._clips:
            self._clips[clip_id] = self._clips[clip_id].model_copy(
                update={"status": "processing_error", "error_message": reason}
            )

    def update_trim(self, clip_id: str, start_s: float, end_s: float) -> None:
        if clip_id in self._clips:
            self._clips[clip_id] = self._clips[clip_id].model_copy(
                update={"start_s": start_s, "end_s": end_s}
            )

    def reset_stuck(self, stuck_configs: list[tuple[str, int, str]]) -> int:
        return 0

    # helpers de teste
    def add(self, clip: Clip) -> None:
        self._clips[clip.clip_id] = clip
