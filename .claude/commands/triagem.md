---
description: Roda triagem em todos os vídeos pendentes, parando para confirmar antes de ações irreversíveis (download).
---

Execute em sequência:

1. `cs discover` — descobre novos vídeos
2. `cs status` — mostra quantos `discovered`
3. **Pergunte ao usuário** antes de prosseguir: "Quantos vídeos rodar triagem? (default: todos)"
4. `cs triage --stage metadata --limit <n>`
5. `cs status` — quantos passaram?
6. `cs triage --stage caption --limit <n>`
7. `cs status` — final

Apresente:
- Quantos foram rejeitados em cada estágio (com 1 exemplo de cada)
- Quantos sobraram para a etapa de download (mostre títulos)
- Custo agregado da triagem (consultar `v_custo_mes_atual`)

**Não** chame `cs download` automaticamente — sempre confirme com o usuário antes.
