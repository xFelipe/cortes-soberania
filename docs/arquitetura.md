# Arquitetura

## Visão de alto nível

Operação single-tenant em máquina local (PC com RTX 4060 + 32GB RAM). Cron dispara scripts que avançam o estado dos vídeos no SQLite. Cada vídeo passa por **triagem em camadas** de custo crescente: barato no início, caro só no fim.

A camada de apresentação migrou de PySide6 (GUI Python) para **Tauri + React**, consumindo a **FastAPI** que expõe o `PipelineService` via REST + SSE.

```
┌────────────────────────────────────────────────────────────────────┐
│ PC local (RTX 4060 + 32GB)                                         │
│                                                                    │
│  ┌─────────────────┐  HTTP/SSE  ┌──────────────────────────────┐  │
│  │ Tauri + React   │ ◄────────► │ FastAPI :8000  (cs serve)    │  │
│  │ (ui/)           │            │  Bearer token auth            │  │
│  └─────────────────┘            │  ↓                            │  │
│                                 │  PipelineService              │  │
│  ┌─────────────────┐            │  ├─ LLMBackend (plugável)    │  │
│  │ cron (30min)    │────────────►  │   hybrid: Ollama + Sonnet  │  │
│  │ run_pipeline.sh │            │  ├─ Transcriber (plugável)   │  │
│  └─────────────────┘            │  │   local_cuda: faster-whis │  │
│                                 │  ├─ EventBus → SSE           │  │
│  ┌─────────────────┐            │  └─ SQLite data/canal.db     │  │
│  │ Ollama :11434   │◄───────────►                               │  │
│  │ Qwen 14B Q4     │            └──────────────────────────────┘  │
│  │ Qwen 32B Q4     │                                               │
│  └─────────────────┘                                               │
└────────────────────────────────────────────────────────────────────┘
```

**Backends plugáveis via env var:**

| `LLM_BACKEND` | Triagem (barata) | Análise profunda |
|---|---|---|
| `anthropic` (padrão) | claude-haiku-4-5 | claude-sonnet-4-6 |
| `hybrid` | Qwen 2.5 14B Q4 via Ollama | claude-sonnet-4-6 |
| `ollama` | Qwen 2.5 14B Q4 | Qwen 2.5 32B Q4 |

| `WHISPER_BACKEND` | Transcrição |
|---|---|
| `local_cpu` (padrão) | faster-whisper CPU (int8) |
| `local_cuda` | faster-whisper CUDA (float16, RTX 4060) |
| `groq` | Groq API (cloud gratuito, escape hatch) |

```
┌──────────────────────────────────────────────────────────────────────┐
│                              CRON                                    │
│  discover (8h, 20h) | run_pipeline (cada 30min) | backup (3h)        │
└──────────────────┬───────────────────────────────────┬───────────────┘
                   │                                   │
                   ▼                                   ▼
┌──────────────────────────┐         ┌─────────────────────────────────┐
│      DISCOVER            │         │     RUN PIPELINE (loop)         │
│  YouTube Data API →      │         │  Para cada video pendente:      │
│  insere videos novos     │         │  Stage 1 → 2 → 3 ... → 12       │
└──────────┬───────────────┘         └──────────┬──────────────────────┘
           │                                    │
           └─────────┬──────────────────────────┘
                     ▼
            ┌────────────────────┐
            │   SQLite           │
            │   (canal.db)       │
            │   videos, clips,   │
            │   triage_results,  │
            │   uploads          │
            └────────────────────┘
```

## Pipeline em camadas (custo crescente)

```
┌────────────────────────────────────────────────────────────────────────────┐
│                                                                            │
│   STAGE 1: triage_metadata          ░░░░░░  ~$0.001/video (Haiku)          │
│   título + descrição + tags + comentários                                  │
│   └─► REJEITA cedo se não cita tema       ─────────────────────────┐       │
│                                                                    │       │
│   STAGE 2: triage_caption           ░░░░░░░░  ~$0.005/video (Haiku)│       │
│   baixa auto-caption do YouTube                                    │       │
│   └─► REJEITA se conteúdo desviar do tema  ────────────────────────┤       │
│                                                                    │       │
│   STAGE 3: download                 █░░░░  ~10s + storage          │       │
│   yt-dlp baixa áudio (sempre); vídeo só se vai cortar              │       │
│                                                                    │       │
│   STAGE 4: transcribe               ██░░░░  ~3min CPU (Whisper)    │       │
│   faster-whisper large-v3                                          │       │
│                                                                    │       │
│   STAGE 5: triage_transcript        ███░░  ~$0.03 (Sonnet)         │       │
│   análise final do conteúdo completo                               │       │
│   └─► REJEITA se análise profunda discordar  ──────────────────────┤       │
│                                                                    │       │
│   STAGE 6: find_clips               ███░░  ~$0.05 (Sonnet)         │       │
│   identifica 3-8 momentos virais relevantes ao tema                │       │
│                                                                    │       │
│   STAGE 7: edit                     ████░  ~5min CPU (ffmpeg)      │       │
│   corte, reframe 9:16, legenda dinâmica, intro/outro               │       │
│                                                                    │       │
│   STAGE 8: thumbnail                █░░░░  ~5s (Pillow)            │       │
│                                                                    │       │
│   STAGE 9: metadata                 ██░░░  ~$0.01 (Sonnet)         │       │
│   título, descrição, tags                                          │       │
│                                                                    │       │
│   STAGE 10: upload_youtube          ██░░░  ~30s (API)              │       │
│                                                                    │       │
│   STAGE 11: upload_tiktok           ░░░░░  fila manual (MVP)       │       │
│                                                                    │       │
└────────────────────────────────────────────────────────────────────┴───────┘
                                                                     │
                                              videos rejeitados ◄────┘
                                              (status = *_rejected)
```

**Insight central:** a triagem em 3 camadas (metadata → caption → transcript) reduz drasticamente o custo de Whisper e de análise profunda. Estimativa: dos vídeos descobertos, **~60% rejeitados na Stage 1**, **mais 20% na Stage 2**, e dos 20% restantes que rodam Whisper, ~25% caem na Stage 5. Sobra **~15% que viram clipes**. Isso mantém o custo médio mensal abaixo de R$ 200 nos 6 canais iniciais.

## Camada de apresentação (FastAPI + Tauri)

### FastAPI (`src/canal_soberania/api/`)

A API REST expõe o `PipelineService` para qualquer cliente HTTP. Iniciada via `cs serve`.

```
┌────────────────────────────────────────────────────────────────┐
│  FastAPI :8000 (create_app)                                    │
│                                                                │
│  Auth: Bearer token em DATA_DIR/.api_token (chmod 600)         │
│         gerado automaticamente na 1ª execução de cs serve      │
│                                                                │
│  Routers                                                       │
│  ├─ GET /videos, /videos/{id}                                  │
│  │  POST /{id}/approve, /{id}/reject                           │
│  ├─ GET /clips, /clips/{id}                                    │
│  │  POST /{id}/approve (daemon thread → upload_youtube)        │
│  │  POST /{id}/reject, /{id}/trim, PATCH /{id}, DELETE /{id}  │
│  ├─ GET /canais + CRUD                                         │
│  ├─ POST /stages/{name}/run (daemon thread, retorna 202)       │
│  │  POST /pipeline/cancel, /pipeline/reset                     │
│  ├─ GET /stats/summary, /costs, /costs/detail                  │
│  ├─ GET /inbox  (lista priorizada: clips prio1, vídeos prio2+) │
│  ├─ GET /events (SSE stream do EventBus, heartbeat 15s)        │
│  └─ GET /health                                                │
│                                                                │
│  SSEBridge                                                     │
│  └─ EventBus (sync, threads) → asyncio.Queue por cliente       │
│     loop.call_soon_threadsafe() garante thread safety          │
└────────────────────────────────────┬───────────────────────────┘
                                     │ DI via request.app.state
                                     ▼
                          PipelineService (core, sem FastAPI)
```

**Referência completa de endpoints:** `docs/api.md`

### Tauri + React (`ui/`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Tauri shell (Rust)                                             │
│  └─ Abre WebView com React 19                                   │
│     ├─ lib/api.ts: cliente HTTP typed (fetch + Bearer token)   │
│     │  token lido de ~/.config/canal-soberania/.api_token      │
│     ├─ lib/sse.ts: hook useSSE() → invalida queries TanStack   │
│     ├─ lib/theme.tsx: ThemeProvider (OS/light/dark, localStorage)│
│     ├─ Sidebar 3.75rem + StatusFooter 1.75rem + <Outlet>       │
│     └─ Rotas: Inbox · Biblioteca · Operação · Stats · Config   │
│        Hotkeys: Ctrl+1..5 (navegar), Ctrl+K (command palette)  │
└─────────────────────────────────────────────────────────────────┘

Stack: Vite 7 · Tailwind v4 · shadcn/ui (Radix/Nova) · TanStack Router/Query
Auth: token em ~/.config/canal-soberania/.api_token (XDG, chmod 600)
      cs serve grava em ambos: DATA_DIR/.api_token e XDG path
```

## Modelo de dados (visão lógica)

```
videos
├─ video_id (PK, YouTube ID, 11 chars)
├─ canal_id (FK → canais.yaml)
├─ title, description, tags, published_at
├─ duration_s
├─ status: discovered | triage_metadata_passed | ... | uploaded | rejected_*
├─ audio_path, video_path, transcript_path
├─ caption_path                              ← auto-caption do YouTube
└─ created_at, updated_at

triage_results
├─ id (PK)
├─ video_id (FK)
├─ stage: metadata | caption | transcript
├─ score (0-10)
├─ themes_detected (JSON array)
├─ rationale (texto livre, salvo pro debug)
├─ model_used, tokens_in, tokens_out, cost_usd
└─ created_at

clips
├─ clip_id (PK = "{video_id}_{start_s}_{end_s}")
├─ video_id (FK)
├─ start_s, end_s
├─ hook (texto), payoff (texto), tema_soberania
├─ score_viral (0-10)
├─ status: identified | edited | metadata_ready | scheduled_youtube | uploaded_youtube | pending_tiktok_manual | uploaded_tiktok
├─ clip_path_vertical, clip_path_horizontal, thumb_path
├─ title, description, tags (JSON)
├─ youtube_id, tiktok_id
└─ created_at, updated_at

api_costs              ← agregação para acompanhar gasto
├─ date (PK)
├─ provider (anthropic | youtube | ...)
├─ tokens_in, tokens_out, requests
└─ cost_usd
```

## Decisões arquiteturais (ADRs em prosa)

### Por que SQLite e não Postgres
Operador único, < 10k linhas previsíveis em 12 meses. Backup é `cp`. Zero ops. Trocar depois, se precisar.

### Por que cron e não Airflow
Pipeline linear, sem fan-out massivo. Cron + idempotência por status na tabela faz o mesmo trabalho com 1% da complexidade operacional. Airflow exige scheduler próprio, metadb separado, workers dedicados e UI — overhead injustificável para um operador único.

### Quando considerar Celery ou Prefect
**Celery** faz sentido se o pipeline precisar de paralelismo real: ex., transcrever 10 vídeos simultaneamente em workers separados, ou rodar edições em paralelo. O broker (Redis) é leve e já rodaria na mesma máquina. **Prefect** faz sentido se a observabilidade de DAG se tornar crítica — ele é Python-first, o servidor local consome ~200MB e adiciona UI de runs/retry sem mudar o código de negócio. Ambos são aceitáveis; a decisão de adotar deve ser motivada por demanda concreta (gargalo de throughput ou dificuldade de debugar falhas), não antecipação.

### Por que SQLite no lugar de Pydantic Models como verdade
SQLite é o estado durável. Pydantic é o **shape** trafegado entre módulos. Não confundir.

### Por que Haiku para triagem e Sonnet para análise
Hierarquia de custo: Haiku ~$1/M tokens input, Sonnet ~$3/M. Triagem de 100s de vídeos diários precisa ser barata; análise final de poucos vídeos pode ser cara. Diferença de qualidade só importa na ponta.

### Por que faster-whisper local e não Whisper via API
Throughput diário esperado: 2-5h de áudio. CPU decente (ou GPU sob demanda RunPod) é gratuito vs ~$0.006/min na API OpenAI (~R$5/dia). Em 1 mês paga uma GPU usada.

### Por que ffmpeg direto e não MoviePy
MoviePy é wrapper bonito mas com performance ruim e bugs em edge cases (concatenação com audio out-of-sync). ffmpeg via subprocess é determinístico, rápido, e a sintaxe se torna familiar rápido.

### Por que TikTok manual no MVP
API oficial exige aprovação (semanas/meses). Automação não oficial arrisca ban. 5 minutos por dia de upload manual é aceitável até o canal justificar o investimento na API oficial.

### Por que FastAPI e não expor PipelineService direto no Tauri via sidecar Rust
FastAPI permite testar endpoints com curl/httpx, gerar cliente TypeScript via OpenAPI, e no futuro expor na LAN para acesso via celular — tudo sem mudar a lógica do `PipelineService`. O overhead de um processo HTTP local é desprezível (< 5ms latência loopback).

### Por que SSE e não WebSocket para eventos do pipeline
SSE é unidirecional (servidor → cliente), exatamente o que o EventBus precisa. WebSocket adicionaria complexidade bidirecional desnecessária. SSE reconecta nativamente no browser/Tauri sem código extra.

### Por que LLMBackend/Transcriber via Protocol e não herança
Protocol (structural subtyping) permite que `LLMClient` e `OpenRouterClient` existentes satisfaçam a interface sem modificação retroativa. Facilita mocking em testes (qualquer objeto com o método correto funciona). Compatível com `mypy --strict` sem casting excessivo.

### Por que Hybrid como padrão de LLM_BACKEND
Qwen 2.5 14B Q4 na GPU local custa R$0 e tem latência < 3s — adequado para triagem de metadata/caption onde volume é alto (dezenas de vídeos/dia). Sonnet mantido para análise profunda e geração de metadados onde qualidade é crítica. Validar com `evals/` (Onda 9) antes de promover Qwen para análise profunda.

## Falhas previstas e mitigações

| Falha | Probabilidade | Mitigação |
|---|---|---|
| YouTube muda HTML / yt-dlp quebra | Média | `uv sync` semanal; pipeline detecta falha de download e re-tenta com versão nova |
| Cota YouTube Data API estourada | Baixa | 10k unidades/dia. Discover gasta ~1 por canal-listagem, ~3 por vídeo (snippet+contentDetails+comments). Cabe folgado. |
| Claude API rate limit | Baixa | Retry exponencial; processo single-threaded |
| Strike no canal | Média (longo prazo) | Transformação forte (vertical+legenda+intro/outro); verificar postura de canais antes de auto_publish; manter 2º canal de reserva |
| Whisper acerta mal nome próprio brasileiro | Alta | Aceita; o ganho de revisar manualmente não compensa. Citações com erro de nome são raras e perdoáveis em cortes. |
| Disco enche (vídeos brutos) | Alta | Cron diário deleta `data/video/{id}.mp4` de vídeos com `status='uploaded_youtube'` há mais de 7 dias. Audio fica (é pequeno). |

## Qualidade e testes (Onda 8+)

### Backend — pytest (654 testes, cobertura 93.71% nos pacotes críticos)

Estrutura de testes em `tests/`:

```
tests/
├── api/
│   ├── conftest.py         ← fixtures: client (TestClient), mock_service (MagicMock + EventBus real),
│   │                          conn (SQLite :memory:), auth_headers
│   ├── test_auth.py, test_canais.py, test_clips.py, test_config.py
│   ├── test_events.py      ← SSEBridge unit (async pytest.mark.anyio) + endpoint direto
│   ├── test_stages.py, test_videos.py
├── e2e/
│   └── test_journeys.py    ← 5 cenários httpx + TestClient real (não mock_service)
├── fakes.py                ← InMemory{Video,Clip,Canal}Repository para testes de serviço
├── test_pipeline_service.py
├── test_repositories.py    ← fixtures com _apply_migrations() (garante colunas de migrations)
└── ...
```

**Padrões importantes:**
- `monkeypatch` para `subprocess.run` global (não em módulo importador) e funções localmente importadas na fonte
- `conftest.py` em `tests/api/` fornece `mock_service` com `svc.event_bus = EventBus()` real
- Fixtures de DB aplicam `schema.sql` + `migrations/*.sql` via `_apply_migrations()` para evitar `no such column`
- `httpx.ASGITransport` não suporta streaming infinito → testar endpoint SSE chamando `stream_events()` diretamente
- `GoogleApiClient.build()` é importado localmente em `add_video_by_id()` → patch em `googleapiclient.discovery.build`, não no módulo do serviço

**Gate de cobertura:**
```bash
.venv/bin/pytest \
  --cov=canal_soberania.api --cov=canal_soberania.transcribers \
  --cov=canal_soberania.llm_backends --cov=canal_soberania.alerts \
  --cov=canal_soberania.health \
  --cov=canal_soberania.services.pipeline_service \
  --cov=canal_soberania.repositories.sqlite \
  --cov-fail-under=90 --cov-report=term-missing
```

### Frontend — Vitest + @testing-library/react (40 testes)

Stack: **Vitest 4** + **@testing-library/react** + **jsdom** + `@testing-library/jest-dom`

Config principal: `ui/vitest.config.ts` — environment jsdom, setupFiles `src/test/setup.ts`, coverage v8 thresholds 80%.

```bash
export PATH="$HOME/.local/node22/bin:$HOME/.local/share/pnpm/bin:$HOME/.cargo/bin:$PATH"
cd ui
pnpm test          # modo run (CI)
pnpm test:watch    # modo watch
pnpm test:cov      # com coverage report
```

**Padrões importantes:**
- `vi.resetModules()` + `vi.doMock()` (NÃO `vi.mock()` que é hoisted) para isolamento de estado ES module
- `await Promise.resolve()` após `applyEvent()` com callbacks `.then()` para flush de microtasks
- `renderHook(() => hook()) + act(() => {...})` para testar `useSyncExternalStore`
- Tauri APIs (`plugin-fs`, `api/core`) mockados globalmente em `src/test/setup.ts`

### E2E — Playwright (browser, skip sem Chromium)

Specs: `ui/e2e/journeys.spec.ts` — 3 jornadas (aprovar clipe, bulk toolbar, Ctrl+K palette).

Pré-requisito (uma vez por máquina):
```bash
sudo npx playwright install-deps chromium
npx playwright install chromium
```

Rodar: `cs serve &` + `pnpm exec playwright test`

Os specs verificam `execSync("npx playwright install --dry-run chromium")` e fazem `test.skip()` automaticamente se o browser não estiver instalado.

### Pre-commit

`.pre-commit-config.yaml` com hooks `local`:
- **`pre-commit` stage:** `ruff check --fix`, `ruff format --check`, `mypy src/`
- **`pre-push` stage:** `pytest --cov-fail-under=90` (pacotes críticos), `pnpm test`

Instalar: `pre-commit install --hook-type pre-commit --hook-type pre-push`

---

## Eval de prompts (Onda 9+)

Sistema de avaliação em `src/canal_soberania/evals/` para medir qualidade de prompts de triagem contra diferentes backends.

### Fluxo

```
evals/dataset.jsonl           ← 50 vídeos rotulados (ground truth manual)
         │
         ▼
  runner.run_eval(stage, backend, version)
         │
         ├── cria SQLite :memory: por entry
         ├── chama função de stage real (triage_video_metadata etc.)
         ├── compara TriageResult.is_relevant vs ground_truth
         └── persiste em evals/runs/{ts}_{stage}_{backend}.jsonl
                                          │
                                          ▼
                             compare.compare_runs(run1, run2)
                                          │
                                          └── report.html (SVG + divergências)
```

### CLI

```bash
# Gerar dataset a partir do banco (uma vez)
python -m canal_soberania.evals.build_dataset --db data/canal.db --limit 50 --output evals/dataset.jsonl

# Rodar eval
cs eval run --stage triage-metadata --backend anthropic --version v1
cs eval run --stage triage-metadata --backend ollama-14b --version v1

# Comparar dois runs
cs eval compare evals/runs/run1.jsonl evals/runs/run2.jsonl --output report.html

# Listar todos os runs com métricas
cs eval list
```

### Módulos

| Arquivo | Responsabilidade |
|---|---|
| `evals/models.py` | `EvalEntry`, `EvalResult`, `RunSummary` (Pydantic) |
| `evals/runner.py` | `run_eval()`, `compute_metrics()`, `load_run()` |
| `evals/compare.py` | `compare_runs()` → `report.html` standalone |
| `evals/build_dataset.py` | extrai labels de `triage_results` do banco |

### Notas de design

- `video_id` no dataset deve ter **exatamente 11 chars** (constraint do `Video` model do pipeline)
- O idempotency guard nas stage functions não dispara porque cada entry usa DB `:memory:` fresco
- Backends suportados: `anthropic`, `ollama-14b`, `ollama-32b`, `hybrid`
- Versões de prompt: `v1` → `prompts/triagem_metadata.txt`, `v2` → `prompts/triagem_metadata_v2.txt`
- `evals/runs/*.jsonl` são gitignored; `evals/dataset.jsonl` é versionado

---

## Observabilidade

- Logs em `data/logs/{stage}_{date}.log` com rotação diária (loguru)
- `cs status` mostra contagem por status (debug rápido)
- `cs status --video-id X` mostra histórico completo de um vídeo
- `cs costs` mostra gasto Anthropic agregado por dia
- Alertas (Fase 3+): se > 50 itens stuck em qualquer status, manda mensagem Telegram via bot
