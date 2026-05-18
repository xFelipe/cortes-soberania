# Pendências TikTok

Canal Soberania usa TikTok em modo de **fila manual** (stage `upload_tiktok` copia o `.mp4`
para `data/clips/pending_tiktok/` e você sobe pelo app). Operações que exigem API oficial
(update, delete, fetch_status) geram entradas neste arquivo automaticamente.

## O que falta para ativar a API oficial

1. **Criar app TikTok for Business**: https://developers.tiktok.com/apps
2. **Solicitar aprovação da Content Posting API** (pode levar semanas).
3. **Configurar `.env`**:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   ```
4. **Implementar OAuth flow** em `src/canal_soberania/platforms/tiktok.py`
   (substituir `TikTokPlatformClient.upload` pelo endpoint `/v2/video/upload/`).
5. **Implementar `update_metadata`** via `/v2/video/query/` + updates de metadados.
6. **Implementar `delete`** via endpoint de deleção da API.
7. Remover chamadas a `record_tiktok_pending()` após cada operação ser implementada.

Alternativa ao passo 1-2: **`tiktok-uploader`** (browser automation), recomendado apenas
em VPS dedicada — ver `docs/pipeline.md §TikTok`.

---

## Operações pendentes (registradas automaticamente)

<!-- O serviço adiciona linhas aqui via record_tiktok_pending() -->
| Timestamp | clip_id | Operação | Detalhes |
|---|---|---|---|
| 2026-05-18T12:53:28Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T12:53:28Z | TT_002 | unschedule |  |
| 2026-05-18T12:53:28Z | TT_003 | delete |  |
| 2026-05-18T12:53:28Z | TT_004 | fetch_status |  |
| 2026-05-18T13:03:59Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T13:03:59Z | TT_002 | unschedule |  |
| 2026-05-18T13:03:59Z | TT_003 | delete |  |
| 2026-05-18T13:03:59Z | TT_004 | fetch_status |  |
