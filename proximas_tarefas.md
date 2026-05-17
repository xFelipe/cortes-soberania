# Próximas Tarefas

> Regra TDAH: **uma caixinha por vez.** Não pule fases. Tarefa "doing" no máximo 1.
> Sempre que terminar, marque `[x]` e commite. Dopamina visível é dopamina conquistada.

Status global do projeto: 🟢 Código completo + resiliente a falhas de rede — aguardando setup operacional

---

## Fase 0 — Setup do ambiente (1 dia)

- [x] Instalar `uv` (https://docs.astral.sh/uv/) e Python 3.11+
- [ ] **PRÓXIMO** Instalar `ffmpeg` no sistema (`apt install ffmpeg` ou `brew install ffmpeg`)
- [x] Clonar/inicializar repo e rodar `uv sync`
- [ ] **PRÓXIMO** Criar `.env` a partir de `.env.example` e preencher:
  - [x] `ANTHROPIC_API_KEY` — testada e funcionando
  - [x] `YOUTUBE_API_KEY` — testada e funcionando
  - [x] `OPENROUTER_API_KEY` — testada e funcionando
  - [ ] `YOUTUBE_OAUTH_CLIENT_SECRETS_PATH` (para upload, OAuth 2.0 — baixar JSON no Google Cloud Console)
- [ ] **PRÓXIMO** Rodar `sqlite3 data/canal.db < schema.sql` (ou `uv run python -c "from canal_soberania.db import *; init_db(...)"`)
- [ ] **PRÓXIMO** Validar setup: `cs discover --dry-run` deve listar vídeos sem erro
- [ ] Criar conta no canal do YouTube (definir nome, foto, banner, descrição) — *ver Decisões pendentes*
- [ ] Criar conta no TikTok com mesmo nome/visual

---

## Fase 1 — MVP manual (semana 1–2)

> Objetivo: validar nicho e qualidade dos cortes antes de automatizar. Sobe 20 vídeos manualmente para o YouTube.

### Backend (essencial)
- [x] `src/canal_soberania/db.py` — connect, init_db, helpers básicos
- [x] `src/canal_soberania/models.py` — `Video`, `Clip`, `TriageResult`
- [x] `src/canal_soberania/logger.py` — setup loguru com rotação em `data/logs/`
- [x] `src/canal_soberania/config.py` — load `.env` e `config/canais.yaml`
- [x] `src/canal_soberania/llm.py` — wrapper Anthropic (direto) + OpenRouter (demais modelos); factory `get_llm_client()` roteia por prefixo
- [x] `src/canal_soberania/cli.py` — esqueleto Typer com subcomandos

### Stage 1 — discover
- [x] `stages/discover.py` — para cada canal em `canais.yaml`, busca uploads dos últimos N dias via YouTube Data API
- [x] Inserir vídeos novos em `videos` com `status='discovered'`
- [x] Teste: roda 1x, verifica banco (14 testes com YouTube API mockada)
- [x] Criar skill com técnicas de edição usadas por donos de canais de cortes para conseguir monetizar

### Stage 2 — triage_metadata
- [x] `stages/triage_metadata.py` — pega `status='discovered'`, monta payload (título + descrição + tags + top 20 comentários)
- [x] Chama Claude Haiku com `prompts/triagem_metadata.txt`
- [x] Salva resultado em `triage_results` (score 0-10 + justificativa)
- [x] Avança para `status='triage_metadata_passed'` se score >= 5, senão `triage_metadata_rejected`

### Stage 3 — triage_caption
- [x] `stages/triage_caption.py` — baixa auto-captions via yt-dlp (`--write-auto-sub`)
- [x] Se houver caption, analisa com Claude Haiku usando `prompts/triagem_caption.txt`
- [x] Avança para `status='triage_caption_passed'` ou `rejected` (sem caption → `skipped`)

### MVP manual (sem automação completa ainda)
- [ ] Rodar discover + triage_metadata + triage_caption nos 6 canais
- [ ] Inspecionar os aprovados manualmente — ajustar `criterios_relevancia.md` e o prompt até o filtro acertar 80%+
- [ ] Para 20 vídeos aprovados: baixar, abrir no CapCut, cortar 3 momentos cada, subir manualmente
- [ ] Medir: tempo médio por vídeo, taxa de aprovação no YouTube (sem strike?), CTR primeiras 48h

### Checkpoint Fase 1
- [ ] 20 vídeos no ar
- [ ] Zero strikes
- [ ] Critério de relevância está afinado (anotar falsos positivos/negativos)
- [ ] Pelo menos 3 cortes com >1k views (sinal de nicho funcionando)

---

## Fase 2 — Automação de edição (semana 3–4)

### Stage 4 — download
- [x] `stages/download.py` — yt-dlp baixa áudio (mp3) sempre, vídeo (mp4 1080p) só se aprovado em todas triagens
- [x] Salva em `data/audio/{video_id}.mp3` e `data/video/{video_id}.mp4`
- [x] Atualiza `videos.audio_path` e `videos.video_path`

### Stage 5 — transcribe
- [x] `stages/transcribe.py` — faster-whisper large-v3, PT-BR
- [x] Salva JSON com segments+timestamps em `data/transcripts/{video_id}.json`
- [x] Status → `transcribed`

### Stage 6 — triage_transcript
- [x] `stages/triage_transcript.py` — análise final do transcript completo com Claude Sonnet usando `prompts/triagem_transcript.txt`
- [x] Output: score final + lista de temas detectados
- [x] Status → `triage_transcript_passed` ou `triage_transcript_rejected`

### Stage 7 — find_clips
- [x] `stages/find_clips.py` — manda transcript + timestamps para Claude Sonnet com `prompts/identificar_cortes.txt`
- [x] Output: 3–8 candidatos com `start_s`, `end_s`, `hook`, `payoff`, `score_viral`, `tema_soberania`
- [x] Insere em `clips` com `status='identified'`

### Stage 8 — edit
- [x] `utils/ffmpeg.py` — helpers (cut, concat, crop_and_scale, add_subtitles, encode_final)
- [x] `stages/edit.py` — para cada clip:
  - [x] Cortar vídeo bruto entre `start_s` e `end_s`
  - [x] Detectar rosto principal com mediapipe, gerar crop dinâmico 9:16 (fallback: crop central)
  - [x] Gerar `.ass` com legendas palavra-por-palavra (estilo CapCut, distribuição uniforme)
  - [x] Adicionar intro 3s (logo do canal) e outro 3s (CTA inscrever) se arquivos existirem
  - [x] Render final 1080x1920 30fps H.264 + AAC
  - [x] Versão 16:9 1920x1080 (para Shorts horizontais opcionais)
- [x] Salva em `data/clips/{clip_id}_vertical.mp4` e `data/clips/{clip_id}_horizontal.mp4`
- [ ] Nota: legendas usam timestamps de segmento (distribuição uniforme). Para precisão palavra-por-palavra real, adicionar `word_timestamps=True` ao Whisper (subtarefa futura)

### Stage 9 — thumbnail
- [x] `stages/thumbnail.py` — Pillow: pega frame do `start_s + 2`, aplica template (gradiente + texto grande + logo)
- [x] Salva `data/thumbs/{clip_id}.jpg` (1280x720)

### Stage 10 — metadata
- [x] `stages/metadata.py` — Claude Sonnet com `prompts/gerar_metadata_clip.txt`
- [x] Gera: título (<60 chars, hook claro), descrição (com link do vídeo original + CTAs), 15 tags

### Hardening — resiliência de rede

> Objetivo: qualquer comando pode ser interrompido e re-executado sem duplicação, custo extra ou estado travado.

**P0 — Crítico (feito)**
- [x] `upload_youtube.py` — guard de `youtube_id` (sem upload duplicado), retry exponencial no `next_chunk()` para HTTP 5xx/socket, recovery do status `uploading_youtube`
- [x] `download.py` — yt-dlp com `retries=10`/`fragment_retries=10`, tenacity para `DownloadError`, validação de tamanho mínimo (10 KB), recovery de `"downloading"` em reruns
- [x] `llm.py` — `LLMClient` cobre `APIConnectionError` + `InternalServerError`; `OpenRouterClient` reescrito com tenacity (cobre `URLError`, timeout, 5xx, `JSONDecodeError`)

**P1 — Alto (feito)**
- [x] `triage_metadata/caption/transcript.py` — guard SQL antes do LLM: rerun não gera chamada duplicada nem gasto extra
- [x] `find_clips.py` — guard por contagem de clips existentes + recovery de `"finding_clips"`
- [x] `metadata.py` — pula LLM se título e descrição já preenchidos

**P2 — Médio (feito)**
- [x] `transcribe.py` — write atômico via `tempfile` + `os.replace` (sem JSON corrompido em crash)
- [x] `triage_caption.py` — retries no yt-dlp de captions + validação de VTT não-vazio
- [x] `edit.py` — recovery de status `"editing"` em reruns

**P3 — Baixo (feito)**
- [x] `discover.py` — `.execute(num_retries=3)` em todas as chamadas YouTube Data API
- [x] `utils/retry.py` — novo decorator `network_retry` centralizado para reuso futuro
- [x] Testes de regressão corrigidos (datas hardcoded, status `transcribe_error`, tamanho de arquivo mock)

### Checkpoint Fase 2
- [x] Pipeline `discover → ... → edit → thumbnail → metadata` rodando ponta a ponta (código completo, 159 testes)
- [x] Pipeline resiliente a falhas de rede: retry, idempotência e recovery de orphans em todos os stages
- [ ] 10 clipes gerados automaticamente e revisados manualmente para qualidade
- [ ] Tempo total por vídeo de 1h: < 15 min de wall-clock (Whisper é o gargalo)

---

## Fase 3 — Upload e cron (semana 5–6)

### Stage 11 — upload_youtube
- [x] `stages/upload_youtube.py` — OAuth flow no primeiro uso, depois token salvo
- [x] Upload com `privacyStatus='private'` e `publishAt` agendado
- [x] Política de agendamento: máx 3 uploads/dia, espaçados em horários 9h / 14h / 19h
- [x] Atualiza `clips.youtube_id` e `clips.status='scheduled_youtube'`

### Stage 12 — upload_tiktok (fila manual primeiro)
- [x] `stages/upload_tiktok.py` — copia `.mp4` para `data/clips/pending_tiktok/` com nome legível + arquivo `.txt` ao lado contendo título/descrição
- [x] Notifica via log: "X vídeos prontos para TikTok"
- [x] Status → `pending_tiktok_manual`

### Cron e operação
- [x] `scripts/run_discover.sh` — chama `cs discover && cs triage --stage metadata && cs triage --stage caption`
- [x] `scripts/run_pipeline.sh` — full pipeline discover → upload; usa flock para evitar paralelas
- [x] `scripts/backup_db.sh` — sqlite3 .backup + purge > 30 dias
- [ ] **PRÓXIMO (após Fase 1)** Configurar crontab na VPS:
  ```
  0 8,20 * * *  /path/scripts/run_discover.sh
  */30 * * * *  /path/scripts/run_pipeline.sh
  0 3 * * *     /path/scripts/backup_db.sh
  ```
- [x] Configurar alertas: `cs alert --threshold 50` + `scripts/check_stuck.sh` — Telegram se configurado

### Checkpoint Fase 3
- [ ] 5 dias consecutivos de operação automática sem intervenção
- [ ] 3 vídeos/dia subindo no YouTube
- [ ] Backlog TikTok < 10 vídeos (você consegue subir manualmente em < 10 min/dia)

---

## Fase 4 — Arquitetura Desktop & Frontend PySide6

> Objetivo: transformar o pipeline CLI num OpusClip simplificado com UI desktop. Refatorar o core antes de construir qualquer tela.

### 4.1 — Service Layer
- [x] Criar `src/canal_soberania/services/pipeline_service.py` — classe `PipelineService` com métodos públicos que a UI vai chamar (`get_videos`, `get_clips`, `get_video`, `get_status_summary`, `get_monthly_cost`, `run_*`)
- [x] CLI (`cli.py`) passa a chamar `PipelineService` em vez de `stages/` diretamente
- [x] Testes unitários em `tests/test_pipeline_service.py` (22 testes — queries + delegation mocks)

### 4.2 — Repository
- [x] Definir protocolos (interfaces) em `core/repositories.py`: `VideoRepository`, `ClipRepository`
- [x] Implementar `SqliteVideoRepository` e `SqliteClipRepository` em `repositories/sqlite.py`
- [x] `PipelineService` recebe repositórios via injeção de dependência (construtor)
- [x] Criar `InMemoryVideoRepository` e `InMemoryClipRepository` em `tests/fakes.py`
- [x] Testes em `tests/test_repositories.py` (19 testes) + testes InMemory no `test_pipeline_service.py`

### 4.3 — State Machine
- [x] Criar `core/state.py` com `VideoStateMachine` e `ClipStateMachine`
- [x] Definir `VIDEO_TRANSITIONS` e `CLIP_TRANSITIONS` cobrindo todos os estados
- [x] `transition()` valida e lança `InvalidTransitionError` em transição inválida; `can_transition()` para queries
- [x] `PipelineService.transition_video/clip()` expõe as máquinas para a UI
- [x] Testes em `tests/test_state.py` (22 testes — válidas, inválidas, cobertura de todos os estados)

### 4.4 — Observer / Event Bus
- [x] Criar `core/events.py` — `EventBus` (subscribe/unsubscribe/publish/wildcard) + `PipelineEvent`
- [x] `PipelineService` publica `stage_started`, `stage_completed`, `stage_error` em cada `run_*`
- [x] Recebe `EventBus` por DI; `event_bus` property exposto para a UI conectar handlers
- [x] Testes em `tests/test_events.py` (13 testes — bus isolado + integração com PipelineService)
- [ ] Adaptar para PySide6: bridge `EventBus → Qt Signal` em `gui/bridge.py` *(na Fase 4.8)*

### 4.5 — Command (stages cancellável e retriável)
- [x] Definir protocolo `Stage` em `core/stage.py`: `execute(ctx)`, `can_retry(error)`, `rollback(ctx)` + `JobContext`, `StageResult`
- [x] Wrappers em `stages/wrappers.py` adaptam os stages existentes ao protocolo sem modificar módulos originais
- [x] `PipelineService._run_stage()` usa Stage protocol: respeita `can_retry`, chama `rollback` em falha não-retriável
- [x] `cancel()` / `reset_cancel()` / `is_cancelled` no PipelineService — estágio é pulado se sinalizado
- [x] Testes em `tests/test_stage.py` (14 testes — protocol, execute, retry, cancel, registry)

### 4.6 — Strategy (pontos variáveis)
- [x] Definir protocolos em `core/strategies.py`: `ReframeStrategy`, `TranscriptionBackend`, `UploadAdapter` + `CropParams`, `TranscriptionSegment`
- [x] Implementar `CenterCropReframe`, `FaceDetectionReframe` em `strategies/reframe.py`
- [x] Implementar `FasterWhisperBackend` em `strategies/transcription.py`
- [x] Implementar `ManualQueueAdapter`, `YouTubeUploadAdapter` em `strategies/upload.py`
- [x] Testes em `tests/test_strategies.py` (14 testes — protocol compliance + comportamento)

### 4.7 — Cobertura de testes ≥ 75% ✅
- [x] Configurar `pytest-cov` no `pyproject.toml` com threshold de 75% (`fail_under = 75` em `[tool.coverage.report]`)
- [x] Adicionar testes unitários do `PipelineService` usando `InMemoryVideoRepository`
- [x] Adicionar testes da `StateMachine` (transições válidas e inválidas)
- [x] Adicionar testes do `EventBus` (subscribe + publish)
- [x] 316 testes passando, cobertura 75.03% (2523 linhas, 630 descobertas)
- [x] `schema.sql` atualizado com tabela `training_examples` (era usada em `db.py` mas faltava no schema)

### 4.8 — Frontend PySide6
- [ ] Criar `src/canal_soberania/gui/` com estrutura básica: `main.py`, `windows/`, `widgets/`, `bridge.py`
- [ ] Tela principal: lista de vídeos com status + ações (rodar stage, ver detalhes)
- [ ] Tela de review de clipes: player de preview + botões Aprovar / Rejeitar / Editar trim
- [ ] Tela de status do pipeline em tempo real (via `EventBus → Qt Signal`)
- [ ] Empacotamento: launcher script `run_gui.sh` + documentar dependências Qt no `pyproject.toml`

### Checkpoint Fase 4
- [ ] `PipelineService` existe e CLI + GUI o usam (zero lógica de negócio fora do core)
- [ ] State machine valida toda transição de status
- [ ] Cobertura ≥ 75% passando no CI
- [ ] GUI abre, lista vídeos, permite review de clipes e dispara pipeline com feedback em tempo real

---

## Fase 5 — Escala e segundo canal (mês 2+)

- [ ] Aplicar para YouTube Partner Program quando atingir tier inicial (500 inscritos + 3M views/90d *ou* 3.000h watch time/ano)
- [ ] Iterar prompts baseado em performance (clipes com >10k views: o que eles têm em comum?)
- [ ] Considerar segundo canal (mesmo tema, ângulo diferente; ex: focado em geopolítica vs. focado em economia)
- [ ] Avaliar TikTok Content Posting API quando tiver tração
- [ ] Considerar diversificação: monetização via afiliados (livros sobre os temas), curso, comunidade paga

---

## Backlog (sem prazo)

- [x] Pesquisa: estratégias de ganchos (hooks) eficazes em vídeos curtos — o que prende nos primeiros 3s, padrões de abertura viral, referências de canais de cortes BR bem-sucedidos → ver `docs/hooks_videos_curtos.md`
- [ ] Dashboard simples (Streamlit) para métricas por canal/clip
- [ ] A/B test de thumbnails (2 variantes, pick winner pelo CTR)
- [ ] Detecção automática de "trecho viral" via análise de prosódia (energia da voz, picos)
- [ ] Remix automático: pegar 3 clipes curtos do mesmo tema e juntar em um Short de 60s
- [ ] Tradução automática para outras línguas (mercado lusófono em Portugal, depois ES)
- [ ] **Emoji contextual acima das legendas** (estilo OpusClip) — detalhes abaixo

### Emoji contextual acima das legendas

> Referência: OpusClip exibe um emoji relevante ao tema acima do bloco de legenda, trocando conforme o assunto muda.

**Onde fica:** `stages/edit.py` — `generate_ass()` + `edit_clip()` + campo novo em `find_clips`/`metadata`.

**Abordagem técnica (ASS):**
- Adicionar segundo `Style` no header ASS: `EmojiStyle,Segoe UI Emoji,{emoji_size},&H00FFFFFF,...,Alignment=8` (Alignment 8 = topo centralizado)
- Cada grupo de legendas recebe um evento `EmojiStyle` sincronizado com o início do chunk
- O emoji fica numa linha independente — não afeta o layout das legendas
- `MarginV` do emoji: ~200px do topo (PlayRes 1920px)

**Como escolher o emoji:**
- `find_clips.py`: LLM já analisa o trecho — adicionar campo `"emoji": "<emoji>"` no JSON de saída (1–2 emojis, ex: `"🛢️🇧🇷"` para Petrobras)
- O emoji fica gravado na tabela `clips.emoji` (nova coluna, nullable)
- `edit_clip()` recebe `emoji: str | None`; se `None`, não gera o estilo

**Flag opcional:** parâmetro `show_emoji: bool = True` em `edit_clip()` para desligar por canal (canais mais sóbrios).

**Schema:** `ALTER TABLE clips ADD COLUMN emoji TEXT;` → criar `migrations/003_clips_emoji.sql`

**Dependências:**
1. Fonte com suporte a emoji disponível no sistema (testar `Noto Color Emoji` ou `Segoe UI Emoji` com ffmpeg `subtitles` filter — pode precisar de fallback para `drawtext`)
2. Prompt `identificar_cortes.txt` precisa incluir o campo `emoji` no JSON de saída
3. Testes: mockar `edit_clip` com `emoji="🛢️"` e verificar que o ASS gerado contém `EmojiStyle`

**Prioridade:** baixa — só faz diferença visual após o canal ter 50+ cortes publicados e começar a testar retenção.

---

## Decisões pendentes (decidir antes de começar fase correspondente)

- [ ] **Nome do canal** (sugestões: "Brasil Soberano", "Quinto Império Cortes", "Visão Soberana", "Pátria em Cortes") — _decidir antes da Fase 1 publicar_
- [ ] **Identidade visual** (cor primária, fonte, logo simples 1024x1024) — _antes da Fase 2_
- [ ] **Intro/outro** (3s cada, com logo + sting de áudio livre) — _antes da Fase 2_
- [ ] **Comprar domínio?** (Ex: `brasilsoberano.com.br` para link na bio) — _antes da Fase 3_
