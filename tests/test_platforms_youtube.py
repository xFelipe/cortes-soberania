"""Testes para platforms/youtube.py (API YouTube mockada)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from canal_soberania.platforms.youtube import YouTubePlatformClient, _parse_platform_status
from canal_soberania.core.platforms import PlatformClient, PlatformOperationNotSupported, PlatformStatus, get_platform


def _make_client() -> tuple[YouTubePlatformClient, MagicMock]:
    """Retorna (client, svc_mock) sem tocar em OAuth."""
    client = YouTubePlatformClient(
        client_secrets_path=Path("config/client_secrets.json"),
        token_path=Path("config/youtube_token.json"),
    )
    svc = MagicMock()
    client._svc = svc  # injeta diretamente, bypassa OAuth
    return client, svc


def _yt_item(
    yt_id: str,
    privacy: str = "private",
    upload_status: str = "processed",
    publish_at: str | None = "2026-06-01T09:00:00Z",
    title: str = "Título Original",
    description: str = "Desc original",
    tags: list[str] | None = None,
    category_id: str = "22",
) -> dict:
    item: dict = {
        "id": yt_id,
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or ["tag1"],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "uploadStatus": upload_status,
            "selfDeclaredMadeForKids": False,
        },
        "statistics": {"viewCount": "100", "likeCount": "5", "commentCount": "2"},
    }
    if publish_at:
        item["status"]["publishAt"] = publish_at
    return item


# ---------------------------------------------------------------------------
# update_metadata
# ---------------------------------------------------------------------------


def test_update_metadata_calls_videos_update() -> None:
    client, svc = _make_client()
    svc.videos().list().execute.return_value = {"items": [_yt_item("YT_001")]}
    svc.videos().list.return_value.execute.return_value = {"items": [_yt_item("YT_001")]}
    svc.videos().update.return_value.execute.return_value = {}
    svc.videos().update().execute.return_value = {}

    client.update_metadata("YT_001", title="Novo Título", description="Nova desc")

    update_call = svc.videos().update
    args = update_call.call_args
    assert "snippet" in args.kwargs["part"]
    body = args.kwargs["body"]
    assert body["snippet"]["title"] == "Novo Título"
    assert body["snippet"]["description"] == "Nova desc"
    assert body["id"] == "YT_001"


def test_update_metadata_preserves_existing_tags_when_not_passed() -> None:
    """Se tags=None, não sobrescreve as tags existentes."""
    client, svc = _make_client()
    existing_tags = ["soberania", "brasil"]
    svc.videos().list.return_value.execute.return_value = {
        "items": [_yt_item("YT_002", tags=existing_tags)]
    }
    svc.videos().update.return_value.execute.return_value = {}

    client.update_metadata("YT_002", title="Apenas título")

    body = svc.videos().update.call_args.kwargs["body"]
    assert body["snippet"]["tags"] == existing_tags


def test_update_metadata_updates_publish_at() -> None:
    client, svc = _make_client()
    svc.videos().list.return_value.execute.return_value = {"items": [_yt_item("YT_003")]}
    svc.videos().update.return_value.execute.return_value = {}

    new_at = "2026-07-01T14:00:00Z"
    client.update_metadata("YT_003", publish_at=new_at)

    body = svc.videos().update.call_args.kwargs["body"]
    assert body["status"]["publishAt"] == new_at
    assert "status" in svc.videos().update.call_args.kwargs["part"]


def test_update_metadata_raises_if_video_not_found() -> None:
    client, svc = _make_client()
    svc.videos().list.return_value.execute.return_value = {"items": []}

    with pytest.raises(ValueError, match="YT_GONE"):
        client.update_metadata("YT_GONE", title="x")


def test_update_metadata_noop_when_nothing_passed() -> None:
    """Nenhum argumento → não faz chamada de update."""
    client, svc = _make_client()
    svc.videos().list.return_value.execute.return_value = {"items": [_yt_item("YT_004")]}

    client.update_metadata("YT_004")

    svc.videos().update.assert_not_called()


# ---------------------------------------------------------------------------
# unschedule
# ---------------------------------------------------------------------------


def test_unschedule_sets_private_without_publish_at() -> None:
    client, svc = _make_client()
    svc.videos().update.return_value.execute.return_value = {}

    client.unschedule("YT_005")

    args = svc.videos().update.call_args.kwargs
    assert args["part"] == "status"
    body = args["body"]
    assert body["id"] == "YT_005"
    assert body["status"]["privacyStatus"] == "private"
    assert "publishAt" not in body["status"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_calls_videos_delete() -> None:
    client, svc = _make_client()
    svc.videos().delete.return_value.execute.return_value = None

    client.delete("YT_006")

    svc.videos().delete.assert_called_with(id="YT_006")


# ---------------------------------------------------------------------------
# fetch_status — batching
# ---------------------------------------------------------------------------


def test_fetch_status_batches_50() -> None:
    """75 IDs → 2 chamadas à API."""
    client, svc = _make_client()
    svc.videos().list.return_value.execute.return_value = {"items": []}

    ids = [f"ID_{i:03d}" for i in range(75)]
    result = client.fetch_status(ids)

    assert svc.videos().list.return_value.execute.call_count == 2
    assert result == {}


def test_fetch_status_parses_items() -> None:
    client, svc = _make_client()
    svc.videos().list.return_value.execute.return_value = {
        "items": [_yt_item("YT_007", privacy="public", publish_at=None)]
    }

    result = client.fetch_status(["YT_007"])

    assert "YT_007" in result
    ps = result["YT_007"]
    assert ps.privacy_status == "public"
    assert ps.view_count == 100
    assert ps.like_count == 5


# ---------------------------------------------------------------------------
# _parse_platform_status
# ---------------------------------------------------------------------------


def test_parse_platform_status_full() -> None:
    item = {
        "id": "X",
        "status": {
            "privacyStatus": "private",
            "uploadStatus": "processed",
            "publishAt": "2026-06-01T09:00:00Z",
            "rejectionReason": None,
        },
        "snippet": {"publishedAt": "2026-06-01T09:00:01Z"},
        "statistics": {"viewCount": "10", "likeCount": "2", "commentCount": "1"},
    }
    ps = _parse_platform_status(item)
    assert ps.privacy_status == "private"
    assert ps.upload_status == "processed"
    assert ps.publish_at == "2026-06-01T09:00:00Z"
    assert ps.view_count == 10
    assert ps.like_count == 2
    assert ps.comment_count == 1


# ---------------------------------------------------------------------------
# get_platform factory
# ---------------------------------------------------------------------------


def test_get_platform_youtube_returns_client() -> None:
    settings = MagicMock()
    settings.youtube_oauth_client_secrets_path = "config/client_secrets.json"
    settings.youtube_oauth_token_path = "config/youtube_token.json"
    client = get_platform("youtube", settings)
    assert isinstance(client, YouTubePlatformClient)
    assert isinstance(client, PlatformClient)


def test_get_platform_tiktok_returns_client() -> None:
    from canal_soberania.platforms.tiktok import TikTokPlatformClient
    settings = MagicMock()
    client = get_platform("tiktok", settings)
    assert isinstance(client, TikTokPlatformClient)
    assert isinstance(client, PlatformClient)


def test_get_platform_unknown_raises() -> None:
    import pytest
    settings = MagicMock()
    with pytest.raises(ValueError, match="desconhecida"):
        get_platform("unknown", settings)  # type: ignore[arg-type]


def test_platform_operation_not_supported_is_exception() -> None:
    exc = PlatformOperationNotSupported("op não suportada")
    assert str(exc) == "op não suportada"
    assert isinstance(exc, Exception)
