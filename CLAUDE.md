# CLAUDE.md — Canal Soberania

> Este arquivo é a memória do projeto. Sempre leia antes de mexer em qualquer coisa.

## Missão

Pipeline automatizado para identificar, recortar e publicar clipes de podcasts e canais brasileiros com tema **soberania nacional**, distribuindo em **YouTube Shorts** e **TikTok**.

Operador único, TDAH friendly: cada peça é independente, com estado em SQLite, sem framework de orquestração pesado.

## Princípios de design (não negocie)

1. **KISS.** Scripts independentes orquestrados por cron. Sem Airflow, sem Prefect, sem Celery.
2. **Triagem em camadas (barato → caro).** Metadata → captions YouTube → transcrição Whisper → análise profunda. Não gasta Whisper em vídeo que claramente não é do tema.
3. **Idempotência.** Toda etapa pode rerodar. Estado vive na coluna `status` da tabela `videos`/`clips`.
4. **Fail-fast por item, resiliente no agregado.** Erro em um vídeo loga e segue. Pipeline não trava.
5. **Estado fora do código.** Tudo em `data/` (não versionado) + SQLite (`data/canal.db`).
6. **Logs sempre.** `loguru` em todo módulo. Sem `print`.
7. **Tipos sempre.** `pydantic` para modelos, `mypy --strict` para src.
8. **Determinismo onde der.** Seeds fixos, modelos versionados, prompts versionados em `prompts/`.

## Stack

| Camada | Ferramenta | Por quê |
|---|---|---|
| Download | `yt-dlp` | Padrão de fato, ativo, robusto |
| Metadados YouTube | `google-api-python-client` | Title/desc/comments/tags sem baixar |
| Transcrição | `faster-whisper` (large-v3) | 4x mais rápido, ótimo PT-BR |
| Análise/triagem | Claude API (`claude-haiku-4-5` para triagem rápida, `claude-sonnet-4-6` para análise profunda e geração de metadados) | Hierarquia de custo |
| Edição vídeo | `ffmpeg` via `subprocess` | Estável, sem MoviePy |
| Reframe vertical | `mediapipe` (face detection) | Centraliza no rosto |
| Legendas dinâmicas | `ffmpeg` + filtro `ass`/`subtitles` | Estilo CapCut palavra-por-palavra |
| Thumbnail | `Pillow` + template fixo | Sem chamadas a modelo de imagem |
| Upload YouTube | `google-api-python-client` | API oficial, cota 10k/dia |
| Upload TikTok | Ver `docs/pipeline.md` §Upload | Caminho oficial limitado, alternativas documentadas |
| Orquestração | `cron` + `typer` CLI | Zero curva de aprendizado |
| Banco | `sqlite3` stdlib | Arquivo único, backupa com `cp` |
| Config | `pyyaml` + `python-dotenv` | YAML para canais, `.env` para segredos |
| Logs | `loguru` | Rotação, níveis, sem boilerplate |
| Lint/format | `ruff` | Single tool, rápido |
| Tipo | `mypy --strict` | Pega bug antes |
| Testes | `pytest` | Padrão |

## Estrutura do repo

```
canal-soberania/
├── CLAUDE.md                    ← você está aqui
├── README.md                    ← visão geral curta
├── proximas_tarefas.md          ← roadmap com checkboxes
├── pyproject.toml
├── .env.example
├── .gitignore
├── schema.sql                   ← esquema SQLite (rodar uma vez)
│
├── config/
│   ├── canais.yaml              ← lista de canais monitorados
│   └── criterios_relevancia.md  ← o que conta como "soberania nacional"
│
├── docs/
│   ├── arquitetura.md           ← visão alto nível, diagrama
│   ├── pipeline.md              ← cada etapa explicada
│   └── prompts.md               ← documentação dos prompts usados
│
├── prompts/                     ← prompts versionados (texto puro)
│   ├── triagem_metadata.txt
│   ├── triagem_transcript.txt
│   ├── identificar_cortes.txt
│   └── gerar_metadata_clip.txt
│
├── src/canal_soberania/
│   ├── __init__.py
│   ├── cli.py                   ← typer entry point
│   ├── db.py                    ← conexão SQLite, migrations
│   ├── models.py                ← pydantic
│   ├── config.py                ← carrega canais.yaml e .env
│   ├── logger.py                ← setup loguru
│   ├── llm.py                   ← wrapper Anthropic API
│   ├── stages/
│   │   ├── discover.py          ← lista vídeos novos dos canais
│   │   ├── triage_metadata.py   ← Stage 1: title+desc+tags+comments
│   │   ├── triage_caption.py    ← Stage 2: captions YouTube
│   │   ├── download.py          ← baixa áudio (e vídeo se aprovado)
│   │   ├── transcribe.py        ← Whisper
│   │   ├── triage_transcript.py ← Stage 3: análise transcript completo
│   │   ├── find_clips.py        ← Stage 4: identifica cortes 30-90s
│   │   ├── edit.py              ← ffmpeg: corte, reframe, legenda
│   │   ├── thumbnail.py         ← Pillow
│   │   ├── metadata.py          ← Claude gera título/desc/tags
│   │   ├── upload_youtube.py
│   │   └── upload_tiktok.py
│   └── utils/
│       ├── ffmpeg.py            ← helpers ffmpeg
│       └── retry.py             ← decorator de retry
│
├── scripts/
│   ├── run_discover.sh          ← chamado pelo cron
│   ├── run_pipeline.sh          ← processa pendentes
│   └── backup_db.sh
│
├── tests/
│   └── ...                      ← pytest
│
├── data/                        ← .gitignore
│   ├── canal.db
│   ├── audio/
│   ├── video/
│   ├── transcripts/
│   ├── clips/
│   └── thumbs/
│
└── .claude/
    ├── commands/                ← slash commands customizados
    └── agents/                  ← subagents especializados
```

## Comandos comuns

```bash
# Setup inicial
uv sync                          # instala deps (use uv, não pip)
sqlite3 data/canal.db < schema.sql
cp .env.example .env             # depois preencha

# Pipeline manual (debugging)
cs discover                      # busca novos vídeos
cs triage --stage metadata       # roda triagem stage 1
cs triage --stage caption        # stage 2
cs download --pending
cs transcribe --pending
cs triage --stage transcript     # stage 3
cs find-clips --pending
cs edit --pending
cs upload --platform youtube --pending
cs upload --platform tiktok --pending

# Status
cs status                        # mostra contagem por status
cs status --video-id <id>        # detalhe de um vídeo

# Cron (produção)
scripts/run_discover.sh          # 2x/dia
scripts/run_pipeline.sh          # a cada 30min
scripts/backup_db.sh             # 1x/dia
```

`cs` é o entry point definido em `pyproject.toml` (`canal_soberania.cli:app`).

## Convenções

- **Commits:** `feat:`, `fix:`, `refactor:`, `docs:`, `chore:` (Conventional Commits).
- **Branches:** trabalho em `main` direto (operador único). Tag a cada release estável.
- **Python:** 3.11+, type hints obrigatórios em `src/`, ruff format.
- **Nomes:** snake_case Python, kebab-case arquivos shell, slugs em ASCII para arquivos de dados.
- **IDs:** sempre usar `video_id` do YouTube (11 chars) como chave. Para clipes: `{video_id}_{start_s}_{end_s}`.
- **Caminhos:** sempre absolutos relativos a `data/` via `config.DATA_DIR`. Nunca hardcode.
- **Segredos:** só em `.env`, nunca em código. `.env` no `.gitignore`.

## Notas importantes

### Direitos autorais e fair use
Canais monitorados (ver `config/canais.yaml`) variam em postura sobre cortes:
- **PodPah, Flow:** explicitamente toleram/incentivam cortes (marketing gratuito).
- **Demais (Marcílio, Arte da Guerra, Kobori, 3 Irmãos):** verificar termo em cada canal antes de subir. Em dúvida, manter `auto_publish: false` em `canais.yaml`.

Mitigação obrigatória contra "reused content":
- Reformatar para 9:16 (vertical)
- Legendas queimadas estilo dinâmico
- Intro/outro próprios (3s cada) — padrão de identidade do canal
- Título e descrição originais (não copiar do vídeo-fonte)
- Hook reescrito nos primeiros 3s (cartela ou recorte agressivo)

### Tema: soberania nacional
A definição operacional vive em `config/criterios_relevancia.md`. **Não retreine a sensibilidade de relevância sem atualizar esse arquivo.** É a single source of truth do que entra no canal.

### TikTok
A Content Posting API oficial exige aprovação. Caminho recomendado (em ordem de preferência):
1. **Conta TikTok for Business + API oficial** quando aprovado.
2. **Fila manual:** pipeline gera o `.mp4` em `data/clips/pending_tiktok/`, você sobe pelo app (5min/dia).
3. **`tiktok-uploader` (não oficial, browser automation):** frágil mas funciona; usar só em VPS dedicada.

Começar pelo (2). Não vale risco de ban de conta no início.

### Custos esperados (mensal, em produção)
- VPS Hetzner CX22: ~€5
- Claude API (Haiku triagem + Sonnet análise): ~$10–30 dependendo de volume
- Whisper local (faster-whisper CPU): R$ 0
- YouTube Data API: grátis (dentro de cota)
- Total: **< R$ 200/mês** para os 6 canais iniciais.

## Onde achar o quê

- **Por que esse design?** → `docs/arquitetura.md`
- **Como roda na prática?** → `docs/pipeline.md`
- **O que é relevância?** → `config/criterios_relevancia.md`
- **O que o Claude está sendo perguntado?** → `prompts/` + `docs/prompts.md`
- **O que falta fazer?** → `proximas_tarefas.md`
- **Tabelas e estado?** → `schema.sql`
- **API REST (todos os endpoints)?** → `docs/api.md`
- **Frontend (rotas, padrões, como estender)?** → `docs/frontend.md`

## Trabalhando com Claude Code neste projeto

- **Sempre leia este arquivo e `proximas_tarefas.md` antes de propor mudança.**
- **Uma etapa por PR mental.** Não tente fazer "tudo de uma vez". Pegue uma tarefa de `proximas_tarefas.md`, implemente, teste, marque concluída.
- **Não mude o esquema sem migration.** Se for adicionar coluna, crie `migrations/00X_descricao.sql`.
- **Não mude prompts sem versionar.** Prompts vivem em `prompts/` com nome semântico. Mudança grande → novo arquivo com sufixo `_v2.txt` e alternar via config.
- **Use os subagents.** `video-editor` para ffmpeg, `prompt-engineer` para iterar prompts. Não polua o contexto principal.
