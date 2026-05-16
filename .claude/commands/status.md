---
description: Mostra resumo do estado atual do pipeline (vídeos por status, clipes pendentes, gasto do mês)
---

Execute os comandos abaixo em sequência e apresente um resumo em prosa com bullets curtos:

1. `cs status` — contagem global por status
2. `sqlite3 data/canal.db "SELECT * FROM v_status_summary;"`
3. `sqlite3 data/canal.db "SELECT clip_id, title, duracao_s FROM v_pending_youtube LIMIT 10;"`
4. `sqlite3 data/canal.db "SELECT clip_id, title FROM v_pending_tiktok LIMIT 10;"`
5. `sqlite3 data/canal.db "SELECT * FROM v_custo_mes_atual;"`
6. `tail -n 20 data/logs/pipeline_$(date +%F).log` (se existir)

Sinalize especialmente:
- Itens stuck (> 24h sem mudança de status) — listar `video_id` ou `clip_id`
- Custo do mês > $20 (alerta)
- Erros recentes (`status LIKE '%_error'`)
