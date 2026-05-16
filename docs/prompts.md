# Prompts

Todos os prompts vivem em `prompts/` como texto puro (sem template engine). Carregamento simples: `Path("prompts/X.txt").read_text()` + `.format(**vars)`.

## Princípios

- **Versionamento por arquivo:** mudança grande = novo arquivo `prompts/X_v2.txt`. Alternar via config, não sobrescrever.
- **Output JSON sempre.** Saída estruturada parseada com `pydantic`. Falha de parse → retry com prompt enxuto.
- **Critérios fora do prompt principal:** quando possível, o prompt **lê** `config/criterios_relevancia.md` em runtime e injeta como contexto. Isso evita duplicação.
- **Few-shot quando ajuda:** triagem e identificação de cortes ganham com 2-3 exemplos. Geração de metadata não precisa.

## Prompts e modelos

| Prompt | Arquivo | Modelo | Custo aprox. por chamada |
|---|---|---|---|
| Triagem por metadados | `prompts/triagem_metadata.txt` | Haiku | ~$0.001 |
| Triagem por caption | `prompts/triagem_caption.txt` | Haiku | ~$0.005 |
| Triagem por transcript completo | `prompts/triagem_transcript.txt` | Sonnet | ~$0.03 |
| Identificar cortes | `prompts/identificar_cortes.txt` | Sonnet | ~$0.05 |
| Gerar metadata do clip | `prompts/gerar_metadata_clip.txt` | Sonnet | ~$0.01 |

## Estrutura padrão

Cada prompt segue:

```
[SISTEMA] (papel + tom)

[CONTEXTO] (carregado dinamicamente: critérios, canal-fonte, etc.)

[ENTRADA] (dados do vídeo/transcript)

[TAREFA] (instrução clara, uma única coisa)

[FORMATO DE SAÍDA] (JSON schema explícito + exemplo)

[EXEMPLOS] (opcional, 1-3 few-shot)
```

## Calibração

Após cada lote de ~50 vídeos processados, comparar:
- Decisão do prompt vs. revisão manual
- Anotar erros em `docs/calibracao.md` (criar quando necessário)
- Ajustar prompt e re-rodar nos casos arquivados

**Não** mude o prompt sem rodar pelo menos 10 casos do histórico para verificar regressão.

## Custos e quotas

Estimativa mensal nos 6 canais iniciais (assumindo 5 vídeos novos/canal/semana = 120 vídeos/mês):

- Triagem metadata (Haiku, 120x): ~$0.12
- Triagem caption (Haiku, ~50x): ~$0.25
- Triagem transcript (Sonnet, ~20x): ~$0.60
- Identificar cortes (Sonnet, ~15x): ~$0.75
- Metadata por clip (Sonnet, ~60x): ~$0.60
- **Total: ~$2.30/mês de Claude API**

Folga de 10x prevista. Ver `cs costs` para acompanhar real.
