# Qualidade e Melhorias — Canal Soberania

> Tarefas ordenadas por **importância × viabilidade**. Cada bloco é independente e pode ser feito em sessão separada.
> Formato: `[ ]` pendente · `[x]` feito · `[-]` descartado

---

## P0 — Análise estática (gate de CI — rodaria a cada commit)

### T0a — Habilitar regras ruff ausentes: complexidade, segurança, prints

**Por quê:** O `pyproject.toml` atual ativa `E,W,F,I,B,UP,RUF,SIM` mas deixa de fora regras de alto valor que o próprio ruff já inclui sem dependências extras:

| Conjunto | O que pega | Exemplo real no projeto |
|----------|-----------|------------------------|
| `C90` (McCabe) | Funções com complexidade ciclomática > 10 | `edit_clip()` em `stages/edit.py` tem ~15 branches |
| `S` (bandit) | Injeção de shell, `subprocess` sem lista, `assert` em produção | `stages/edit.py` usa `subprocess.run(shell=True)` em alguns helpers |
| `T20` | `print()` avulso (viola "Logs sempre" do CLAUDE.md) | Verificar se existe algum `print` esquecido |
| `PL` (pylint) | Funções com muitos argumentos (`PLR0913`), branches (`PLR0912`), statements (`PLR0915`) | `edit_clip()` tem >10 parâmetros |

**Arquivos afetados:** `pyproject.toml`

**Subtarefas:**
- [ ] Adicionar ao `[tool.ruff.lint] select`: `"C90"`, `"S"`, `"T20"`, `"PL"`
- [ ] Definir `[tool.ruff.lint.mccabe] max-complexity = 10`
- [ ] Rodar `ruff check src/` e triagear as violações:
  - [ ] **C90**: refatorar funções com complexidade > 10 (extrair submétodo ou simplificar condicionais)
  - [ ] **S**: revisar cada `subprocess` — usar lista de argumentos em vez de string quando possível; adicionar `# noqa: S603` com justificativa onde shell é intencional
  - [ ] **T20**: remover ou substituir por `logger.*` todos os `print()` encontrados
  - [ ] **PL**: funções com muitos argumentos → agrupar em dataclass/`TypedDict` onde faz sentido
- [ ] Adicionar `ruff check src/ tests/` no script de CI (ou `pre-commit`)

**Esforço estimado:** 2–3 horas

---

### T0b — Detecção de código morto com `vulture`

**Por quê:** Código não executado (funções, imports, variáveis) cresce silenciosamente sem testes e sem análise estática. `vulture` detecta símbolos definidos mas nunca referenciados — especialmente útil após refatorações (ex: migração para DAO/Service Layer da Fase 4 pode ter deixado funções órfãs).

**Arquivos afetados:** `pyproject.toml`, `src/`

**Subtarefas:**
- [ ] Adicionar `vulture>=2.11` em `[project.optional-dependencies] dev`
- [ ] Criar `vulture_whitelist.py` na raiz para declarar falsos positivos (ex: callbacks de CLI registrados via decorador, métodos de Protocol)
- [ ] Rodar `vulture src/ vulture_whitelist.py --min-confidence 80` e triar resultados:
  - [ ] Remover imports não usados que ruff não pegou
  - [ ] Remover funções/métodos públicos que nunca são chamados
  - [ ] Adicionar ao whitelist o que for intencional (ex: `rollback()` do Stage Protocol — implementado mas nem sempre chamado)
- [ ] Integrar ao CI: `vulture src/ vulture_whitelist.py --min-confidence 80`

**Esforço estimado:** 2 horas

---

### T0c — Coverage por módulo: impedir regressão em CLI e GUI

**Por quê:** O threshold global de 75% mascara que `cli.py` (0%), `gui/` (0%) e `llm.py` (50%) têm cobertura zero ou mínima. É possível quebrar a CLI inteira e o CI passa. `pytest-cov` suporta `exclude_lines` e relatório por arquivo; a configuração correta força um mínimo por módulo crítico.

**Arquivos afetados:** `pyproject.toml`

**Subtarefas:**
- [ ] Adicionar `[tool.coverage.report] show_missing = true` para ver linhas descobertas no output CI
- [ ] Após implementar T1 (testes CLI/GUI): configurar `[tool.coverage.paths]` para garantir que `cli.py` e `gui/` são incluídos no relatório (verificar se não estão em `omit`)
- [ ] Avaliar uso de `pytest-cov --cov-fail-under` por arquivo via plugin `coverage-conditional-plugin` ou script auxiliar que lê `coverage.json` e falha se módulo específico cair abaixo de threshold mínimo
- [ ] Alternativa simples: adicionar marcador `# pragma: no cover` apenas em blocos genuinamente não-testáveis (ex: `if __name__ == "__main__"`) — não usar para esconder gaps

**Esforço estimado:** 1 hora (configuração) + depende de T1

---

### T0d — Auditoria de dependências com `pip-audit`

**Por quê:** O projeto usa ~15 dependências de produção (yt-dlp, anthropic, faster-whisper, mediapipe, pillow...). CVEs em qualquer uma delas podem expor a API key do Anthropic ou o token OAuth do YouTube. `pip-audit` verifica o lockfile contra o banco de dados PyPA Advisory.

**Arquivos afetados:** `pyproject.toml`, CI

**Subtarefas:**
- [ ] Adicionar `pip-audit>=2.7` em `[project.optional-dependencies] dev`
- [ ] Rodar `pip-audit` uma vez e resolver vulnerabilidades conhecidas (atualizar versões mínimas se necessário)
- [ ] Adicionar ao CI: `pip-audit --requirement <(uv export --no-dev)` (ou equivalente com lockfile)
- [ ] Documentar em `README.md` como rodar auditoria manualmente antes de atualizar deps

**Esforço estimado:** 1 hora

---

## P0 — Crítico (quebra CI ou confiabilidade em produção)

### T1 — Cobertura de testes: CLI e GUI em 0%

**Por quê:** `cli.py` (185 linhas) e toda a `gui/` têm 0% de cobertura. Regressões em comandos do dia-a-dia (`discover`, `triage`, `upload`) passam despercebidas. O threshold de 75% no `pyproject.toml` foi atingido pela cobertura dos stages, mas esses dois módulos críticos estão sem nenhuma rede de segurança.

**Arquivos afetados:** `src/canal_soberania/cli.py`, `src/canal_soberania/gui/`, `tests/`

**Subtarefas:**
- [ ] Criar `tests/test_cli.py` com testes dos principais comandos usando `typer.testing.CliRunner` + mock de `PipelineService`
  - [ ] `cs discover` — verifica que chama `service.run_discover()`
  - [ ] `cs triage --stage metadata` — verifica delegação correta
  - [ ] `cs triage --stage caption`
  - [ ] `cs download --pending`
  - [ ] `cs transcribe --pending`
  - [ ] `cs find-clips --pending`
  - [ ] `cs edit --pending`
  - [ ] `cs upload --platform youtube --pending`
  - [ ] `cs status` — testa output formatado
- [ ] Criar `tests/test_gui_integration.py` com testes de widget usando mock de `PipelineService`
  - [ ] `VideoTable.load_videos()` popula linhas corretamente
  - [ ] Clique em "Aprovar" emite sinal correto
  - [ ] `StageWorker` publica evento no `EventBus` ao completar
- [ ] Verificar que `pytest --cov` volta a ≥ 75% após adições

**Esforço estimado:** 1 dia

---

### T2 — Fechar conexões SQLite (resource leak)

**Por quê:** `cli.py:47` e `gui/main.py:42` abrem conexão via `connect()` mas nunca chamam `.close()`. Em aplicações de longa duração (GUI, scripts cron), isso acumula conexões abertas. Em testes, gera `ResourceWarning: unclosed database`.

**Arquivos afetados:** `src/canal_soberania/cli.py`, `src/canal_soberania/gui/main.py`, `tests/conftest.py` (ou equivalente)

**Subtarefas:**
- [ ] Em `cli.py`: adicionar `ctx.call_on_close(conn.close)` no callback principal do Typer
- [ ] Em `gui/main.py`: fechar `conn` antes de `sys.exit()` (após `app.exec()`)
- [ ] Em `tests/`: garantir que fixture de conexão use `yield` + `conn.close()` no teardown
- [ ] Rodar `pytest -W error::ResourceWarning` e confirmar zero warnings

**Esforço estimado:** 2–3 horas

---

### T3 — Corrigir erros mypy (101 erros → 0)

**Por quê:** 101 erros mypy significa que o type checker está desabilitado na prática. Bugs de tipagem (retorno `Any`, `None` não verificado) não são capturados antes do runtime. Alguns erros escondem bugs reais.

**Arquivos afetados:** `stages/thumbnail.py`, `stages/edit.py`, `stages/triage_metadata.py`, `stages/triage_transcript.py`, `llm.py`, `gui/windows/clip_review.py`, `gui/windows/main_window.py`

**Subtarefas:**
- [ ] **`stages/thumbnail.py:111,152`** — substituir `Image.LANCZOS` por `Image.Resampling.LANCZOS` (removido no Pillow 10+; causa `AttributeError` em runtime)
- [ ] **`llm.py:216–218`** — tipar dicionário de resposta com `TypedDict` em vez de `dict[str, Any]`; remover `# type: ignore` obsoletos
- [ ] **`stages/edit.py:201`** — ajustar tipo de retorno declarado (ou o retorno real) para `int | None`
- [ ] **`stages/triage_metadata.py:79–81`** e **`stages/triage_transcript.py:55–57`** — adicionar asserções de tipo antes de `int(obj)` / iteração em objetos do LLM
- [ ] **`gui/windows/clip_review.py:150`** — adicionar guard `if self._clip.youtube_publish_at:` antes de `[:16]`
- [ ] **`gui/windows/clip_review.py:423–424`** — verificar `clip_path_vertical is not None` antes de `.unlink()`
- [ ] **`gui/windows/main_window.py:201–202`** — checar `layout.itemAt()` retorna `None` (tipo `QLayoutItem | None`)
- [ ] **`strategies/transcription.py:30,44`** — anotar corretamente o decorator do tenacity para não gerar `unused-ignore`
- [ ] Remover todos os `# type: ignore` que o mypy reporta como `[unused-ignore]` (~30 instâncias)
- [ ] Rodar `mypy src/ --strict` e confirmar zero erros

**Esforço estimado:** 1 dia

---

## P1 — Alto (qualidade e manutenibilidade do core)

### T4 — Converter `Literal` para `StrEnum` em VideoStatus e ClipStatus

**Por quê:** `VideoStatus` e `ClipStatus` como `Literal` não são refatoráveis com segurança: um typo numa string (`"uploaded_youtbe"`) passa pelo type checker, o IDE não autocompleta, e renomear um status exige grep manual. `StrEnum` resolve tudo isso mantendo compatibilidade com SQLite (serializa como string).

**Arquivos afetados:** `src/canal_soberania/models.py`, todos os `stages/`, `repositories/sqlite.py`, `gui/`, `tests/`

**Subtarefas:**
- [ ] Em `models.py`: substituir `VideoStatus = Literal[...]` por `class VideoStatus(StrEnum)` com membros em UPPER_SNAKE
- [ ] Em `models.py`: idem para `ClipStatus` e `TriageStage`
- [ ] Atualizar `Video.status` e `Clip.status` para usar o enum como default: `status: VideoStatus = VideoStatus.DISCOVERED`
- [ ] Substituir todas as strings hardcoded de status nos stages (ex: `"pending_tiktok_manual"` → `ClipStatus.PENDING_TIKTOK_MANUAL`)
- [ ] Atualizar `_STATUS_COLOR` em `gui/widgets/video_table.py` para usar `VideoStatus.XXX.value` como chave
- [ ] Atualizar `_sort_priority` em `video_table.py` idem
- [ ] Garantir que `SqliteVideoRepository.get_by_status()` continua funcionando (StrEnum serializa como string — deve ser transparente)
- [ ] Rodar testes e confirmar zero regressões

**Esforço estimado:** 3–4 horas

---

### T5 — Tratamento de exceções por categoria nos stages

**Por quê:** Blocos `except Exception as exc:` genéricos em 15+ lugares nos stages mistura falhas de LLM, falhas de parsing e erros inesperados num único handler. Isso dificulta: (a) decidir se deve retentear, (b) logar contexto útil, (c) identificar bugs reais vs. falhas de rede transitórias.

**Arquivos afetados:** `stages/triage_metadata.py:147–161`, `stages/edit.py:249,271,282,299+`, `stages/find_clips.py`, `llm.py:94`

**Subtarefas:**
- [ ] Definir hierarquia de exceções em `canal_soberania/exceptions.py`: `PipelineError > LLMError, ParseError, NetworkError, EditError`
- [ ] Em `llm.py`: levantar `LLMError` em falhas da API Anthropic/OpenRouter
- [ ] Em `stages/triage_*.py`: capturar `LLMError` separado de `json.JSONDecodeError` (ParseError); re-raise `Exception` inesperada
- [ ] Em `stages/edit.py`: capturar `subprocess.CalledProcessError` como `EditError`; logar stdout/stderr do ffmpeg no erro
- [ ] Em `llm.py:94` (training log): logar stack trace completo, não suprimir silenciosamente
- [ ] Testes: verificar que `LLMError` resulta em retry e `ParseError` não

**Esforço estimado:** 4–6 horas

---

### T6 — Repositórios herdam explicitamente de Protocol

**Por quê:** `SqliteVideoRepository` e `SqliteClipRepository` implementam `VideoRepository`/`ClipRepository` estruturalmente (duck typing), mas sem herança explícita. Mypy não verifica conformidade: se um método for removido do Protocol, a implementação fica fora de sincronia silenciosamente.

**Arquivos afetados:** `src/canal_soberania/repositories/sqlite.py`, `src/canal_soberania/core/repositories.py`

**Subtarefas:**
- [ ] Em `repositories/sqlite.py`: adicionar herança explícita — `class SqliteVideoRepository(VideoRepository):`
- [ ] Idem para `SqliteClipRepository(ClipRepository)`
- [ ] Rodar mypy e corrigir eventuais assinaturas divergentes que se tornam visíveis
- [ ] Verificar que `InMemoryVideoRepository` em `tests/fakes.py` também herda do Protocol (para consistência)

**Esforço estimado:** 1–2 horas

---

### T7 — Consolidar conversão de row SQLite → modelo

**Por quê:** A lógica de `_row_to_video()` e `_row_to_clip()` (JSON de tags, tratamento de `ValidationError`) existe tanto em `db.py` quanto em `repositories/sqlite.py` com pequenas variações. DRY: uma fonte de verdade, um lugar para corrigir.

**Arquivos afetados:** `src/canal_soberania/db.py`, `src/canal_soberania/repositories/sqlite.py`

**Subtarefas:**
- [ ] Mover `_row_to_video()` e `_row_to_clip()` para `db.py` como funções de módulo (não métodos privados)
- [ ] `repositories/sqlite.py` importa e reutiliza essas funções
- [ ] Remover duplicatas e confirmar que testes de repositório continuam passando

**Esforço estimado:** 1–2 horas

---

## P2 — Médio (design de GUI e config)

### T8 — Refatorar GUI: widgets emitem signals em vez de chamar service diretamente

**Por quê:** `gui/windows/clip_review.py` chama `self._service.update_clip_text()` diretamente dentro de `_save_changes()`. Misturar lógica de persistência em janelas de diálogo dificulta testes (não dá para testar o widget sem um service real) e cria acoplamento forte entre camadas.

**Arquivos afetados:** `src/canal_soberania/gui/windows/clip_review.py`, `src/canal_soberania/gui/windows/main_window.py`

**Subtarefas:**
- [ ] Em `ClipReviewDialog`: declarar `Signal` para cada ação (`clip_saved = Signal(str)`, `clip_rejected = Signal(str)`)
- [ ] Substituir chamadas diretas a `self._service` por emissão de signals
- [ ] Em `MainWindow` (que abre `ClipReviewDialog`): conectar signals ao service
- [ ] Verificar que `StageWorker` já usa EventBus (não chamar service diretamente de worker thread)
- [ ] Adicionar testes de widget que instanciam `ClipReviewDialog` com service mockado e verificam signals

**Esforço estimado:** 3–4 horas

---

### T9 — Caminhos OAuth absolutos no Settings

**Por quê:** `settings.youtube_oauth_client_secrets_path` e `settings.youtube_oauth_token_path` são strings relativas (`"config/client_secrets.json"`). Se o processo for iniciado de um `cwd` diferente (ex: cron rodando de `/`), os caminhos quebram com `FileNotFoundError` silencioso.

**Arquivos afetados:** `src/canal_soberania/config.py`, `src/canal_soberania/stages/upload_youtube.py`

**Subtarefas:**
- [ ] Em `config.py`: adicionar `@validator` (ou `model_validator`) que resolve caminhos relativos para absolutos baseado em `BASE_DIR` (raiz do repo)
- [ ] Alternativa mais simples: usar `Path(__file__).parents[3] / "config/client_secrets.json"` como default
- [ ] Verificar que `upload_youtube.py` passa o `Path` em vez de `str` para `Credentials.from_authorized_user_file()`
- [ ] Adicionar teste que verifica que `Settings()` com caminho relativo resolve para absoluto

**Esforço estimado:** 1–2 horas

---

### T10 — Logs com contexto estruturado nos stages

**Por quê:** Vários stages logam sem incluir `video_id` ou duração no início/fim. Em produção, com 50+ vídeos processando, é impossível correlacionar um erro num log com o vídeo que causou.

**Arquivos afetados:** `stages/find_clips.py:169–170`, `stages/edit.py:333`, e demais stages que omitem `video_id`

**Subtarefas:**
- [ ] Padronizar início de cada stage com: `logger.info("stage={} video_id={} started", STAGE_NAME, video_id)`
- [ ] Padronizar fim com: `logger.info("stage={} video_id={} done | duration_s={:.1f}", ...)`
- [ ] Em `stages/edit.py`: incluir no log de conclusão se versão vertical E horizontal foram geradas
- [ ] Em erros: sempre incluir `video_id` ou `clip_id` no contexto

**Esforço estimado:** 1–2 horas

---

## P3 — Baixo (polish, backlog técnico)

### T11 — Whisper com `word_timestamps=True`

**Por quê:** As legendas palavra-por-palavra atualmente usam distribuição uniforme dentro de cada segmento (workaround em `stages/edit.py`). Habilitar `word_timestamps=True` no Whisper entrega timestamps reais por palavra, com sincronização exata. Melhora retenção no YouTube Shorts.

**Arquivos afetados:** `stages/transcribe.py`, `stages/edit.py`, `strategies/transcription.py`

**Subtarefas:**
- [ ] Em `strategies/transcription.py`: passar `word_timestamps=True` para `model.transcribe()`
- [ ] Atualizar o schema do JSON de transcript para incluir `"words": [{"word": ..., "start": ..., "end": ...}]` por segmento
- [ ] Em `stages/edit.py`: usar `seg["words"]` quando disponível em vez do fallback de distribuição uniforme
- [ ] Testes: verificar que o `.ass` gerado usa timestamps de palavra quando presentes
- [ ] Medir impacto em velocidade de transcrição (large-v3 com word_timestamps é ~15% mais lento)

**Esforço estimado:** 2–3 horas

---

### T12 — Dashboard de métricas (Streamlit)

**Por quê:** Atualmente a única forma de monitorar performance é via `cs status` no terminal. Um dashboard visual mostrando views, taxa de aprovação, custo da API e funil de status por canal facilitaria decisões de negócio (quando escalar, quais canais têm melhor ROI).

**Arquivos afetados:** novo `src/canal_soberania/dashboard/app.py`

**Subtarefas:**
- [ ] Criar `src/canal_soberania/dashboard/app.py` com Streamlit
- [ ] Métricas essenciais: funil de status (discover → upload), custo API do mês, views por canal
- [ ] Gráfico de linha: clips publicados por dia nas últimas 4 semanas
- [ ] Tabela de top clips: maior `score_viral` + maior view_count (quando disponível via YouTube Analytics)
- [ ] Adicionar `streamlit` em `pyproject.toml` como dependência opcional (`[dashboard]`)
- [ ] Documentar em `README.md`: `uv run streamlit run src/canal_soberania/dashboard/app.py`

**Esforço estimado:** 1 dia

---

### T13 — Emoji contextual nas legendas (OpusClip style)

**Por quê:** Diferencial visual para aumentar retenção. OpusClip exibe emoji relevante ao tema acima do bloco de legenda. Já detalhado no backlog de `proximas_tarefas.md`.

**Arquivos afetados:** `stages/edit.py`, `stages/find_clips.py`, `models.py`, `schema.sql`

**Subtarefas:**
- [ ] Criar migration `migrations/003_clips_emoji.sql`: `ALTER TABLE clips ADD COLUMN emoji TEXT;`
- [ ] Atualizar `ClipCandidate` em `models.py`: adicionar `emoji: str | None = None`
- [ ] Atualizar prompt `prompts/identificar_cortes.txt`: incluir campo `"emoji"` no JSON de saída
- [ ] Em `stages/edit.py`: adicionar `EmojiStyle` no header ASS; renderizar emoji em linha separada acima das legendas
- [ ] Parâmetro `show_emoji: bool = True` em `edit_clip()` (desligável por canal)
- [ ] Testar com fonte `Noto Color Emoji` no ffmpeg; documentar fallback se fonte não disponível
- [ ] Testes: verificar que ASS gerado contém `EmojiStyle` quando `emoji` fornecido

**Esforço estimado:** 4–6 horas

---

## Resumo de esforço

| # | Tarefa | Prioridade | Esforço | Impacto |
|---|--------|-----------|---------|---------|
| T0a | Ruff: C90 + S + T20 + PL | P0-estático | 3h | Complexidade e segurança |
| T0b | Vulture: código morto | P0-estático | 2h | Sem dead code |
| T0c | Coverage por módulo | P0-estático | 1h | CLI/GUI não regridem a 0% |
| T0d | pip-audit: CVEs em deps | P0-estático | 1h | Segurança de supply chain |
| T1 | Cobertura CLI e GUI | P0 | 1 dia | CI confiável |
| T2 | Fechar conexões SQLite | P0 | 3h | Zero leaks |
| T3 | Mypy zero erros | P0 | 1 dia | Type safety |
| T4 | Literal → StrEnum | P1 | 4h | Refactoring seguro |
| T5 | Exceções por categoria | P1 | 6h | Debugging e retry |
| T6 | Repositórios herdam Protocol | P1 | 2h | Conformidade mypy |
| T7 | Consolidar row conversion | P1 | 2h | DRY |
| T8 | GUI signals em vez de service | P2 | 4h | Testabilidade |
| T9 | Caminhos OAuth absolutos | P2 | 2h | Robustez cron |
| T10 | Logs com contexto | P2 | 2h | Observabilidade |
| T11 | Whisper word_timestamps | P3 | 3h | Legendas precisas |
| T12 | Dashboard Streamlit | P3 | 1 dia | Visibilidade métricas |
| T13 | Emoji nas legendas | P3 | 6h | Retenção visual |

**Total P0-estático:** ~7h (pode ser feito num único bloco — só muda config + corrige violações)
**Total P0:** ~2–3 dias · **Total P1:** ~1–2 dias · **Total P2+P3:** ~2–3 dias

### Ordem sugerida de execução

```
T0a → T0b → T3   (análise estática: tudo junto num bloco, ~2 dias)
T0c + T1         (cobertura: dependem um do outro)
T2               (30 min, rápido de fazer junto com T3)
T4 → T6 → T7    (tipos e repositórios: refactoring em cascata)
T5               (exceções: separado, não depende de T4)
T0d              (pip-audit: independente, a qualquer momento)
T8 → T9 → T10   (polish: quando GUI estiver funcional)
T11 → T13 → T12 (features: somente após canal em produção)
```
