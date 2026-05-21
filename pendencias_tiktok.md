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
| 2026-05-18T19:43:31Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T19:43:31Z | TT_002 | unschedule |  |
| 2026-05-18T19:43:31Z | TT_003 | delete |  |
| 2026-05-18T19:43:31Z | TT_004 | fetch_status |  |
| 2026-05-18T19:58:54Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T19:58:54Z | TT_002 | unschedule |  |
| 2026-05-18T19:58:54Z | TT_003 | delete |  |
| 2026-05-18T19:58:54Z | TT_004 | fetch_status |  |
| 2026-05-18T20:01:12Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T20:01:12Z | TT_002 | unschedule |  |
| 2026-05-18T20:01:12Z | TT_003 | delete |  |
| 2026-05-18T20:01:12Z | TT_004 | fetch_status |  |
| 2026-05-18T20:02:24Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T20:02:24Z | TT_002 | unschedule |  |
| 2026-05-18T20:02:24Z | TT_003 | delete |  |
| 2026-05-18T20:02:24Z | TT_004 | fetch_status |  |
| 2026-05-18T20:06:19Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T20:06:19Z | TT_002 | unschedule |  |
| 2026-05-18T20:06:19Z | TT_003 | delete |  |
| 2026-05-18T20:06:19Z | TT_004 | fetch_status |  |
| 2026-05-18T20:10:18Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T20:10:18Z | TT_002 | unschedule |  |
| 2026-05-18T20:10:18Z | TT_003 | delete |  |
| 2026-05-18T20:10:18Z | TT_004 | fetch_status |  |
| 2026-05-18T20:14:36Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T20:14:36Z | TT_002 | unschedule |  |
| 2026-05-18T20:14:36Z | TT_003 | delete |  |
| 2026-05-18T20:14:36Z | TT_004 | fetch_status |  |
| 2026-05-18T20:27:34Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T20:27:34Z | TT_002 | unschedule |  |
| 2026-05-18T20:27:34Z | TT_003 | delete |  |
| 2026-05-18T20:27:34Z | TT_004 | fetch_status |  |
| 2026-05-18T21:01:58Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:01:58Z | TT_002 | unschedule |  |
| 2026-05-18T21:01:58Z | TT_003 | delete |  |
| 2026-05-18T21:01:58Z | TT_004 | fetch_status |  |
| 2026-05-18T21:05:42Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:05:42Z | TT_002 | unschedule |  |
| 2026-05-18T21:05:42Z | TT_003 | delete |  |
| 2026-05-18T21:05:42Z | TT_004 | fetch_status |  |
| 2026-05-18T21:20:39Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:20:39Z | TT_002 | unschedule |  |
| 2026-05-18T21:20:39Z | TT_003 | delete |  |
| 2026-05-18T21:20:39Z | TT_004 | fetch_status |  |
| 2026-05-18T21:21:53Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:21:53Z | TT_002 | unschedule |  |
| 2026-05-18T21:21:53Z | TT_003 | delete |  |
| 2026-05-18T21:21:53Z | TT_004 | fetch_status |  |
| 2026-05-18T21:24:21Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:24:21Z | TT_002 | unschedule |  |
| 2026-05-18T21:24:21Z | TT_003 | delete |  |
| 2026-05-18T21:24:21Z | TT_004 | fetch_status |  |
| 2026-05-18T21:29:45Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:29:45Z | TT_002 | unschedule |  |
| 2026-05-18T21:29:45Z | TT_003 | delete |  |
| 2026-05-18T21:29:45Z | TT_004 | fetch_status |  |
| 2026-05-18T21:31:23Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:31:23Z | TT_002 | unschedule |  |
| 2026-05-18T21:31:23Z | TT_003 | delete |  |
| 2026-05-18T21:31:23Z | TT_004 | fetch_status |  |
| 2026-05-18T21:31:37Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:31:37Z | TT_002 | unschedule |  |
| 2026-05-18T21:31:37Z | TT_003 | delete |  |
| 2026-05-18T21:31:37Z | TT_004 | fetch_status |  |
| 2026-05-18T21:32:49Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:32:49Z | TT_002 | unschedule |  |
| 2026-05-18T21:32:49Z | TT_003 | delete |  |
| 2026-05-18T21:32:49Z | TT_004 | fetch_status |  |
| 2026-05-18T21:33:53Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:33:53Z | TT_002 | unschedule |  |
| 2026-05-18T21:33:53Z | TT_003 | delete |  |
| 2026-05-18T21:33:53Z | TT_004 | fetch_status |  |
| 2026-05-18T21:34:29Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:34:29Z | TT_002 | unschedule |  |
| 2026-05-18T21:34:29Z | TT_003 | delete |  |
| 2026-05-18T21:34:29Z | TT_004 | fetch_status |  |
| 2026-05-18T21:34:50Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:34:50Z | TT_002 | unschedule |  |
| 2026-05-18T21:34:50Z | TT_003 | delete |  |
| 2026-05-18T21:34:50Z | TT_004 | fetch_status |  |
| 2026-05-18T21:35:36Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-18T21:35:36Z | TT_002 | unschedule |  |
| 2026-05-18T21:35:36Z | TT_003 | delete |  |
| 2026-05-18T21:35:36Z | TT_004 | fetch_status |  |
| 2026-05-19T00:54:31Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T00:54:31Z | TT_002 | unschedule |  |
| 2026-05-19T00:54:31Z | TT_003 | delete |  |
| 2026-05-19T00:54:31Z | TT_004 | fetch_status |  |
| 2026-05-19T00:55:25Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T00:55:25Z | TT_002 | unschedule |  |
| 2026-05-19T00:55:25Z | TT_003 | delete |  |
| 2026-05-19T00:55:25Z | TT_004 | fetch_status |  |
| 2026-05-19T11:54:51Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T11:54:51Z | TT_002 | unschedule |  |
| 2026-05-19T11:54:51Z | TT_003 | delete |  |
| 2026-05-19T11:54:51Z | TT_004 | fetch_status |  |
| 2026-05-19T12:10:41Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T12:10:41Z | TT_002 | unschedule |  |
| 2026-05-19T12:10:41Z | TT_003 | delete |  |
| 2026-05-19T12:10:41Z | TT_004 | fetch_status |  |
| 2026-05-19T12:45:49Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T12:45:49Z | TT_002 | unschedule |  |
| 2026-05-19T12:45:49Z | TT_003 | delete |  |
| 2026-05-19T12:45:49Z | TT_004 | fetch_status |  |
| 2026-05-19T14:07:28Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T14:07:28Z | TT_002 | unschedule |  |
| 2026-05-19T14:07:28Z | TT_003 | delete |  |
| 2026-05-19T14:07:28Z | TT_004 | fetch_status |  |
| 2026-05-19T21:28:06Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T21:28:06Z | TT_002 | unschedule |  |
| 2026-05-19T21:28:06Z | TT_003 | delete |  |
| 2026-05-19T21:28:06Z | TT_004 | fetch_status |  |
| 2026-05-19T21:33:12Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T21:33:12Z | TT_002 | unschedule |  |
| 2026-05-19T21:33:12Z | TT_003 | delete |  |
| 2026-05-19T21:33:12Z | TT_004 | fetch_status |  |
| 2026-05-19T21:34:38Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T21:34:38Z | TT_002 | unschedule |  |
| 2026-05-19T21:34:38Z | TT_003 | delete |  |
| 2026-05-19T21:34:38Z | TT_004 | fetch_status |  |
| 2026-05-19T21:55:24Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T21:55:24Z | TT_002 | unschedule |  |
| 2026-05-19T21:55:24Z | TT_003 | delete |  |
| 2026-05-19T21:55:24Z | TT_004 | fetch_status |  |
| 2026-05-19T21:57:00Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T21:57:00Z | TT_002 | unschedule |  |
| 2026-05-19T21:57:00Z | TT_003 | delete |  |
| 2026-05-19T21:57:00Z | TT_004 | fetch_status |  |
| 2026-05-19T23:26:58Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T23:26:58Z | TT_002 | unschedule |  |
| 2026-05-19T23:26:58Z | TT_003 | delete |  |
| 2026-05-19T23:26:58Z | TT_004 | fetch_status |  |
| 2026-05-19T23:28:18Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-19T23:28:18Z | TT_002 | unschedule |  |
| 2026-05-19T23:28:18Z | TT_003 | delete |  |
| 2026-05-19T23:28:18Z | TT_004 | fetch_status |  |
| 2026-05-20T00:58:29Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T00:58:29Z | TT_002 | unschedule |  |
| 2026-05-20T00:58:29Z | TT_003 | delete |  |
| 2026-05-20T00:58:29Z | TT_004 | fetch_status |  |
| 2026-05-20T01:49:49Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T01:49:49Z | TT_002 | unschedule |  |
| 2026-05-20T01:49:49Z | TT_003 | delete |  |
| 2026-05-20T01:49:49Z | TT_004 | fetch_status |  |
| 2026-05-20T02:44:43Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T02:44:43Z | TT_002 | unschedule |  |
| 2026-05-20T02:44:43Z | TT_003 | delete |  |
| 2026-05-20T02:44:43Z | TT_004 | fetch_status |  |
| 2026-05-20T02:58:09Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T02:58:09Z | TT_002 | unschedule |  |
| 2026-05-20T02:58:09Z | TT_003 | delete |  |
| 2026-05-20T02:58:09Z | TT_004 | fetch_status |  |
| 2026-05-20T02:59:09Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T02:59:09Z | TT_002 | unschedule |  |
| 2026-05-20T02:59:09Z | TT_003 | delete |  |
| 2026-05-20T02:59:09Z | TT_004 | fetch_status |  |
| 2026-05-20T03:39:38Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T03:39:38Z | TT_002 | unschedule |  |
| 2026-05-20T03:39:38Z | TT_003 | delete |  |
| 2026-05-20T03:39:38Z | TT_004 | fetch_status |  |
| 2026-05-20T03:49:18Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T03:49:18Z | TT_002 | unschedule |  |
| 2026-05-20T03:49:18Z | TT_003 | delete |  |
| 2026-05-20T03:49:18Z | TT_004 | fetch_status |  |
| 2026-05-20T14:13:07Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T14:13:07Z | TT_002 | unschedule |  |
| 2026-05-20T14:13:07Z | TT_003 | delete |  |
| 2026-05-20T14:13:07Z | TT_004 | fetch_status |  |
| 2026-05-20T15:41:44Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T15:41:44Z | TT_002 | unschedule |  |
| 2026-05-20T15:41:44Z | TT_003 | delete |  |
| 2026-05-20T15:41:44Z | TT_004 | fetch_status |  |
| 2026-05-20T17:01:14Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T17:01:14Z | TT_002 | unschedule |  |
| 2026-05-20T17:01:14Z | TT_003 | delete |  |
| 2026-05-20T17:01:14Z | TT_004 | fetch_status |  |
| 2026-05-20T17:01:45Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T17:01:45Z | TT_002 | unschedule |  |
| 2026-05-20T17:01:45Z | TT_003 | delete |  |
| 2026-05-20T17:01:45Z | TT_004 | fetch_status |  |
| 2026-05-20T17:10:26Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T17:10:26Z | TT_002 | unschedule |  |
| 2026-05-20T17:10:26Z | TT_003 | delete |  |
| 2026-05-20T17:10:26Z | TT_004 | fetch_status |  |
| 2026-05-20T19:30:10Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T19:30:10Z | TT_002 | unschedule |  |
| 2026-05-20T19:30:10Z | TT_003 | delete |  |
| 2026-05-20T19:30:10Z | TT_004 | fetch_status |  |
| 2026-05-20T19:30:54Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T19:30:54Z | TT_002 | unschedule |  |
| 2026-05-20T19:30:54Z | TT_003 | delete |  |
| 2026-05-20T19:30:54Z | TT_004 | fetch_status |  |
| 2026-05-20T23:13:57Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-20T23:13:57Z | TT_002 | unschedule |  |
| 2026-05-20T23:13:57Z | TT_003 | delete |  |
| 2026-05-20T23:13:57Z | TT_004 | fetch_status |  |
| 2026-05-21T03:39:07Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:39:07Z | TT_002 | unschedule |  |
| 2026-05-21T03:39:07Z | TT_003 | delete |  |
| 2026-05-21T03:39:07Z | TT_004 | fetch_status |  |
| 2026-05-21T03:41:17Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:41:17Z | TT_002 | unschedule |  |
| 2026-05-21T03:41:17Z | TT_003 | delete |  |
| 2026-05-21T03:41:17Z | TT_004 | fetch_status |  |
| 2026-05-21T03:42:49Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:42:49Z | TT_002 | unschedule |  |
| 2026-05-21T03:42:49Z | TT_003 | delete |  |
| 2026-05-21T03:42:49Z | TT_004 | fetch_status |  |
| 2026-05-21T03:43:24Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:43:24Z | TT_002 | unschedule |  |
| 2026-05-21T03:43:24Z | TT_003 | delete |  |
| 2026-05-21T03:43:24Z | TT_004 | fetch_status |  |
| 2026-05-21T03:43:57Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:43:57Z | TT_002 | unschedule |  |
| 2026-05-21T03:43:57Z | TT_003 | delete |  |
| 2026-05-21T03:43:57Z | TT_004 | fetch_status |  |
| 2026-05-21T03:47:01Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:47:01Z | TT_002 | unschedule |  |
| 2026-05-21T03:47:01Z | TT_003 | delete |  |
| 2026-05-21T03:47:01Z | TT_004 | fetch_status |  |
| 2026-05-21T03:52:36Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:52:36Z | TT_002 | unschedule |  |
| 2026-05-21T03:52:36Z | TT_003 | delete |  |
| 2026-05-21T03:52:36Z | TT_004 | fetch_status |  |
| 2026-05-21T03:53:33Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:53:33Z | TT_002 | unschedule |  |
| 2026-05-21T03:53:33Z | TT_003 | delete |  |
| 2026-05-21T03:53:33Z | TT_004 | fetch_status |  |
| 2026-05-21T03:54:36Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:54:36Z | TT_002 | unschedule |  |
| 2026-05-21T03:54:36Z | TT_003 | delete |  |
| 2026-05-21T03:54:36Z | TT_004 | fetch_status |  |
| 2026-05-21T03:56:51Z | TT_001 | update_metadata | title='x' description=None tags=None |
| 2026-05-21T03:56:51Z | TT_002 | unschedule |  |
| 2026-05-21T03:56:51Z | TT_003 | delete |  |
| 2026-05-21T03:56:51Z | TT_004 | fetch_status |  |
