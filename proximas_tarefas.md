# Próximas Tarefas

> Regra TDAH: **uma caixinha por vez.** Não pule ondas. Cada onda termina com commit + `git tag onda-N-done` + smoke de 5 min.
> Rollback sempre disponível: `git reset --hard onda-{N-1}-done`

**Stack decidida:** Tauri + React + shadcn/ui + TanStack + FastAPI + Ollama (full-local AI)
**Referência completa:** ver plano em `/home/felipe/.claude/plans/me-ajude-a-pensar-serene-sunset.md`

---

## Status geral

| Fase | Ondas | Status |
|---|---|---|
| **A — MVP completo e bonito** | 0–5 | 🟡 Em andamento (Ondas 0–1 ✅) |
| **B — Robustez + features power** | 6–9 | ⬜ Aguardando Fase A |
| **C — Extras** | 10–12 | ⬜ Aguardando Fase B |

---

## FASE A — MVP completo e bonito (~25 dias)

### ✅ Onda 0 — Mitigação de risco (`git tag onda-0-done`)

- [x] `git tag pre-refactor` — ponto de rollback antes de qualquer mudança
- [x] Pacote `alerts/`: `TelegramChannel`, `SmtpChannel`, `AlertRouter` plugável via `ALERT_CHANNELS`
- [x] `health/check.py` — verifica DB, disco livre, itens presos, heartbeat do loop
- [x] `scripts/healthcheck.sh` — cron 15min com `cs health-check --notify`
- [x] `scripts/restart_pipeline.sh` — detecta loop parado >2h e reinicia automaticamente
- [x] Comandos CLI `cs health-check` e `cs alert-test`
- [x] `pipeline-loop` escreve `data/.pipeline_heartbeat` a cada iteração
- [x] `Settings`: campos `LLM_BACKEND`, `WHISPER_BACKEND`, SMTP, `ALERT_CHANNELS` (base para Onda 1)
- [x] `.env.example` atualizado com todas as novas variáveis documentadas
- [x] 25 novos testes (suite total: 415 passando, 0 falhas)
- [x] `mypy --strict` zero erros nos novos módulos
- **Smoke OK:** `cs health-check` retorna `[OK] Disco livre: 184.4 GB`

---

### ✅ Onda 1 — Infra de execução plugável (`git tag onda-1-done`)

> Objetivo: substituir Haiku por Qwen 14B local na triagem, manter Sonnet nas análises pesadas.

- [x] `transcribers/base.py` — protocolo `Transcriber` com `transcribe(audio_path) → list[Segment]`
- [x] `transcribers/faster_whisper_local.py` — CUDA (local_cuda) e CPU (local_cpu)
- [x] `transcribers/groq_whisper.py` — opt-in nuvem grátis (escape hatch)
- [x] `transcribers/openai_whisper.py` — opt-in nuvem pago
- [x] `stages/transcribe.py` refatorado para usar `Transcriber` plugável via `get_transcriber()`
- [x] `llm_backends/base.py` — protocolo `LLMBackend` com `complete(prompt, model, ...) → LLMResponse`
- [x] `llm_backends/anthropic.py` — wraps `LLMClient` + `OpenRouterClient` existentes
- [x] `llm_backends/ollama.py` — Ollama OpenAI-compatible API (Qwen 2.5 14B/32B Q4)
- [x] `llm_backends/hybrid.py` — Ollama para triage_metadata/triage_caption; Anthropic para stages pesados
- [x] Factory `get_llm_backend(settings)` roteada por `LLM_BACKEND` env var
- [x] 5 stages refatorados (`triage_metadata`, `triage_caption`, `triage_transcript`, `find_clips`, `metadata`) usam `LLMBackend` por DI
- [x] `config.py`: `OLLAMA_BASE_URL`, `OLLAMA_MODEL_TRIAGE`, `OLLAMA_MODEL_DEEP`, `GROQ_API_KEY`, `OPENAI_API_KEY`
- [x] `.env.example` atualizado com instruções de instalação Ollama
- [x] 26 novos testes (suite total: 441 passando, 0 falhas)
- [x] `mypy --strict` zero erros nos novos módulos (17 arquivos verificados)
- **Pendente operacional (quando GPU disponível):**
  - [ ] Instalar Ollama e baixar `qwen2.5:14b-instruct-q4_K_M` (~9 GB)
  - [ ] Verificar VRAM com `nvidia-smi` (Qwen 14B ~5GB + Whisper large-v3 ~3GB = 8GB OK)
  - [ ] Validar qualidade: precision/recall Qwen 14B vs Haiku (promover só se diferença < 10%)

---

### ⬜ Onda 2 — API REST FastAPI (4 dias)

> Objetivo: expor o PipelineService via HTTP+SSE para o frontend Tauri consumir.

#### Endpoints principais
- [ ] `api/main.py` — app FastAPI com CORS e auth por token local
- [ ] `GET /videos` + `POST /videos` (adicionar por ID)
- [ ] `GET /clips` + `GET /clips/{id}` + `GET /clips/{id}/face-crop`
- [ ] `POST /clips/{id}/approve` | `reject` | `trim` | `discard`
- [ ] `GET /canais` + `POST /canais` + `PUT /canais/{id}` + `DELETE /canais/{id}`
- [ ] `POST /stages/{name}/run` + `POST /pipeline/cancel` + `POST /pipeline/pause`
- [ ] `GET /stats/summary` + `GET /stats/cost` + `GET /stats/throughput`
- [ ] `GET /inbox` — lista priorizada: METADATA_READY → erros → triagem pendente → agendados 24h
- [ ] `GET /events` — SSE stream do EventBus

#### Auth
- [ ] Token local gerado em `~/.config/canal-soberania/token` na primeira execução
- [ ] Middleware valida `Authorization: Bearer <token>` em todos os endpoints

#### CLI
- [ ] `cs serve` — levanta FastAPI em `:8000` (+ flag `--with-tauri` futura)
- [ ] `GET /openapi.json` disponível para geração de cliente TypeScript

#### Testes
- [ ] `tests/api/test_videos.py`, `test_clips.py`, `test_stages.py`, `test_sse.py`
- [ ] Todos com `httpx.AsyncClient` contra app real em memória

- **Smoke:** `cs serve` → `curl http://localhost:8000/videos` retorna JSON; `curl -N http://localhost:8000/events` recebe stream SSE ao rodar um stage

---

### ⬜ Onda 3 — Tauri + React fundação (5 dias)

> Objetivo: shell desktop funcionando com layout completo e remove PySide6.

#### Scaffold
- [ ] `pnpm create tauri-app ui --template react-ts` na raiz do repo
- [ ] Instalar: `tailwindcss` + `shadcn/ui` + `@tanstack/react-query` + `@tanstack/router` + `zod` + `cmdk` + `sonner`
- [ ] `src-tauri/`: comandos Tauri mínimos (open external URL, file dialog, system tray)

#### Fundação React
- [ ] `lib/api.ts` — cliente gerado de `/openapi.json` via `openapi-typescript`
- [ ] `lib/sse.ts` — hook `useSSE()` que conecta ao EventBus e invalida queries TanStack
- [ ] `lib/status-labels.ts` — `STATUS_META[status] = { label_pt, color, icon }` central
- [ ] `lib/theme.ts` — auto OS (prefers-color-scheme) + override salvo em localStorage
- [ ] `lib/shortcuts.ts` — registro global de hotkeys (Ctrl+1..6, J/K, A/R, etc.)
- [ ] `components/layout/Sidebar.tsx` — 60px, ícones + tooltip + badge de contagem
- [ ] `components/layout/StatusFooter.tsx` — 28px: stage atual · cancel · pause loop · custo mês
- [ ] `App.tsx` com router + QueryClientProvider + ThemeProvider + Toaster

#### Remoção PySide6
- [ ] Deletar `src/canal_soberania/gui/` inteira
- [ ] Remover dependências PySide6 do `pyproject.toml`

- **Smoke:** `pnpm tauri dev` abre janela; tema segue OS; troca entre 6 rotas funciona; Ctrl+K abre placeholder de palette; StatusFooter exibe custo mensal real

---

### ⬜ Onda 4 — Inbox + Biblioteca (4 dias)

> Objetivo: as duas rotas de uso diário funcionando completamente.

#### Inbox
- [ ] `routes/inbox.tsx` — query `GET /inbox`; cards shadcn com STATUS_META; J/K nav; A aprova inline; empty state com mensagem positiva
- [ ] Cards de vídeo pendente (triagem) e clipe (METADATA_READY) com ações contextuais
- [ ] Badge de contagem na sidebar atualiza via SSE

#### Biblioteca
- [ ] `routes/biblioteca.tsx` — `<Tabs>` Vídeos / Clipes
- [ ] `<DataTable>` (TanStack Table) com: busca global, chips de filtro por status, ordenação por coluna, paginação virtual
- [ ] `<Toggle>` tabela ↔ grid; grid de clipes com thumbnail + status badge
- [ ] Bulk select via checkbox na coluna 0; sticky toolbar quando ≥ 1 selecionado (approve, reject, discard)
- [ ] `<ContextMenu>` rico em cada linha (approve, reject, review, open YouTube, copy ID)

- **Smoke:** Inbox lista corretamente priorizado; J/K navega; A aprova sem recarregar; Biblioteca filtra por status; selecionar 3 → bulk toolbar aparece; grid mostra thumbnails

---

### ⬜ Onda 5 — ClipReview Tauri (5 dias)

> Objetivo: o fluxo principal de aprovação de clipe end-to-end, substituindo o PySide6 dialog.

#### Layout
- [ ] `routes/clip-review/$id.tsx` — 2 colunas: Player (esquerda) + Form+Actions (direita)
- [ ] Player HTML5 com controles padrão + overlay Canvas para máscara 9:16
- [ ] Preview do crop: `GET /clips/{id}/face-crop` retorna frame PNG; Canvas renderiza sobreposição

#### Timeline e hotkeys
- [ ] `<Slider>` shadcn customizado com marcas in/out (duplo thumb via Radix)
- [ ] Loop A↔B com debounce 200ms (igual ao PySide6 atual)
- [ ] Hotkeys: `[` in, `]` out, `Space` play/pause, `A` aprovar, `R` rejeitar — via `lib/shortcuts.ts`

#### Form e autosave
- [ ] Campos: hook (textarea), score viral (1-10), in/out timestamps, notas
- [ ] Zod schema + TanStack `useMutation` + debounce 500ms → autosave sem botão "Salvar"
- [ ] Toast de confirmação: "Salvo automaticamente"

#### Navegação e ações
- [ ] "Aprovar e próximo" → muta `POST /clips/{id}/approve` + navega para próximo da Inbox
- [ ] "Rejeitar" — inline sem confirmação
- [ ] "Deletar do YouTube" — `shadcn AlertDialog` (única ação destrutiva irreversível)
- [ ] Breadcrumb: Inbox → Clipe

- **Smoke:** abrir review; ajustar in/out; autosave funciona sem tocar em botão; aprovar navega para próximo clipe; deletar pede confirmação; player sincroniza com slider

---

## FASE B — Robustez + features power (~10 dias)

### ⬜ Onda 6 — Operação + Stats + Settings (3 dias)

- [ ] `routes/operacao/pipeline.tsx` — 12 stages em 4 grupos; contagem de pendentes por stage; log virtualizado com filtro/busca/clear
- [ ] `routes/operacao/discover.tsx` — form simplificado de discover ad-hoc; histórico de runs
- [ ] `routes/operacao/canais.tsx` — CRUD via `<Sheet>` (edição inline, sem página separada)
- [ ] `routes/stats.tsx` — 4 cards (custo+projeção, throughput, publicados, taxa aprovação) + `recharts` bar chart 4 semanas + tabela por canal
- [ ] `routes/settings.tsx` — tema, loop interval, LLM_BACKEND, WHISPER_BACKEND, destinos de alerta, cheatsheet de atalhos

---

### ⬜ Onda 7 — Command palette + bulk operations (2 dias)

- [ ] `cmdk` integrado em `Ctrl+K`; índice in-memory de vídeos, clipes, canais e ações nomeadas
- [ ] SSE atualiza índice incrementalmente (sem refetch total)
- [ ] Ações nomeadas: "Aprovar clipe X", "Ir para Stats", "Pausar pipeline loop", "Abrir Settings"
- [ ] Bulk toolbar sticky na Biblioteca com ações: approve, reject, discard, export list

---

### ⬜ Onda 8 — Cobertura testes + E2E (3 dias)

- [ ] Backend `pytest --cov` ≥ 90% (api/, transcribers/, llm_backends/, alerts/, health/)
- [ ] Frontend Vitest + React Testing Library para components críticos; cobertura ≥ 80%
- [ ] E2E Playwright headless contra `cs serve` real:
  - [ ] Cenário 1: aprovar clipe end-to-end
  - [ ] Cenário 2: bulk approve 3 clipes
  - [ ] Cenário 3: rejeitar + restaurar via palette
- [ ] Pre-commit hook: lint + coverage gate

---

### ⬜ Onda 9 — Eval pipeline de prompts (3 dias)

- [ ] `evals/dataset.jsonl` — 50 vídeos rotulados (extraídos do banco + correção manual em sessão única)
- [ ] `evals/runner.py` — roda prompt vN contra 4 backends; mede precision/recall/cost por vídeo
- [ ] `evals/compare.py` — diff entre 2 versões; gera `report.html` com gráficos + exemplos divergentes
- [ ] `cs eval run --prompt triagem_metadata --backend ollama-14b --version v1`

---

## FASE C — Extras (~7 dias)

### ⬜ Onda 10 — Multi-canal genérico (4 dias)

- [ ] `config/canais/{slug}.yaml` — migrar de `canais.yaml` flat para um arquivo por canal
- [ ] Schema migration: `videos.target_canal_id` + `clips.target_canal_id`
- [ ] Prompts por canal: `prompts/{slug}/...`; critérios: `config/criterios_relevancia/{slug}.md`
- [ ] Branding por canal: `branding/{slug}/intro.mp4`, `outro.mp4`, `logo.png`, `thumb_template.png`
- [ ] UI: chip de canal na Biblioteca; filtro persistente

---

### ⬜ Onda 11 — TikTok Caminho 3 (2 dias) ⚠️ RISCO ALTO

> Conta dedicada de testes. Rate limit hard: 3 uploads/dia. Opt-in via `TIKTOK_BOT_ENABLED=false`.

- [ ] `stages/upload_tiktok_bot.py` usando `tiktok-uploader`
- [ ] `docker/tiktok-bot/Dockerfile` — Chrome headless + xvfb; volume `cookies/` persistente
- [ ] `docs/operacao/tiktok-bot.md` — recomendações operacionais de risco

---

### ⬜ Onda 12 — Empacotamento + auto-update (1–2 dias)

- [ ] `pnpm tauri build` → Linux `.AppImage` + `.deb`; Windows `.msi`
- [ ] `tauri-plugin-updater` apontando para GitHub Releases
- [ ] GitHub Actions release workflow (publica binários; não CI/CD de deploy)
- [ ] `docs/install.md`

---

## Smoke checklist padrão (< 5 min, rodar ao fechar cada onda)

```bash
uv run pytest --tb=no -q          # todos passando
uv run mypy src/ --strict          # zero erros
uv run cs health-check             # [OK]
git tag onda-N-done                # marcar conclusão
```

---

## Caminho crítico — métricas alvo

| Fluxo | Hoje (PySide6) | Meta (Tauri) |
|---|---|---|
| Aprovar 1 clipe METADATA_READY | ~7 cliques | ≤ 3 |
| Bulk approve 5 clipes | ~35 cliques | ~4 |
| Encontrar clipe específico | filtro + scroll | Ctrl+K + Enter |
| Pipeline travou → saber | só abrindo app | Telegram ≤ 15 min |

---

## Histórico — fases anteriores concluídas

<details>
<summary>Fases 0–4 (backend + PySide6 — concluídas)</summary>

**Fase 0 — Setup:** repo, uv, .env, schema.sql
**Fase 1 — MVP manual:** discover + triage_metadata + triage_caption
**Fase 2 — Automação:** download, transcribe, triage_transcript, find_clips, edit, thumbnail, metadata + hardening de rede
**Fase 3 — Upload e cron:** upload_youtube, upload_tiktok (fila manual), run_pipeline.sh, backup_db.sh
**Fase 4 — Service Layer + PySide6:**
- PipelineService, repositories (SQLite + InMemory), StateMachine, EventBus, Stage protocol, Strategy pattern
- GUI PySide6: MainWindow (vídeos + clipes + pipeline + discover), ClipReviewDialog (player, overlay 9:16, in/out markers, face crop, loop A↔B), VideoTable com spinner, DiscoverPanel
- 390 testes passando; cobertura ≥ 75%; mypy --strict zero erros
- `git tag gui-v1` — snapshot da GUI PySide6 antes da migração para Tauri

</details>
