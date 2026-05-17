# Canal Soberania

Pipeline automatizado de cortes de vídeo focado em soberania nacional do Brasil. Monitora canais brasileiros, identifica trechos relevantes ao tema, recorta para YouTube Shorts e TikTok, e publica automaticamente.

---

## Índice

1. [Pré-requisitos de sistema](#1-pré-requisitos-de-sistema)
2. [Instalação do projeto](#2-instalação-do-projeto)
3. [Banco de dados](#3-banco-de-dados)
4. [Variáveis de ambiente (.env)](#4-variáveis-de-ambiente-env)
5. [Credenciais do Google Cloud (YouTube)](#5-credenciais-do-google-cloud-youtube)
6. [Identidade visual (logo, intro, outro)](#6-identidade-visual-logo-intro-outro)
7. [Validação do setup](#7-validação-do-setup)
8. [Rodar o pipeline manualmente](#8-rodar-o-pipeline-manualmente)
9. [Interface gráfica (GUI)](#9-interface-gráfica-gui)
10. [Automação com cron](#10-automação-com-cron)
11. [Alertas via Telegram (opcional)](#11-alertas-via-telegram-opcional)
12. [Estrutura de arquivos gerados](#12-estrutura-de-arquivos-gerados)
13. [Documentação complementar](#13-documentação-complementar)

---

## 1. Pré-requisitos de sistema

| Dependência | Versão mínima | Como instalar |
|---|---|---|
| Python | 3.11+ | `apt install python3.11` ou `pyenv install 3.11` |
| uv | qualquer | `curl -Lsf https://astral.sh/uv/install.sh \| sh` |
| ffmpeg | 4.x+ | `apt install ffmpeg` ou `brew install ffmpeg` |
| sqlite3 | 3.35+ | Já incluído no Python / `apt install sqlite3` |

Verifique:

```bash
python3 --version   # >= 3.11
uv --version
ffmpeg -version
sqlite3 --version
```

**GPU (opcional):** Se tiver NVIDIA, instale `cuda` e configure `WHISPER_DEVICE=cuda` e `WHISPER_COMPUTE_TYPE=float16` no `.env`. Sem GPU, o pipeline roda em CPU com `int8` — mais lento, mas funciona.

---

## 2. Instalação do projeto

```bash
# Clone e entre no diretório
git clone <url-do-repo> canal-soberania
cd canal-soberania

# Instala dependências de produção
uv sync

# Instala dependências de desenvolvimento (pytest, ruff, mypy)
uv sync --extra dev

# Instala dependências da interface gráfica (PySide6)
uv sync --extra gui
```

---

## 3. Banco de dados

Rode o schema uma única vez para criar as tabelas:

```bash
sqlite3 data/canal.db < schema.sql
```

Verificação:

```bash
sqlite3 data/canal.db ".tables"
# Deve listar: api_costs  clips  triage_results  uploads_log  videos
```

> O banco usa WAL mode — o `backup_db.sh` faz backup seguro mesmo com o pipeline rodando.

---

## 4. Variáveis de ambiente (.env)

Copie o exemplo e preencha:

```bash
cp .env.example .env
```

Abra `.env` e configure cada seção:

### 4.1 Anthropic Claude API (obrigatório)

Acesse **https://console.anthropic.com/settings/keys**, crie uma API key e coloque:

```env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Os modelos já têm default correto (`claude-haiku-4-5-20251001` para triagem, `claude-sonnet-4-6` para análise profunda) — não precisa mexer a não ser para trocar.

### 4.2 YouTube Data API v3 (obrigatório para discover)

Essa key é usada **somente para leitura** (descobrir vídeos, buscar comentários).

1. Acesse **https://console.cloud.google.com**
2. Crie um projeto (ex: `canal-soberania`)
3. Vá em **APIs & Services → Enable APIs** e ative **YouTube Data API v3**
4. Vá em **APIs & Services → Credentials → Create Credentials → API Key**
5. Copie a key gerada

```env
YOUTUBE_API_KEY=AIzaSy...
```

> Cota gratuita: 10.000 unidades/dia. O pipeline consome ~50–200 unidades por execução de discover.

### 4.3 YouTube OAuth 2.0 (obrigatório para upload)

Essa credencial permite que o pipeline faça upload na **sua conta do canal**.

1. No mesmo projeto do Google Cloud, vá em **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. Application type: **Desktop app**
3. Clique em **Download JSON** e salve o arquivo — esse é o `client_secrets.json`
4. Vá em **OAuth consent screen** e adicione seu e-mail como **Test user** (enquanto o app estiver em modo de teste)

```env
YOUTUBE_OAUTH_CLIENT_SECRETS_PATH=/caminho/absoluto/para/client_secrets.json
YOUTUBE_OAUTH_TOKEN_PATH=/caminho/absoluto/para/youtube_token.json
```

O `youtube_token.json` **não precisa existir ainda** — na primeira vez que você rodar `cs upload --platform youtube`, o browser abre automaticamente para autorizar. O token é salvo e reutilizado.

### 4.4 Whisper

```env
WHISPER_MODEL=large-v3        # large-v3 = melhor qualidade PT-BR
WHISPER_DEVICE=cpu            # cpu ou cuda
WHISPER_COMPUTE_TYPE=int8     # cpu: int8; cuda: float16
```

Na primeira execução do `cs transcribe`, o modelo é baixado automaticamente (~1.5 GB para `large-v3`).

### 4.5 Telegram alerts (opcional)

Só necessário se quiser receber alertas quando o pipeline travar.

1. Crie um bot no Telegram: fale com `@BotFather`, use `/newbot`, copie o token
2. Descubra seu `chat_id`: fale com `@userinfobot` ou inspecione `https://api.telegram.org/bot<TOKEN>/getUpdates` após enviar uma mensagem para o bot

```env
TELEGRAM_BOT_TOKEN=123456789:AAF...
TELEGRAM_CHAT_ID=987654321
```

### 4.6 Comportamento geral

```env
DATA_DIR=./data      # onde ficam banco, áudios, vídeos, thumbnails
LOG_LEVEL=INFO       # DEBUG | INFO | WARNING | ERROR
DRY_RUN=false        # true = não faz download, upload nem side effects
```

---

## 5. Credenciais do Google Cloud (YouTube)

Resumo visual do fluxo de criação:

```
console.cloud.google.com
└── Projeto "canal-soberania"
    ├── APIs & Services
    │   ├── Enable API: YouTube Data API v3         ← para discover/read
    │   └── Credentials
    │       ├── API Key                              ← YOUTUBE_API_KEY
    │       └── OAuth 2.0 Desktop App               ← client_secrets.json
    └── OAuth consent screen
        └── Test users: seu-email@gmail.com          ← sem isso o login falha
```

**Importante:** enquanto o OAuth app estiver em modo "Testing" (não publicado), apenas os e-mails em "Test users" conseguem autorizar. Adicione o e-mail da conta do canal.

---

## 6. Identidade visual (logo, intro, outro)

Esses arquivos são **opcionais** mas melhoram muito a qualidade dos vídeos:

| Arquivo | Onde colocar | Formato | Uso |
|---|---|---|---|
| Logo | `data/logo.png` | PNG com transparência (RGBA), qualquer tamanho | Aparece no canto superior esquerdo do thumbnail |
| Intro | `data/intro.mp4` | MP4, 1080×1920 (9:16), ~3s | Adicionado no início de cada clipe |
| Outro | `data/outro.mp4` | MP4, 1080×1920 (9:16), ~3s | Adicionado no final de cada clipe com CTA |

Se os arquivos não existirem, o pipeline continua normalmente (thumbnail sem logo, clipes sem intro/outro).

---

## 7. Validação do setup

Rode cada comando e confirme que não há erros:

```bash
# 1. Verifica que o banco foi criado
cs status
# Esperado: "Banco vazio — rode `cs discover` primeiro."

# 2. Verifica conexão com YouTube API (não gasta cota real)
cs discover --dry-run
# Esperado: logs de "dry-run" sem erros de autenticação

# 3. Verifica que o ffmpeg está no PATH
ffmpeg -version

# 4. Roda todos os testes unitários
uv run pytest
# Esperado: 316 passed
```

---

## 8. Rodar o pipeline manualmente

Cada comando processa todos os itens no status correto:

```bash
cs discover                        # busca vídeos novos nos 6 canais
cs triage --stage metadata         # filtra por título/desc/comentários (Claude Haiku)
cs triage --stage caption          # filtra por legenda automática (Claude Haiku)
cs download --pending              # baixa áudio (sempre) + vídeo (se aprovado)
cs transcribe --pending            # transcreve com faster-whisper PT-BR
cs triage --stage transcript       # filtra por transcrição completa (Claude Sonnet)
cs find-clips --pending            # identifica 3–8 cortes por vídeo (Claude Sonnet)
cs edit --pending                  # corta, recadra 9:16, adiciona legendas e intro/outro
cs thumbnail --pending             # gera thumbnail 1280×720 com frame + texto
cs metadata --pending              # gera título/descrição/tags (Claude Sonnet)
cs upload --platform youtube       # upload privado agendado (OAuth)
cs upload --platform tiktok        # copia para data/clips/pending_tiktok/ (manual)

cs status                          # mostra contagem por status e custo do mês
cs alert --threshold 50            # verifica se algum status tem > 50 itens presos
```

Use `--dry-run` em qualquer comando para simular sem side effects:

```bash
cs discover --dry-run
cs triage --stage metadata --dry-run
```

---

## 9. Interface gráfica (GUI)

O pipeline tem uma interface desktop opcional construída em **PySide6** — útil para review de clipes, inspecionar o estado do banco e disparar stages sem precisar lembrar de comandos.

### 9.1 Pré-requisitos adicionais (Linux)

```bash
# OpenGL, xcb e GStreamer para o player de vídeo
# (libgl1 substitui libgl1-mesa-glx a partir do Ubuntu 22.04)
sudo apt install libgl1 \
                 libxcb-cursor0 \
                 gstreamer1.0-plugins-good \
                 gstreamer1.0-plugins-bad \
                 gstreamer1.0-libav
```

No macOS e Windows o Qt usa backends nativos — não é necessário instalar GStreamer.

### 9.2 Instalar dependências Qt

```bash
uv sync --extra gui
```

### 9.3 Iniciar a GUI

```bash
# Via launcher script (recomendado — verifica dependências antes)
bash run_gui.sh

# Ou diretamente via uv
uv run cs-gui
```

A GUI lê o mesmo `.env` e `data/canal.db` do pipeline CLI — nenhuma configuração extra.

### 9.4 O que a interface oferece

| Aba | Funcionalidade |
|---|---|
| **Vídeos** | Lista todos os vídeos com código de cores por status; filtro por status; duplo-clique exibe todos os campos do vídeo |
| **Clipes** | Grade de cards com score viral, hook e duração; botão **Review** abre o diálogo de revisão |
| **Pipeline** | Botões para cada stage (Discover → Upload); log colorido em tempo real via `EventBus → Qt Signal`; botão **Cancelar** para interromper o stage em curso |

### 9.5 Diálogo de review de clipe

Aberto via o botão **Review** na aba Clipes:

- **Player integrado** — reproduz o `.mp4` vertical do clipe (requer GStreamer no Linux)
- **Informações** — score viral, relevância, tema, hook e payoff
- **Editar trim** — ajusta `start_s` / `end_s` e salva no banco (rode o stage Edit depois para re-renderizar)
- **Aprovar** — avança o clipe para o próximo status na máquina de estados
- **Rejeitar** — marca o clipe como `processing_error` com nota "Rejeitado manualmente via GUI"

### 9.6 Execução em background

A GUI não substitui o cron — ela é complementar. O cron cuida do processamento noturno automático; a GUI serve para revisão manual diária e para disparar stages pontuais sem ter que digitar na CLI.

---

## 10. Automação com cron

Primeiro autorize os scripts:

```bash
chmod +x scripts/*.sh
```

Edite o crontab (`crontab -e`) e adicione — substitua `/CAMINHO/ABSOLUTO` pelo caminho real do repo:

```cron
# Discover 2x/dia (8h e 20h)
0 8,20 * * *  /CAMINHO/ABSOLUTO/scripts/run_discover.sh

# Pipeline a cada 30 min
*/30 * * * *  /CAMINHO/ABSOLUTO/scripts/run_pipeline.sh

# Backup diário às 3h
0 3 * * *     /CAMINHO/ABSOLUTO/scripts/backup_db.sh
```

**Na primeira vez que o cron rodar `cs upload --platform youtube`**, ele vai falhar porque não há terminal para o fluxo OAuth. Faça a autorização manualmente antes:

```bash
# Autorize uma única vez (abre o browser)
cs upload --platform youtube --dry-run
# Depois rode real:
# cs upload --platform youtube
```

Depois que o `youtube_token.json` existir, o cron funciona sem interação.

Logs de cada execução ficam em `data/logs/`:

```bash
tail -f data/logs/pipeline_$(date +%F).log
```

---

## 11. Alertas via Telegram (opcional)

Com `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` configurados:

```bash
# Verifica manualmente
cs alert --threshold 50

# Verificação automática — adicione ao crontab:
# */5 * * * *  /CAMINHO/ABSOLUTO/scripts/check_stuck.sh
```

O comando retorna exit code 1 se algum status tiver mais de `threshold` itens — útil para monitoramento.

---

## 12. Estrutura de arquivos gerados

Tudo em `data/` (não versionado):

```
data/
├── canal.db                      ← banco SQLite (toda a máquina de estado)
├── audio/
│   └── {video_id}.mp3            ← áudios baixados
├── video/
│   └── {video_id}.mp4            ← vídeos baixados
├── captions/
│   └── {video_id}.pt.vtt         ← legendas automáticas do YouTube
├── transcripts/
│   └── {video_id}.json           ← transcrição Whisper com timestamps
├── clips/
│   ├── {clip_id}_vertical.mp4    ← clipe final 1080×1920 (Shorts/TikTok)
│   ├── {clip_id}_horizontal.mp4  ← clipe 1920×1080 (opcional)
│   └── pending_tiktok/
│       ├── {slug}.mp4            ← fila para upload manual no TikTok
│       └── {slug}.txt            ← título + descrição + hashtags
├── thumbs/
│   └── {clip_id}.jpg             ← thumbnail 1280×720
├── logs/
│   ├── pipeline_YYYY-MM-DD.log
│   └── discover_YYYY-MM-DD.log
└── backups/
    └── canal_YYYY-MM-DD.db       ← backups diários
```

---

## 13. Documentação complementar

| Arquivo | Conteúdo |
|---|---|
| [`CLAUDE.md`](./CLAUDE.md) | Princípios de design, stack completa, convenções de código |
| [`proximas_tarefas.md`](./proximas_tarefas.md) | Roadmap em fases com checkboxes |
| [`docs/arquitetura.md`](./docs/arquitetura.md) | Visão geral do sistema, diagrama de fluxo |
| [`docs/pipeline.md`](./docs/pipeline.md) | Cada stage explicado em detalhe |
| [`docs/prompts.md`](./docs/prompts.md) | Documentação dos prompts usados |
| [`config/criterios_relevancia.md`](./config/criterios_relevancia.md) | O que conta como tema relevante (single source of truth do filtro) |
| [`config/canais.yaml`](./config/canais.yaml) | Lista de canais monitorados e parâmetros globais |
| [`schema.sql`](./schema.sql) | Schema completo do banco SQLite |
| [`.env.example`](./.env.example) | Todas as variáveis de ambiente documentadas |
