# Próximas Tarefas

> Regra TDAH: **uma caixinha por vez.** Não pule ondas. Cada onda termina com commit + `git tag onda-N-done` + smoke de 5 min.
> Rollback sempre disponível: `git reset --hard onda-{N-1}-done`

**Stack decidida:** Tauri + React + shadcn/ui + TanStack + FastAPI + Ollama (full-local AI)
**Referência completa:** ver plano em `/home/felipe/.claude/plans/me-ajude-a-pensar-serene-sunset.md`

---

## Status geral

| Fase | Ondas | Status |
|---|---|---|
| **A — MVP completo e bonito** | 0–5 | ✅ Fase A concluída (Ondas 0–5 ✅) |
| **B — Robustez + features power** | 6–9 | 🔄 Em andamento (Ondas 6–7 ✅) |
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

### ✅ Onda 2 — API REST FastAPI (`git tag onda-2-done`)

> Objetivo: expor o PipelineService via HTTP+SSE para o frontend Tauri consumir.

- [x] `api/app.py` — `create_app()` factory com CORS (tauri://localhost + localhost:*)
- [x] `api/auth.py` — token Bearer em `DATA_DIR/.api_token` (chmod 600, `secrets.compare_digest`)
- [x] `api/sse.py` — `SSEBridge` thread-safe (EventBus sync → async via queue + `loop.call_soon_threadsafe`); heartbeat 15s
- [x] `GET /videos`, `GET /videos/{id}`, `POST /{id}/approve`, `POST /{id}/reject`
- [x] `GET /clips`, `GET /clips/{id}`, `POST /{id}/approve` (upload em thread), `POST /{id}/reject`, `POST /{id}/trim`, `PATCH /{id}`, `DELETE /{id}`
- [x] `GET /canais`, `POST /canais`, `PUT /canais/{id}`, `DELETE /canais/{id}`
- [x] `POST /stages/{name}/run` — 13 stages em daemon thread; retorna 202 imediato
- [x] `POST /pipeline/cancel`, `POST /pipeline/reset`
- [x] `GET /stats/summary`, `GET /stats/costs`, `GET /stats/costs/detail`
- [x] `GET /inbox` — lista priorizada (clips METADATA_READY prio 1, vídeos prio 2+)
- [x] `GET /events` — SSE stream com heartbeat keepalive
- [x] `GET /health`
- [x] `cs serve` — levanta FastAPI em `:8000`, imprime token Bearer no stdout
- [x] 59 novos testes `tests/api/` (500 total, todos passando)
- [x] `mypy --strict` zero erros em `src/canal_soberania/api/` (13 arquivos)
- **Referência completa:** `docs/api.md`
- **Smoke:** `cs serve` → `curl -H "Authorization: Bearer <token>" http://localhost:8000/inbox`

---

### ✅ Onda 3 — Tauri + React fundação (`git tag onda-3-done`)

> Objetivo: shell desktop funcionando com layout completo e remoção do PySide6. API (Onda 2) já estava pronta — esta onda só consome endpoints existentes.

#### Toolchain instalado (user-level)
- [x] Rust 1.95 via rustup (`~/.cargo/bin/`) — `source ~/.cargo/env` antes de usar
- [x] Node 22.16.0 manual em `~/.local/node22/` (pnpm env use falhou por timeout; tarball direto)
- [x] pnpm 11.1.3 em `~/.local/share/pnpm/bin/pnpm`
- [x] `ui/pnpm-workspace.yaml` com `allowBuilds` (pnpm 11 obriga; package.json `pnpm` field ignorado)
- **PATH necessário:** `export PATH="$HOME/.local/node22/bin:$HOME/.local/share/pnpm/bin:$HOME/.cargo/bin:$PATH"`
- **Pendente (sudo no terminal do usuário):** `sudo apt install -y libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev`

#### Scaffold `ui/`
- [x] Tauri 2 + React 19 + Vite 7 em `ui/` via `pnpm create tauri-app`
- [x] `ui/src-tauri/tauri.conf.json` — productName "Canal Soberania", 1400×900, devUrl localhost:5173
- [x] Tailwind v4 via `@tailwindcss/vite` (sem `tailwind.config.js`)
- [x] shadcn/ui v4.7 com preset Radix/Nova — `pnpm dlx shadcn@latest init -t vite -b radix -p nova`
- [x] TanStack Router + TanStack Query + cmdk + sonner + lucide-react
- [x] `@tauri-apps/plugin-fs` para leitura do token XDG

#### Biblioteca `ui/src/lib/`
- [x] `api.ts` — cliente HTTP typed; `getToken()` tenta Tauri plugin-fs, fallback localStorage; namespaces: stats, inbox, stages, videos, clips
- [x] `sse.ts` — `useSSE()` com EventSource + `?token=` query param, retry 3s, invalida TanStack Query keys
- [x] `theme.tsx` — `ThemeProvider` OS-follow + override localStorage `canal-soberania-theme`, `useTheme()`
- [x] `query.ts` — QueryClient (staleTime 5000, refetchOnWindowFocus false, retry 1)
- [x] `router.tsx` — TanStack Router com 5 rotas + redirect `/` → `/inbox`
- [x] `shortcuts.ts` — `useGlobalShortcuts(onCommandPalette)`: Ctrl+1..5 navegação, Ctrl+K palette
- [x] `status-labels.ts` — `VideoStatus` (18 values) + `ClipStatus` (14 values) + `VIDEO_STATUS_META` + `CLIP_STATUS_META` Records PT-BR + `ACTIVE_VIDEO_STATUSES`

#### Layout `ui/src/components/layout/`
- [x] `RootLayout.tsx` — grid `3.75rem + 1fr` × `1fr + 1.75rem`; monta Sidebar, main Outlet, StatusFooter
- [x] `Sidebar.tsx` — 5 nav items, Tooltip, Badge via `useQuery(['stats','summary'])`, `border-l-2 border-primary` ativo
- [x] `StatusFooter.tsx` — SSEDot (verde/amarelo/vermelho), custo via `useQuery(['stats','costs'])`, link Settings
- [x] `CommandPalette.tsx` — cmdk Dialog, placeholder "Implementado na Onda 4"

#### Rotas `ui/src/routes/`
- [x] `index.tsx` — redirect → `/inbox`
- [x] `inbox.tsx` — placeholder card "Onda 4"
- [x] `biblioteca.tsx` — placeholder card "Onda 4"
- [x] `operacao.tsx` — placeholder card "Onda 6"
- [x] `stats.tsx` — placeholder card "Onda 6"
- [x] `settings.tsx` — tema toggle funcional (Light/Dark/System) com `useTheme()`

#### Integração backend
- [x] `src/canal_soberania/api/auth.py` — dual-write token: XDG `~/.config/canal-soberania/.api_token` + `DATA_DIR/.api_token`; XDG tem prioridade
- [x] `src/canal_soberania/cli.py` — `cs serve` imprime caminho XDG do token no stdout
- [x] `tests/api/test_auth.py` — 6 testes cobrindo geração, dual-write, chmod 600, prioridade XDG, cópia data→XDG

#### Remoção PySide6
- [x] `git rm -r src/canal_soberania/gui/` (14 arquivos, 2538 linhas)
- [x] `git rm run_gui.sh`
- [x] `pyproject.toml`: removido `pyside6`, script `cs-gui`, extra `gui`, exclusão de cobertura `gui/*`
- [x] 506 testes passando; `mypy --strict` zero erros em 76 arquivos; `pnpm tsc --noEmit` zero erros TS

- **Smoke pendente (requer sudo):** `sudo apt install -y libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev` → `cs serve &` → `cd ui && pnpm tauri dev` → janela "Canal Soberania" abre

---

### ✅ Onda 4 — Inbox + Biblioteca (`git tag onda-4-done`)

> Objetivo: as duas rotas de uso diário funcionando completamente.  
> Base pronta em `ui/src/routes/inbox.tsx` e `ui/src/routes/biblioteca.tsx` (placeholders da Onda 3).  
> Todos os hooks e status labels já existem — só implementar o JSX.

#### Inbox (`ui/src/routes/inbox.tsx`)
- [x] `useQuery(['inbox'], api.inbox.get)` — cards reais de clipes e vídeos priorizados
- [x] Cards com `VIDEO_STATUS_META` / `CLIP_STATUS_META` e ações contextuais
- [x] `useInboxShortcuts` em `shortcuts.ts`; J/K nav; A aprova; R rejeita
- [x] Empty state com mensagem positiva
- [x] `useMutation` approve/reject com invalidação de queries

#### Biblioteca (`ui/src/routes/biblioteca.tsx`)
- [x] `<Tabs>` Clipes / Vídeos
- [x] `@tanstack/react-table` 8.21.3
- [x] `<DataTable>` busca global, chips de filtro por status, ordenação por coluna, paginação (50/página)
- [x] Toggle tabela ↔ grid; grid de clipes com thumbnail + status badge
- [x] Bulk select via Checkbox.Root (radix-ui); sticky toolbar approve/reject/discard
- [x] `<ContextMenu>` rico: approve, reject, abrir YouTube, copy ID, excluir

---

### ✅ Onda 5 — ClipReview Tauri (`git tag onda-5-done`)

- [x] `routes/clip-review.tsx` — 2 colunas: player (esq) + form+ações (dir)
- [x] Player HTML5 src autenticado + canvas overlay 9:16 com crop_x da face detection
- [x] `GET /clips/{id}/face-crop` (backend) — ffprobe + detect_face_crop_x
- [x] `GET /clips/{id}/source-video` (backend) — FileResponse com preferência clip vertical
- [x] Slider Radix dual-thumb in/out + scrubber de posição atual
- [x] Loop A↔B via timeupdate (salta para inPoint quando >= outPoint)
- [x] Hotkeys via `useClipReviewShortcuts`: `[` in, `]` out, `Space` play/pause, `A`, `R`
- [x] Form: hook textarea, score viral slider 1–10, in/out numérico, notas
- [x] Autosave debounce 500ms → PATCH + trim (sem botão Salvar)
- [x] "Aprovar e próximo" navega ao próximo clipe da inbox
- [x] "Rejeitar" inline; "Excluir" via AlertDialog
- [x] `score_viral` propagado por toda a cadeia (protocolo → SQLite → service → router)
- [x] 506 testes passando; mypy --strict zero erros

---

## FASE B — Robustez + features power (~10 dias)

### ✅ Onda 6 — Operação + Stats + Settings (`git tag onda-6-done`)

- [x] `routes/operacao/pipeline.tsx` — 12 stages em 4 grupos; contagem de pendentes por stage; log virtualizado com filtro/busca/clear
- [x] `routes/operacao/discover.tsx` — form simplificado de discover ad-hoc; histórico de runs (SSE)
- [x] `routes/operacao/canais.tsx` — CRUD via `<Sheet>` (edição inline, sem página separada)
- [x] `routes/stats.tsx` — 4 cards (custo+projeção, throughput, publicados, taxa aprovação) + `recharts` bar chart 4 semanas + tabela por canal
- [x] `routes/settings.tsx` — tema, loop interval, LLM_BACKEND, WHISPER_BACKEND, destinos de alerta, cheatsheet de atalhos, import .env filtrado
- [x] Backend: canais CRUD (POST/PUT/PATCH/DELETE), `POST /discover/adhoc`, `/stats/by-canal`, `/stats/throughput`, `GET/PUT /config`
- [x] `Settings.pipeline_loop_interval` + cli.py + restart_pipeline.sh atualizado
- [x] 533 testes passando; mypy --strict zero erros; pnpm tsc zero erros

---

### ✅ Onda 7 — Command palette + bulk operations (`git tag onda-7-done`)

- [x] `cmdk` integrado em `Ctrl+K`; índice in-memory de vídeos, clipes, canais e ações nomeadas (`lib/command-index.ts`)
- [x] SSE atualiza índice incrementalmente (sem refetch total) — fix do bug `event_type` vs `type`/`payload`
- [x] Ações nomeadas: "Aprovar clipe X", "Ir para Stats", "Pausar/Retomar pipeline loop", "Abrir Settings"
- [x] Bulk toolbar na Biblioteca: approve, reject, discard + "Exportar lista" (CSV→clipboard); bulk handlers Promise.allSettled (uma toast + uma invalidação)
- [x] Backend: `pause_loop()`/`resume_loop()`/`is_loop_paused()` em `PipelineService`; endpoints `POST /pipeline/{pause,resume}` + `GET /pipeline/loop-state`; `cs pipeline-loop` respeita flag
- [x] 544 testes passando; mypy --strict zero erros; pnpm tsc zero erros

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
.venv/bin/pytest --tb=no -q        # todos passando
.venv/bin/mypy src/ --strict       # zero erros
cs health-check                    # [OK]
git tag onda-N-done                # marcar conclusão
```

> **Nota:** Usar `.venv/bin/pytest` diretamente (não `uv run pytest`) — o pyenv shim pode não ativar a venv corretamente. Dev deps instaladas via `uv sync --extra dev`.

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
