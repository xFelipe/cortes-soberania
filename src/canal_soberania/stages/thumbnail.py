"""Stage 9: gera thumbnail com Pillow — frame + gradiente + texto + logo."""

from __future__ import annotations

import sqlite3
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import connect, get_clips_by_status, init_db
from canal_soberania.logger import logger
from canal_soberania.models import Clip, ClipStatus

# Dimensões do thumbnail do YouTube
_THUMB_W = 1280
_THUMB_H = 720

# Fontes candidatas (sistema) em ordem de preferência
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]


def _find_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # noqa: S112 — font candidates: silently skip corrupted/absent fonts
                continue
    return ImageFont.load_default()


def extract_frame(video_path: Path, seek_s: float, output_path: Path) -> bool:
    """Extrai um frame do vídeo no tempo seek_s. Retorna True se bem-sucedido."""
    try:
        cmd = ["ffmpeg", "-y", "-ss", str(seek_s), "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(output_path)]
        subprocess.run(cmd, capture_output=True, check=True)  # noqa: S603
        return output_path.exists()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("Falha ao extrair frame de {}: {}", video_path.name, exc)
        return False


def _make_gradient(width: int, height: int, gradient_h: int) -> Image.Image:
    """Cria imagem preta transparente com gradiente na metade inferior."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(gradient_h):
        alpha = int(200 * (y / gradient_h))
        draw.line([(0, height - gradient_h + y), (width, height - gradient_h + y)],
                  fill=(0, 0, 0, alpha))
    return overlay


def _wrap_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> list[str]:
    """Quebra texto em linhas que cabem em max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        w = font.getlength(test) if hasattr(font, "getlength") else len(test) * 10  # fallback grosseiro
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_thumbnail(
    frame_path: Path | None,
    hook_text: str,
    output_path: Path,
    logo_path: Path | None = None,
    width: int = _THUMB_W,
    height: int = _THUMB_H,
) -> Path:
    """
    Gera thumbnail: frame (ou fundo escuro) + gradiente + texto do hook + logo.
    Retorna output_path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Base: frame ou fundo escuro fallback
    if frame_path and frame_path.exists():
        base = Image.open(frame_path).convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    else:
        base = Image.new("RGB", (width, height), (20, 20, 35))

    base = base.convert("RGBA")

    # Gradiente na metade inferior para legibilidade do texto
    gradient_h = height // 2
    overlay = _make_gradient(width, height, gradient_h)
    base = Image.alpha_composite(base, overlay)

    draw = ImageDraw.Draw(base)

    # Texto do hook em maiúsculas
    text = hook_text.upper()[:120]
    font_size = 72
    font = _find_font(font_size)

    margin = 60
    max_text_w = width - 2 * margin
    lines = _wrap_text(text, font, max_text_w)

    # Calcula posição Y do texto (parte inferior)
    line_height = font_size + 12
    total_text_h = len(lines) * line_height
    text_y = height - total_text_h - margin - 20

    for i, line in enumerate(lines):
        y = text_y + i * line_height
        # Sombra
        draw.text((margin + 3, y + 3), line, font=font, fill=(0, 0, 0, 180))
        # Texto branco
        draw.text((margin, y), line, font=font, fill=(255, 255, 255, 255))

    # Logo no canto superior esquerdo
    if logo_path and logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_h = 80
            ratio = logo_h / logo.height
            logo_w = int(logo.width * ratio)
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            base.paste(logo, (30, 20), logo)
        except Exception as exc:
            logger.debug("Falha ao colocar logo: {}", exc)

    # Salva como JPEG
    result = base.convert("RGB")
    result.save(str(output_path), "JPEG", quality=92)
    return output_path


def make_thumbnail_for_clip(
    clip: Clip,
    conn: sqlite3.Connection,
    thumbs_dir: Path,
    logo_path: Path | None = None,
    dry_run: bool = False,
) -> Path | None:
    """
    Gera thumbnail para um clipe. Retorna o path do arquivo JPEG ou None.
    """
    thumb_path = thumbs_dir / f"{clip.clip_id}.jpg"

    if thumb_path.exists():
        logger.debug("Thumbnail já existe: {}", thumb_path)
        if not dry_run:
            with conn:
                conn.execute(
                    "UPDATE clips SET thumb_path=?, status='thumbnail_ready' WHERE clip_id=?",
                    (str(thumb_path), clip.clip_id),
                )
        return thumb_path

    if dry_run:
        logger.info("[dry-run] thumbnail {}", clip.clip_id)
        return None

    # Obtém o vídeo vertical editado ou o vídeo-fonte
    row = conn.execute(
        "SELECT clip_path_vertical, video_path FROM clips c "
        "LEFT JOIN videos v ON c.video_id = v.video_id "
        "WHERE c.clip_id = ?",
        (clip.clip_id,),
    ).fetchone()

    video_path: Path | None = None
    seek_s = 2.0

    if row:
        if row["clip_path_vertical"] and Path(row["clip_path_vertical"]).exists():
            video_path = Path(row["clip_path_vertical"])
            seek_s = clip.start_s + 2.0 if clip.clip_path_vertical is None else 2.0
        elif row["video_path"] and Path(row["video_path"]).exists():
            video_path = Path(row["video_path"])
            seek_s = clip.start_s + 2.0

    frame_path: Path | None = None
    if video_path:
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "frame.jpg"
            if extract_frame(video_path, seek_s, fp):
                frame_path = fp
                out = generate_thumbnail(
                    frame_path=frame_path,
                    hook_text=clip.hook or clip.clip_id,
                    output_path=thumb_path,
                    logo_path=logo_path,
                )
                logger.info("Thumbnail gerado: {}", out)
                with conn:
                    conn.execute(
                        "UPDATE clips SET thumb_path=?, status='thumbnail_ready' WHERE clip_id=?",
                        (str(out), clip.clip_id),
                    )
                return out

    # Fallback: sem frame (texto puro)
    out = generate_thumbnail(
        frame_path=None,
        hook_text=clip.hook or clip.clip_id,
        output_path=thumb_path,
        logo_path=logo_path,
    )
    logger.info("Thumbnail gerado (sem frame): {}", out)
    with conn:
        conn.execute(
            "UPDATE clips SET thumb_path=?, status='thumbnail_ready' WHERE clip_id=?",
            (str(out), clip.clip_id),
        )
    return out


def run(
    conn: sqlite3.Connection | None = None,
    dry_run: bool = False,
) -> None:
    """Entry point chamado pelo CLI."""
    settings = load_settings()
    paths = get_paths(settings)

    if conn is None:
        if not paths["db_path"].exists():
            init_db(paths["db_path"], paths["schema_path"])
        conn = connect(paths["db_path"])

    logo_path = paths["data_dir"] / "logo.png"
    thumbs_dir = paths["thumbs_dir"]

    clips = get_clips_by_status(conn, ClipStatus.EDITED)
    logger.info("thumbnail: {} clipes para processar", len(clips))

    success = failed = 0
    for clip in clips:
        result = make_thumbnail_for_clip(
            clip=clip,
            conn=conn,
            thumbs_dir=thumbs_dir,
            logo_path=logo_path if logo_path.exists() else None,
            dry_run=dry_run or settings.dry_run,
        )
        if result is not None:
            success += 1
        elif not (dry_run or settings.dry_run):
            failed += 1

    logger.info("thumbnail concluído | ok={} falhas={}", success, failed)
