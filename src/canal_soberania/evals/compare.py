"""Gera report.html comparando dois runs de eval."""

from __future__ import annotations

import html
from pathlib import Path

from canal_soberania.evals.models import EvalResult, RunSummary
from canal_soberania.evals.runner import compute_metrics, load_run


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _bar(value: float, color: str, label: str, bar_width: int = 120) -> str:
    w = round(value * bar_width)
    return (
        f'<div class="bar-row">'
        f'<span class="bar-label">{label}</span>'
        f'<div class="bar-track">'
        f'<div class="bar-fill" style="width:{w}px;background:{color}"></div>'
        f'</div>'
        f'<span class="bar-value">{_pct(value)}</span>'
        f'</div>'
    )


def _metrics_card(summary: RunSummary, label: str) -> str:
    return f"""
<div class="card">
  <h3>{html.escape(label)}</h3>
  <p class="meta">Stage: {html.escape(summary.stage)} &bull; Backend: {html.escape(summary.backend)} &bull; v{html.escape(summary.prompt_version)}</p>
  {_bar(summary.precision, "#2563eb", "Precision")}
  {_bar(summary.recall,    "#16a34a", "Recall")}
  {_bar(summary.f1,        "#9333ea", "F1")}
  {_bar(summary.accuracy,  "#ea580c", "Accuracy")}
  <p class="cost">Custo: ${summary.total_cost_usd:.4f} USD &bull; Entradas: {summary.total_entries} &bull; Tokens in/out: {summary.total_tokens_in}/{summary.total_tokens_out}</p>
</div>
"""


def _divergence_rows(
    results1: list[EvalResult],
    results2: list[EvalResult],
    entries_by_id: dict[str, tuple[str, str]],
) -> str:
    map1 = {r.video_id: r for r in results1}
    map2 = {r.video_id: r for r in results2}
    all_ids = sorted(set(map1) | set(map2))

    rows: list[str] = []
    for vid in all_ids:
        r1 = map1.get(vid)
        r2 = map2.get(vid)
        pred1 = ("✓ relevante" if r1 and r1.is_relevant_predicted else "✗ irrelevante") if r1 else "—"
        pred2 = ("✓ relevante" if r2 and r2.is_relevant_predicted else "✗ irrelevante") if r2 else "—"
        expected = ("✓" if r1 and r1.is_relevant_expected else "✗") if r1 else ("✓" if r2 and r2.is_relevant_expected else "✗")
        disagree = r1 and r2 and r1.is_relevant_predicted != r2.is_relevant_predicted
        title_esc = html.escape(entries_by_id.get(vid, (vid, ""))[1] or vid)
        row_class = ' class="diverge"' if disagree else ""

        raw1 = html.escape((r1.raw_response or "")[:600]) if r1 else ""
        raw2 = html.escape((r2.raw_response or "")[:600]) if r2 else ""

        detail = ""
        if disagree:
            detail = (
                f'<tr{row_class}><td colspan="5">'
                f'<details><summary>Ver respostas divergentes</summary>'
                f'<div class="raw"><strong>Run 1:</strong><pre>{raw1}</pre>'
                f'<strong>Run 2:</strong><pre>{raw2}</pre></div>'
                f'</details></td></tr>'
            )

        rows.append(
            f'<tr{row_class}>'
            f'<td><code>{html.escape(vid)}</code></td>'
            f'<td>{title_esc}</td>'
            f'<td>{pred1}</td>'
            f'<td>{pred2}</td>'
            f'<td>{expected}</td>'
            f'</tr>'
            + detail
        )
    return "\n".join(rows)


_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem; color: #1e293b; }
h1 { color: #0f172a; }
h2 { color: #334155; margin-top: 2rem; }
h3 { margin: 0 0 .5rem; }
.cards { display: flex; gap: 1.5rem; flex-wrap: wrap; }
.card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem 1.5rem; min-width: 280px; }
.meta { color: #64748b; font-size: .85rem; margin: .25rem 0 .75rem; }
.cost { color: #64748b; font-size: .8rem; margin-top: .75rem; }
.bar-row { display: flex; align-items: center; gap: .5rem; margin: .3rem 0; }
.bar-label { width: 80px; font-size: .85rem; color: #475569; }
.bar-track { background: #e2e8f0; border-radius: 4px; height: 14px; width: 120px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width .3s; }
.bar-value { font-size: .85rem; font-weight: 600; }
table { border-collapse: collapse; width: 100%; margin-top: 1rem; font-size: .9rem; }
th { background: #f1f5f9; text-align: left; padding: .5rem .75rem; border-bottom: 2px solid #cbd5e1; }
td { padding: .45rem .75rem; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr.diverge td { background: #fef9c3; }
pre { white-space: pre-wrap; font-size: .8rem; background: #f8fafc; padding: .5rem; border-radius: 4px; }
.raw { margin-top: .5rem; }
code { font-size: .8rem; }
"""


def compare_runs(run1_path: Path, run2_path: Path, output_path: Path) -> None:
    """Lê dois run JSONL, gera report.html comparando métricas e divergências."""
    summary1, results1 = load_run(run1_path)
    summary2, results2 = load_run(run2_path)

    entries_by_id: dict[str, tuple[str, str]] = {}
    for r in results1 + results2:
        if r.video_id not in entries_by_id:
            entries_by_id[r.video_id] = (r.video_id, r.video_id)

    diverge_count = sum(
        1
        for vid in set(r.video_id for r in results1) & set(r.video_id for r in results2)
        if any(r.video_id == vid for r in results1) and any(r.video_id == vid for r in results2)
        and next(r for r in results1 if r.video_id == vid).is_relevant_predicted
        != next(r for r in results2 if r.video_id == vid).is_relevant_predicted
    )

    div_rows = _divergence_rows(results1, results2, entries_by_id)

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Eval Report — {html.escape(summary1.stage)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Eval Report — Stage: {html.escape(summary1.stage)}</h1>
<p>Comparando <strong>{html.escape(run1_path.name)}</strong> vs <strong>{html.escape(run2_path.name)}</strong></p>

<h2>Métricas</h2>
<div class="cards">
{_metrics_card(summary1, "Run 1: " + summary1.backend + " v" + summary1.prompt_version)}
{_metrics_card(summary2, "Run 2: " + summary2.backend + " v" + summary2.prompt_version)}
</div>

<h2>Divergências ({diverge_count} de {len(set(r.video_id for r in results1 + results2))} vídeos)</h2>
<table>
<thead>
<tr>
  <th>Video ID</th>
  <th>Título</th>
  <th>Run 1</th>
  <th>Run 2</th>
  <th>Esperado</th>
</tr>
</thead>
<tbody>
{div_rows}
</tbody>
</table>

</body>
</html>
"""
    output_path.write_text(html_content, encoding="utf-8")
