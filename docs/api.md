# API REST — Canal Soberania

Referência dos endpoints FastAPI expostos pelo `cs serve`. Consumida pelo frontend Tauri (Onda 3+) e utilizável diretamente via `curl` para debug.

## Inicialização

```bash
cs serve                       # localhost:8000
cs serve --host 0.0.0.0        # expõe na LAN (acesso do celular)
cs serve --port 9000           # porta customizada
```

Na primeira execução, gera o token e o grava em dois locais (ambos chmod 600):
- `DATA_DIR/.api_token` — usado internamente pelo backend
- `~/.config/canal-soberania/.api_token` — caminho XDG lido pelo Tauri

O XDG tem prioridade: se existir, é reutilizado. O caminho XDG é impresso no stdout ao iniciar (`"Token salvo em ~/.config/canal-soberania/.api_token"`).

## Autenticação

Todos os endpoints (exceto `/health`) exigem:

```
Authorization: Bearer <token>
```

Alternativa via query param (menos seguro, útil para SSE em browser):
```
GET /events?token=<token>
```

O token fica em `DATA_DIR/.api_token`. No cliente Tauri, leia via `readTextFile('~/.config/canal-soberania/.api_token')` e injete no header de todo fetch.

---

## Endpoints

### Health

```
GET /health
```
Não requer auth. Retorna `{"status": "ok"}`.

---

### Vídeos

```
GET /videos
GET /videos?status=discovered&limit=50
```
Lista vídeos. `status` aceita qualquer `VideoStatus`. `limit` padrão 200.

```
GET /videos/{video_id}
```
Retorna um vídeo ou 404.

```
POST /videos/{video_id}/approve
POST /videos/{video_id}/reject
```
Retorna `{"status": "ok", "video_id": "..."}` ou 400 se transição inválida.

---

### Clipes

```
GET /clips
GET /clips?status=metadata_ready&video_id=dQw4w9WgXcQ&limit=50
```
Lista clipes. Filtros opcionais por `status` e `video_id`.

```
GET /clips/{clip_id}
```
Retorna um clipe ou 404.

```
POST /clips/{clip_id}/approve
```
Aprova e dispara upload YouTube em daemon thread. Retorna imediatamente:
```json
{"status": "upload_started", "clip_id": "..."}
```
Progresso via `GET /events` (SSE). Requer clipe em status `metadata_ready`; retorna 400 se outro status.

```
POST /clips/{clip_id}/reject
```
Marca como `rejected_youtube`. Retorna `{"status": "rejected", "clip_id": "..."}`.

```
POST /clips/{clip_id}/trim
Content-Type: application/json
{"start_s": 10.5, "end_s": 65.0}
```
Atualiza `start_s`/`end_s`. Retorna 400 se `end_s <= start_s`.

```
PATCH /clips/{clip_id}
Content-Type: application/json
{
  "hook": "...",
  "payoff": "...",
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2"],
  "youtube_publish_at": "2025-06-01T15:00:00Z",
  "render_vertical": true,
  "render_horizontal": false
}
```
Todos os campos são opcionais. Chama `update_clip_text()` no service. Retorna `{"status": "updated", "clip_id": "..."}`.

```
DELETE /clips/{clip_id}
```
Remove o clipe do banco (irreversível). Retorna `{"status": "discarded", "clip_id": "..."}`.

---

### Canais

```
GET /canais
GET /canais?apenas_ativos=true
```

```
POST /canais
Content-Type: application/json
{canal schema completo — ver Canal model}
```

```
PUT /canais/{canal_id}
DELETE /canais/{canal_id}
POST /canais/{canal_id}/toggle-ativo
```

---

### Stages e Pipeline

```
POST /stages/{name}/run
```
Inicia um stage em daemon thread. Retorna imediatamente `{"status": "started", "stage": "..."}`.

Stages disponíveis:
| name | descrição |
|---|---|
| `discover` | Busca novos vídeos nos canais |
| `triage_metadata` | Stage 1: title + desc + tags |
| `triage_caption` | Stage 2: auto-captions YouTube |
| `download` | Download de áudio (+ vídeo se aprovado) |
| `transcribe` | Whisper |
| `triage_transcript` | Stage 3: análise do transcript completo |
| `find_clips` | Identifica momentos virais (3–8 por vídeo) |
| `edit` | ffmpeg: corte, reframe 9:16, legendas |
| `thumbnail` | Pillow: thumb com template |
| `generate_metadata` | Claude gera título/desc/tags |
| `upload_youtube` | Upload via YouTube Data API |
| `upload_tiktok` | Fila manual ou bot |
| `sync_youtube` | Atualiza views/likes/status de publicados |
| `auto` | Roda todos os stages pendentes em sequência |

```
POST /pipeline/cancel
```
Sinaliza cancelamento (flag testada em cada iteração dos stages). Retorna `{"status": "cancelling"}`.

```
POST /pipeline/reset
```
Reseta vídeos/clipes com heartbeat expirado (processo morreu mid-execução). Retorna `{"reset_videos": N, "reset_clips": M}`.

---

### Stats

```
GET /stats/summary
```
Retorna contagem por status de vídeo:
```json
{"discovered": 12, "triage_metadata_passed": 8, "metadata_ready": 3, ...}
```

```
GET /stats/costs
```
Retorna custo total do mês corrente:
```json
{"total_usd": 4.23}
```

```
GET /stats/costs/detail
```
Retorna últimas 90 linhas da tabela `api_costs` (90 dias):
```json
[
  {"date": "2025-05-19", "provider": "anthropic", "model": "claude-haiku-4-5", "tokens_in": 50000, "tokens_out": 2000, "requests": 18, "cost_usd": 0.063},
  ...
]
```

---

### Inbox

```
GET /inbox
```
Lista itens prioritizados para revisão do operador:
```json
{
  "items": [
    {"type": "clip", "priority": 1, "clip_id": "...", "hook": "...", ...},
    {"type": "video", "priority": 2, "video_id": "...", "title": "...", ...},
    {"type": "video", "priority": 3, "video_id": "...", "status": "processing_error", ...}
  ],
  "total": 3
}
```

Prioridades:
- **1** — clipes em `metadata_ready` (precisam de review humano)
- **2** — vídeos em `discovered` (aguardando triagem)
- **3** — vídeos em `processing_error` ou `transcribe_error` (precisam de atenção)

---

### Eventos SSE

```
GET /events
GET /events?token=<token>
```

Conecta ao stream de eventos do pipeline. Formato SSE padrão:

```
data: {"event_type": "stage_progress", "stage": "triage_metadata", "video_id": "dQw4w9WgXcQ", "status": "processing_error", "message": "..."}

data: {"event_type": "stage_complete", "stage": "edit", "clip_id": "dQw4w9WgXcQ_10_70"}

: heartbeat

```

Heartbeat a cada 15 segundos para manter a conexão viva. Reconectar após desconexão com `EventSource` nativo ou hook customizado.

**Hook React sugerido:**
```typescript
// lib/sse.ts
export function useSSE(token: string) {
  const queryClient = useQueryClient()

  useEffect(() => {
    const es = new EventSource(`/events?token=${token}`)
    es.onmessage = (e) => {
      const event = JSON.parse(e.data)
      // Invalida queries afetadas pelo tipo de evento
      if (event.event_type?.includes('clip')) {
        queryClient.invalidateQueries({ queryKey: ['clips'] })
        queryClient.invalidateQueries({ queryKey: ['inbox'] })
      }
      if (event.event_type?.includes('video')) {
        queryClient.invalidateQueries({ queryKey: ['videos'] })
        queryClient.invalidateQueries({ queryKey: ['inbox'] })
      }
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    }
    return () => es.close()
  }, [token, queryClient])
}
```

---

## Geração do cliente TypeScript

```bash
cd ui
pnpm dlx openapi-typescript http://localhost:8000/openapi.json -o src/lib/api.d.ts
```

Requer `cs serve` rodando. Re-executar sempre que um endpoint mudar.

---

## Exemplos curl

```bash
TOKEN=$(cat data/.api_token)

# Status geral
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/stats/summary | jq

# Inbox
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/inbox | jq '.items[].type'

# Rodar triagem metadata
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/stages/triage_metadata/run

# Stream de eventos (Ctrl+C para encerrar)
curl -s -N "http://localhost:8000/events?token=$TOKEN"

# Aprovar clipe
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/clips/dQw4w9WgXcQ_10_70/approve
```
