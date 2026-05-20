"""Extrai candidatos do canal.db e gera evals/dataset.jsonl para curadoria manual.

Uso:
    python -m canal_soberania.evals.build_dataset \\
        --db data/canal.db --limit 50 --output evals/dataset.jsonl

Estratégia de extração (50 vídeos):
  - 25 que passaram triage_metadata (is_relevant=True segundo triage_results)
  - 15 que foram rejeitados em triage_metadata (is_relevant=False)
  - 10 que passaram em 3 stages (ground truth completo)

Labels são os valores registrados em triage_results — ponto de partida para
curadoria manual (abrir o JSONL e corrigir as entradas incorretas).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _parse_vtt_to_text(vtt_path: str, max_chars: int = 6000) -> str | None:
    """Converte VTT para texto simples, sem imports do módulo principal."""
    import re

    try:
        raw = Path(vtt_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line) or re.match(r"^\d+$", line):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        lines.append(clean)

    return (" ".join(lines))[:max_chars] or None


def build_dataset(db_path: Path, limit: int, output_path: Path) -> int:
    """Extrai vídeos do banco e gera JSONL. Retorna número de entradas criadas."""
    if not db_path.exists():
        print(f"Banco não encontrado: {db_path}")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Busca vídeos que têm ao menos um resultado em triage_results
    rows = conn.execute(
        """
        SELECT DISTINCT v.video_id, v.title, v.description, v.tags,
               v.canal_id, v.transcript_path, v.caption_path
          FROM videos v
          JOIN triage_results tr ON tr.video_id = v.video_id
         ORDER BY v.video_id
         LIMIT ?
        """,
        (limit,),
    ).fetchall()

    entries_written = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            video_id = row["video_id"]

            # Busca todos os resultados de triage para esse vídeo
            triage_rows = conn.execute(
                """
                SELECT stage, is_relevant, score
                  FROM triage_results
                 WHERE video_id = ?
                 ORDER BY created_at DESC
                """,
                (video_id,),
            ).fetchall()

            ground_truth: dict[str, dict[str, object]] = {}
            seen_stages: set[str] = set()
            for tr in triage_rows:
                stage_name = f"triage_{tr['stage']}"
                if stage_name not in seen_stages:
                    seen_stages.add(stage_name)
                    ground_truth[stage_name] = {
                        "is_relevant": bool(tr["is_relevant"]),
                        "score_expected": int(tr["score"]),
                    }

            if not ground_truth:
                continue

            captions: str | None = None
            if row["caption_path"]:
                captions = _parse_vtt_to_text(row["caption_path"])

            try:
                tags = json.loads(row["tags"] or "[]")
            except json.JSONDecodeError:
                tags = []

            entry = {
                "video_id": video_id,
                "title": row["title"] or "",
                "description": (row["description"] or "")[:2000],
                "tags": tags,
                "canal_id": row["canal_id"] or "",
                "transcript_path": row["transcript_path"],
                "captions": captions,
                "ground_truth": ground_truth,
                "notes": "Extraído automaticamente de triage_results — revisar manualmente.",
            }
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            entries_written += 1

    conn.close()
    return entries_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera evals/dataset.jsonl a partir do canal.db")
    parser.add_argument("--db", default="data/canal.db", help="Caminho para canal.db")
    parser.add_argument("--limit", type=int, default=50, help="Máximo de vídeos")
    parser.add_argument("--output", default="evals/dataset.jsonl", help="Arquivo de saída")
    args = parser.parse_args()

    n = build_dataset(
        db_path=Path(args.db),
        limit=args.limit,
        output_path=Path(args.output),
    )
    print(f"Escrito: {n} entradas → {args.output}")
    if n > 0:
        print("Próximo passo: revisar o JSONL e corrigir ground_truth incorretos.")


if __name__ == "__main__":
    main()
