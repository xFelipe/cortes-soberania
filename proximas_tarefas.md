# Próximas Tarefas

> Regra TDAH: **uma caixinha por vez.** Não pule fases. Tarefa "doing" no máximo 1.
> Sempre que terminar, marque `[x]` e commite. Dopamina visível é dopamina conquistada.

Status global do projeto: 🟡 Setup

---

## Fase 0 — Setup do ambiente (1 dia)

- [x] Instalar `uv` (https://docs.astral.sh/uv/) e Python 3.11+
- [ ] Instalar `ffmpeg` no sistema (`apt install ffmpeg` ou `brew install ffmpeg`)
- [x] Clonar/inicializar repo e rodar `uv sync`
- [ ] Criar `.env` a partir de `.env.example` e preencher:
  - [ ] `ANTHROPIC_API_KEY` (https://console.anthropic.com)
  - [ ] `YOUTUBE_API_KEY` (Google Cloud Console → YouTube Data API v3, criar key)
  - [ ] `YOUTUBE_OAUTH_CLIENT_SECRETS_PATH` (para upload, OAuth 2.0, baixar JSON)
- [ ] Rodar `sqlite3 data/canal.db < schema.sql`
- [ ] Validar setup: `cs discover --dry-run` deve listar vídeos sem erro
- [ ] Criar conta no canal do YouTube (definir nome, foto, banner, descrição)
- [ ] Criar conta no TikTok com mesmo nome/visual

---

## Fase 1 — MVP manual (semana 1–2)

> Objetivo: validar nicho e qualidade dos cortes antes de automatizar. Sobe 20 vídeos manualmente para o YouTube.

### Backend (essencial)
- [x] `src/canal_soberania/db.py` — connect, init_db, helpers básicos
- [x] `src/canal_soberania/models.py` — `Video`, `Clip`, `TriageResult`
- [x] `src/canal_soberania/logger.py` — setup loguru com rotação em `data/logs/`
- [x] `src/canal_soberania/config.py` — load `.env` e `config/canais.yaml`
- [x] `src/canal_soberania/llm.py` — wrapper Anthropic, suporte Haiku e Sonnet
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

### Checkpoint Fase 2
- [x] Pipeline `discover → ... → edit → thumbnail → metadata` rodando ponta a ponta (código completo, 159 testes)
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
- [ ] Crontab:
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

## Fase 4 — Escala e segundo canal (mês 2+)

- [ ] Aplicar para YouTube Partner Program quando atingir tier inicial (500 inscritos + 3M views/90d *ou* 3.000h watch time/ano)
- [ ] Iterar prompts baseado em performance (clipes com >10k views: o que eles têm em comum?)
- [ ] Considerar segundo canal (mesmo tema, ângulo diferente; ex: focado em geopolítica vs. focado em economia)
- [ ] Avaliar TikTok Content Posting API quando tiver tração
- [ ] Considerar diversificação: monetização via afiliados (livros sobre os temas), curso, comunidade paga

---

## Backlog (sem prazo)

- [ ] Dashboard simples (Streamlit) para métricas por canal/clip
- [ ] A/B test de thumbnails (2 variantes, pick winner pelo CTR)
- [ ] Detecção automática de "trecho viral" via análise de prosódia (energia da voz, picos)
- [ ] Remix automático: pegar 3 clipes curtos do mesmo tema e juntar em um Short de 60s
- [ ] Tradução automática para outras línguas (mercado lusófono em Portugal, depois ES)

---

## Decisões pendentes (decidir antes de começar fase correspondente)

- [ ] **Nome do canal** (sugestões: "Brasil Soberano", "Quinto Império Cortes", "Visão Soberana", "Pátria em Cortes") — _decidir antes da Fase 1 publicar_
- [ ] **Identidade visual** (cor primária, fonte, logo simples 1024x1024) — _antes da Fase 2_
- [ ] **Intro/outro** (3s cada, com logo + sting de áudio livre) — _antes da Fase 2_
- [ ] **Comprar domínio?** (Ex: `brasilsoberano.com.br` para link na bio) — _antes da Fase 3_
