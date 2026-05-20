# API REST — Canal Soberania

Referência dos endpoints FastAPI expostos pelo `cs serve`. Consumida pelo frontend Tauri (Onda 3+) e utilizável diretamente via `curl` para debug.

**Atualizado após Onda 6** — canais CRUD, discover adhoc, stats agregado, config R/W.

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
  "render_horizontal": false,
  "score_viral": 8
}
```
Todos os campos são opcionais. `score_viral` aceita 1–10 (int). Chama `update_clip_text()` no service. Retorna `{"status": "updated", "clip_id": "..."}`.

```
DELETE /clips/{clip_id}
```
Remove o clipe do banco (irreversível). Retorna `{"status": "discarded", "clip_id": "..."}`.

```
GET /clips/{clip_id}/source-video
```
Serve o arquivo de vídeo do clipe para o player HTML5. Preferência: `clip_path_vertical` → `clip_path_horizontal` → `video_path` do vídeo-fonte. Suporta `Range` requests (necessário para seeking no `<video>`). Requer auth via Bearer ou `?token=`.

```
GET /clips/{clip_id}/face-crop
```
Detecta a posição do rosto no vídeo-fonte usando `mediapipe` e retorna as coordenadas do crop 9:16. Se `mediapipe` não estiver disponível ou nenhum rosto for detectado, retorna crop centralizado.

```json
{
  "crop_x": 240,
  "crop_width": 405,
  "source_width": 1280,
  "source_height": 720
}
```

- `crop_x`: coluna de início do crop 9:16 no frame original (pixels)
- `crop_width`: largura do crop = `source_height × 9/16`
- Usado pelo `CropOverlay` canvas no frontend para renderizar a máscara 9:16

---

### Canais

Fonte de dados: SQLite (tabela `canais`), não o YAML. O YAML (`config/canais.yaml`) é apenas seed inicial; após a primeira importação, o banco é a fonte de verdade.

```
GET /canais
```
Retorna todos os canais cadastrados (`list[Canal]`).

```
POST /canais
Content-Type: application/json
```
Body: schema `Canal` completo. Retorna 201 com o canal criado.

```json
{
  "id": "flow_podcast",
  "nome": "Flow Podcast",
  "handle": "@FlowPodcast",
  "channel_url": "https://youtube.com/@FlowPodcast",
  "tema_primario": "variado",
  "peso": 0.7,
  "auto_publish": false,
  "tolerancia_cortes": "alta",
  "nota": "",
  "ativo": true
}
```

```
PUT /canais/{canal_id}
Content-Type: application/json
```
Body: schema `Canal` completo. O `id` no body deve ser igual ao `canal_id` do path (422 se divergir). Faz upsert.

```
PATCH /canais/{canal_id}/ativo
Content-Type: application/json
{"ativo": false}
```
Liga/desliga o canal sem editar os demais campos. Retorna `{"canal_id": "...", "ativo": false}`.

```
DELETE /canais/{canal_id}
```
Remove o canal do banco. Retorna `{"status": "deleted", "canal_id": "..."}`.

---

### Discover ad-hoc

```
POST /discover/adhoc
Content-Type: application/json
```

```json
{
  "channel_url_or_handle": "@NomeDoCanal",
  "persist": false,
  "janela_dias": 7,
  "max_videos": 20
}
```

Todos os campos exceto `channel_url_or_handle` são opcionais (defaults do `canais.yaml`).

- Retorna **202** imediatamente: `{"status": "started", "handle": "@NomeDoCanal"}`.
- O discover roda em daemon thread; acompanhe via SSE (`discover_adhoc_done`).
- Se `YOUTUBE_API_KEY` não estiver configurada, retorna **400** antes de disparar a thread.
- Se `persist = true`, o canal é salvo na tabela `canais` ao fim do discover.

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

```
GET /stats/by-canal
```
Retorna contagens por `canal_id` (JOIN videos + clips):
```json
[
  {
    "canal_id": "flow_podcast",
    "total_videos": 28,
    "videos_aprovados": 3,
    "clips_gerados": 12,
    "clips_publicados": 4
  },
  ...
]
```
`videos_aprovados` = vídeos em status `approved_for_clips`, `finding_clips` ou `clips_found`.
`clips_publicados` = clips em `uploaded_youtube`, `scheduled_youtube`, `uploaded_tiktok` ou `pending_tiktok_manual`.

```
GET /stats/throughput
```
Retorna throughput semanal das últimas 4 semanas (última data de 28 dias):
```json
[
  {
    "semana": "2026-19",
    "videos_descobertos": 134,
    "clips_criados": 10,
    "clips_publicados": 6
  },
  ...
]
```
`semana` = `strftime('%Y-%W', created_at)` (ano-semanaISO). Ordenado ASC.

---

### Config

Permite ler e persistir as configurações editáveis do backend. **Não expõe segredos** (API keys). Após salvar, reiniciar `cs serve` para aplicar.

```
GET /config
```
Retorna os valores atuais das chaves editáveis (lidos via `load_settings()`):
```json
{
  "LLM_BACKEND": "anthropic",
  "WHISPER_BACKEND": "local_cpu",
  "WHISPER_DEVICE": "cuda",
  "WHISPER_COMPUTE_TYPE": "float16",
  "OLLAMA_BASE_URL": "http://localhost:11434/v1/chat/completions",
  "OLLAMA_MODEL_TRIAGE": "qwen2.5:14b-instruct-q4_K_M",
  "OLLAMA_MODEL_DEEP": "qwen2.5:32b-instruct-q4_K_M",
  "ALERT_CHANNELS": "telegram",
  "ALERT_STUCK_THRESHOLD": 50,
  "TELEGRAM_CHAT_ID": "",
  "SMTP_HOST": "", "SMTP_PORT": 587, "SMTP_FROM": "", "SMTP_TO": "",
  "LOG_LEVEL": "INFO",
  "DRY_RUN": false,
  "PIPELINE_LOOP_INTERVAL": 60
}
```

```
PUT /config
Content-Type: application/json
{"LOG_LEVEL": "DEBUG", "PIPELINE_LOOP_INTERVAL": "120"}
```

- Aceita um subset das chaves acima (mais `SMTP_PASSWORD` e `TELEGRAM_BOT_TOKEN` — graváveis, não retornados no GET).
- Faz **merge não-destrutivo no `.env`**: atualiza apenas as linhas das chaves enviadas, preserva comentários e demais vars.
- Retorna `{"status": "saved", "restart_required": true, "updated": ["LOG_LEVEL", "PIPELINE_LOOP_INTERVAL"]}`.
- Chaves fora da whitelist retornam **400**.

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

**Hook React (`lib/sse.ts`):**
```typescript
// Uso básico (só invalida queries automaticamente)
const status = useSSE()   // "connecting" | "open" | "closed"

// Uso com callback (recebe cada evento)
useSSE((event) => {
  // event.type  = event_type da mensagem SSE (ex: "discover_adhoc_done")
  // event.data  = objeto JSON completo parseado
  if (event.type === "discover_adhoc_done") {
    const d = event.data as { handle: string; inserted: number }
    setHistory(prev => [...prev, { handle: d.handle, inserted: d.inserted }])
  }
})
```

O callback recebe **todos** os eventos; a invalidação de queries continua acontecendo automaticamente em paralelo.

**Eventos mais comuns do pipeline:**

| `event_type` | Dados relevantes |
|---|---|
| `stage_progress` | `stage`, `video_id`, `status`, `message` |
| `stage_complete` | `stage`, `clip_id` ou `video_id` |
| `stage_error` | `stage`, `error` |
| `discover_adhoc_done` | `handle`, `inserted`, `persisted` |
| `canal_upserted` | `canal_id` |
| `canal_deleted` | `canal_id` |

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
