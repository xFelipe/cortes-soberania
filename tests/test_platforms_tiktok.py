"""Testes para platforms/tiktok.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from canal_soberania.core.platforms import PlatformOperationNotSupported
from canal_soberania.platforms.tiktok import TikTokPlatformClient, record_tiktok_pending


def _make_clip(tmp_path: Path) -> object:
    """Cria um objeto fake com clip_path_vertical."""
    mp4 = tmp_path / "clip_vertical.mp4"
    mp4.write_bytes(b"fake")

    class FakeClip:
        clip_id = "abc123ABCDE_0_60"
        clip_path_vertical = str(mp4)
        clip_path_horizontal = None

    return FakeClip()


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


def test_upload_writes_mp4_and_sidecar(tmp_path: Path) -> None:
    pending = tmp_path / "pending"
    client = TikTokPlatformClient(pending_dir=pending)
    clip = _make_clip(tmp_path)

    result = client.upload(
        clip,  # type: ignore[arg-type]
        "vertical",
        title="Soberania em Debate",
        description="Desc aqui",
        tags=["soberania", "brasil"],
        publish_at=None,
        thumb_path=None,
    )

    mp4_files = list(pending.glob("*.mp4"))
    txt_files = list(pending.glob("*.txt"))
    assert len(mp4_files) == 1
    assert len(txt_files) == 1
    sidecar = txt_files[0].read_text(encoding="utf-8")
    assert "Soberania em Debate" in sidecar
    assert "#soberania" in sidecar
    assert result  # retorna stem do arquivo


def test_upload_horizontal_raises() -> None:
    client = TikTokPlatformClient()

    class FakeClip:
        clip_id = "x"
        clip_path_vertical = None
        clip_path_horizontal = None

    with pytest.raises(PlatformOperationNotSupported, match="vertical"):
        client.upload(FakeClip(), "horizontal", title="t", description="d", tags=[], publish_at=None, thumb_path=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Operações não suportadas
# ---------------------------------------------------------------------------


def test_update_metadata_raises_not_supported(tmp_path: Path) -> None:
    pendencias = tmp_path / "pendencias_tiktok.md"
    pendencias.write_text("| Timestamp | clip_id | Operação | Detalhes |\n|---|---|---|---|\n", encoding="utf-8")
    client = TikTokPlatformClient()

    with pytest.raises(PlatformOperationNotSupported):
        client.update_metadata("TT_001", title="x")


def test_unschedule_raises_not_supported() -> None:
    client = TikTokPlatformClient()
    with pytest.raises(PlatformOperationNotSupported):
        client.unschedule("TT_002")


def test_delete_raises_not_supported() -> None:
    client = TikTokPlatformClient()
    with pytest.raises(PlatformOperationNotSupported):
        client.delete("TT_003")


def test_fetch_status_raises_not_supported() -> None:
    client = TikTokPlatformClient()
    with pytest.raises(PlatformOperationNotSupported):
        client.fetch_status(["TT_004"])


# ---------------------------------------------------------------------------
# record_tiktok_pending
# ---------------------------------------------------------------------------


def test_record_tiktok_pending_appends_row(tmp_path: Path) -> None:
    f = tmp_path / "pendencias.md"
    f.write_text("| Timestamp | clip_id | Op | Det |\n|---|---|---|---|\n", encoding="utf-8")

    record_tiktok_pending("clip001", "delete", "youtube_id=abc", file=f)

    content = f.read_text(encoding="utf-8")
    assert "clip001" in content
    assert "delete" in content
    assert "youtube_id=abc" in content


def test_record_tiktok_pending_creates_file_if_missing(tmp_path: Path) -> None:
    f = tmp_path / "new_pendencias.md"
    record_tiktok_pending("clip002", "update_metadata", "title changed", file=f)
    assert f.exists()
    assert "clip002" in f.read_text(encoding="utf-8")
