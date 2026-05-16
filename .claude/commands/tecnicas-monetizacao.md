---
description: Guia de técnicas de edição e estratégias para monetizar canais de cortes no YouTube sem strikes
---

Apresente o guia abaixo em formato estruturado com seções claras. Use o contexto do projeto (canais.yaml, criterios_relevancia.md) quando relevante para dar exemplos concretos.

---

# Técnicas de Monetização para Canais de Cortes — Guia Operacional

## 1. Transformações anti-"reused content" (obrigatórias para YPP)

O YouTube rejeita canais que apenas recortam conteúdo sem transformação. As transformações mínimas são:

### Reformatação
- **9:16 vertical obrigatório** (Shorts): crop dinâmico centralizado no rosto via mediapipe. Não usar crop estático que corta vozes por fora do quadro.
- Adicionar barras com gradiente para preencher espaço vazio (fundo desfocado do frame original é melhor que barras pretas).

### Legendas dinâmicas
- Estilo CapCut: **palavra por palavra**, cor vibrante (amarelo ou branco com contorno preto), fonte sem serifa em caixa alta.
- Timing exato (vem do Whisper), nunca legenda "bloco" de frase inteira.
- Razão: a maioria dos Shorts é assistida sem som — legenda é conteúdo, não acessibilidade.

### Identidade própria
- **Intro 3s**: logo do canal + nome + sting sonoro (pode ser livre de royalties do YouTube Audio Library).
- **Outro 3s**: CTA de inscrição ("Inscreva-se para mais cortes de [tema]") + logo.
- **Hook reescrito**: os primeiros 2s do Short devem mostrar o ponto mais impactante do clipe, não o início cronológico do trecho.

### Metadados originais
- Título: nunca copiar do vídeo-fonte. Escrever em 1ª pessoa do tema ("Brasil ignora aviso da OTAN" > "Ricardo Marcílio fala sobre OTAN").
- Descrição: crédito claro ao canal original + link + CTAs. Isso demonstra curadoria, não parasitismo.

---

## 2. Estratégia de publicação

### Frequência
- **3 Shorts/dia** é o sweet spot para crescimento rápido sem penalidade de spam.
- Espaçar: 9h / 14h / 19h (horários de pico de consumo no Brasil).
- Nunca subir mais de 5/dia — algoritmo interpreta como spam.

### Primeiras 48h são decisivas
- CTR e watch time nas primeiras 2h determinam o alcance inicial.
- Usar miniatura com texto grande e rosto em expressão forte (surpresa, indignação).
- Títulos com números, perguntas ou "palavra-bomba" (Ex: "REVELADO", "PROIBIDO", "URGENTE").

### Consistência de tema
- Canal de nicho específico (soberania/geopolítica) ranqueia mais fácil que canal genérico.
- Algoritmo de recomendação de Shorts favorece canais onde >70% dos vídeos são do mesmo tema.

---

## 3. Requisitos para YouTube Partner Program (YPP)

### Tier de monetização básica (Shorts)
- **500 inscritos** + **3 milhões de visualizações de Shorts nos últimos 90 dias**, OU
- 1.000 inscritos + 4.000h de watch time/ano (para vídeos longos)
- Sem strikes ativos, sem aviso de spam

### Para evitar rejeição no YPP
- O canal deve ter pelo menos **90 dias de existência** com atividade consistente.
- Todos os vídeos devem ter **transformação visível** (ver seção 1).
- Evitar republicar o mesmo clipe com variações mínimas.
- Canal-fonte deve ser credenciado na descrição.

---

## 4. Copyright e Fair Use

### Canais com alta tolerância (safe to clip)
- **PodPah** e **Flow Podcast**: tolerância alta documentada, canal de cortes é prática estabelecida.
- Usar `auto_publish: true` nestes canais após validação inicial.

### Canais com tolerância desconhecida
- Iniciar com `auto_publish: false`.
- Antes de escalar, verificar: (1) se o canal já tem canais de cortes existentes sem strike; (2) contato direto via DM pedindo autorização explícita (guarda como prova).

### Proteção jurídica (fair use BR)
- Lei 9.610/98, Art. 46: comentário, crítica e informação são permitidos sem autorização.
- Nosso canal **comenta e contextualiza** os trechos — não é redistribuição pura.
- Manter crédito visível (URL do original na descrição) reforça o argumento de curadoria.

---

## 5. Otimização de SEO para Shorts

### Títulos (máx 60 chars)
- Formato: `[Tema impactante] + [quem disse/onde]`
- Ex: "Brasil recusou armamento da OTAN | Flow Podcast"
- Evitar nomes de pessoas famosas como único gancho (risco de spam flag).

### Descrição
- Linha 1: frase de impacto (aparece antes do "ver mais").
- Linha 2+: crédito ao canal original com link, hashtags, link para vídeo completo.
- Hashtags: 3–5 relevantes (#Geopolitica #BrasilSoberano #Shorts).

### Hashtags estratégicas
- `#Shorts` sempre (classifica como Short).
- 1–2 de volume alto: `#Geopolitica`, `#Brasil`.
- 1–2 de nicho: `#SoberaniaEconomica`, `#AnaliseGeopolitica`.

---

## 6. Checklist pré-upload (automatizar no pipeline)

- [ ] Duração: 30–90s (ideal 55–60s para Shorts)
- [ ] Resolução: 1080x1920, 30fps, H.264, AAC
- [ ] Intro 3s com logo
- [ ] Outro 3s com CTA
- [ ] Legendas dinâmicas palavra-por-palavra em todos os segundos com fala
- [ ] Thumbnail: rosto em destaque, texto legível em miniatura (tamanho 200x356px)
- [ ] Título < 60 chars, original, sem nome do canal-fonte como único elemento
- [ ] Descrição com link do vídeo original + crédito
- [ ] Tags: mínimo 5, máximo 15

---

## 7. Métricas para acompanhar (após publicação)

| Métrica | Meta curto prazo | Meta longo prazo |
|---|---|---|
| CTR (click-through rate) | > 8% | > 12% |
| Watch time médio | > 50% do vídeo | > 70% |
| Ratio curtidas/views | > 2% | > 4% |
| Comentários/views | > 0.3% | > 1% |
| Retenção 3s | > 70% | > 85% |

**Sinal de que o nicho funciona:** 3+ vídeos com >1k views nas primeiras 48h.
**Sinal de que o formato funciona:** watch time médio > 60% consistente.

---

## 8. Fontes de referência

- YouTube Creator Academy: Política de uso permitido
- Estúdio do YouTube → Analytics → Retenção de público (identificar onde o vídeo perde o viewer)
- Canais modelo a estudar (BR): "PodPah Cortes", "Flow Cortes", canais de cortes do Nerdcast
