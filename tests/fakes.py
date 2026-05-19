"""Implementações in-memory dos repositórios para uso em testes."""

from __future__ import annotations

from collections import Counter
from typing import Literal

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
        self.update_status(video_id, VideoStatus.TRIAGE_METADATA_REJECTED)

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
        render_vertical: bool = True,
        render_horizontal: bool = True,
    ) -> None:
        if clip_id not in self._clips:
            raise ValueError(f"Clip não encontrado no banco: {clip_id}")
        self._clips[clip_id] = self._clips[clip_id].model_copy(
            update={
                "hook": hook, "payoff": payoff, "title": title,
                "youtube_publish_at": youtube_publish_at,
                "render_vertical": render_vertical, "render_horizontal": render_horizontal,
            }
        )

    def update_metadata_fields(
        self,
        clip_id: str,
        *,
        hook: str | None = None,
        payoff: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        youtube_publish_at: str | None = None,
        render_vertical: bool | None = None,
        render_horizontal: bool | None = None,
    ) -> None:
        if clip_id not in self._clips:
            raise ValueError(f"Clip não encontrado: {clip_id}")
        updates: dict = {}
        if hook is not None:
            updates["hook"] = hook
        if payoff is not None:
            updates["payoff"] = payoff
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        if tags is not None:
            updates["tags"] = tags
        if youtube_publish_at is not None:
            updates["youtube_publish_at"] = youtube_publish_at
        if render_vertical is not None:
            updates["render_vertical"] = render_vertical
        if render_horizontal is not None:
            updates["render_horizontal"] = render_horizontal
        if updates:
            self._clips[clip_id] = self._clips[clip_id].model_copy(update=updates)

    def clear_platform_id(
        self, clip_id: str, *, kind: Literal["vertical", "horizontal"]
    ) -> None:
        if clip_id not in self._clips:
            return
        field = "youtube_id" if kind == "vertical" else "youtube_id_horizontal"
        self._clips[clip_id] = self._clips[clip_id].model_copy(update={field: None})

    def update_status(self, clip_id: str, new_status: str) -> None:
        if clip_id in self._clips:
            self._clips[clip_id] = self._clips[clip_id].model_copy(update={"status": new_status})

    def reject(self, clip_id: str, reason: str) -> None:
        if clip_id in self._clips:
            self._clips[clip_id] = self._clips[clip_id].model_copy(
                update={"status": ClipStatus.PROCESSING_ERROR, "error_message": reason}
            )

    def restore(self, clip_id: str) -> None:
        if clip_id in self._clips and self._clips[clip_id].status == ClipStatus.PROCESSING_ERROR:
            self._clips[clip_id] = self._clips[clip_id].model_copy(
                update={"status": ClipStatus.IDENTIFIED, "error_message": None}
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
