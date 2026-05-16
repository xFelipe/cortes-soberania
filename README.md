# Canal Soberania

Pipeline automatizado de cortes de vídeo focado em soberania nacional do Brasil. Monitora canais brasileiros, identifica trechos relevantes ao tema, recorta para YouTube Shorts e TikTok, e publica automaticamente.

## Quick start

```bash
git clone <repo> canal-soberania && cd canal-soberania
uv sync
cp .env.example .env  # preencha as keys
sqlite3 data/canal.db < schema.sql
cs discover
cs status
```

## Documentação

- [`CLAUDE.md`](./CLAUDE.md) — contexto, stack, convenções (leia primeiro)
- [`proximas_tarefas.md`](./proximas_tarefas.md) — roadmap em fases
- [`docs/arquitetura.md`](./docs/arquitetura.md) — visão geral do sistema
- [`docs/pipeline.md`](./docs/pipeline.md) — etapas do pipeline em detalhe
- [`config/criterios_relevancia.md`](./config/criterios_relevancia.md) — o que conta como tema relevante

## Status

🟡 Em setup. Fase 0/4. Ver [`proximas_tarefas.md`](./proximas_tarefas.md).

## Licença

Uso pessoal. Conteúdo cortado mantém direitos dos autores originais; ver seção de fair use em `CLAUDE.md`.
