# Hooks para Vídeos Curtos — Pesquisa e Guia Operacional

> Aplicado ao contexto de canais de cortes de podcast brasileiro com tema soberania nacional.

---

## Por que os primeiros 3 segundos decidem tudo

O algoritmo do YouTube Shorts, TikTok e Reels mede **retenção** como sinal primário. Se o espectador sai nos primeiros 3s, o vídeo deixa de ser distribuído. Por isso, o hook não é introdução — é o vídeo. O restante é recompensa para quem ficou.

Regra operacional: **o corte começa na fala mais impactante, não na fala que antecede ela.**

---

## Os 3 vetores de um hook eficaz

Todo hook forte ataca simultaneamente:

| Vetor | O que é | Como aplicar em cortes |
|---|---|---|
| **Visual** | Primeiro frame prende o olho | Começar no rosto do convidado em close, zoom rápido, ou cartela de texto grande com a afirmação mais forte |
| **Auditivo** | Tom de voz ou efeito sonoro imediato | Cortar antes do "hm", "então", "olha só" — entrar direto na frase com energia; música de fundo sobe nos 1s iniciais |
| **Conteúdo** | A promessa implícita de que vale ficar | Ver seção abaixo — tipos de gancho por conteúdo |

---

## Tipos de gancho por conteúdo (do mais para o menos eficaz)

### 1. Afirmação polêmica / contraintuitiva
> "O Brasil foi o único país que..."  
> "Isso não te contaram na escola."  
> "A maioria está errada sobre isso."

Funciona porque gera **dissonância cognitiva** — o cérebro precisa resolver a contradição.

### 2. Pergunta que dói (aponta um problema do espectador)
> "Você sabe quem controla o seu combustível?"  
> "Por que o Brasil exporta petróleo e importa derivados?"

Funciona porque torna o espectador protagonista. A pergunta parece direcionada a ele.

### 3. Contraste / virada
> "Achei que era X… até descobrir Y."  
> "Em 1970 o Brasil tinha X. Hoje tem Y. O que aconteceu?"

Funciona porque estabelece uma jornada — o espectador quer saber como chegou de A a B.

### 4. Curiosidade aberta (cliffhanger)
> "O que ele disse depois disso mudou minha visão sobre tudo."  
> "A resposta do ministro foi o que ninguém esperava."

Atenção: exige que a entrega seja proporcional. Se decepcionar, gera abandono e comentário negativo.

### 5. Prova social / autoridade chocante
> "Esse general foi o único a falar isso em público."  
> "O economista que previu a crise explica o que vem aí."

Funciona bem para o nicho de soberania — o público valoriza fontes com credencial.

### 6. Dado surpreendente
> "O Brasil tem a 3ª maior reserva do mundo e 83% das pessoas não sabem."

Fácil de gerar a partir do transcript — qualquer número relevante que o convidado mencione.

---

## Padrões visuais de abertura (execução no ffmpeg/edit.py)

### Padrão A — "Corte direto na fala forte"
- Frame 0: rosto do convidado em close, já falando
- 0–2s: legenda dinâmica já aparece com a palavra-chave da frase
- 2s+: conteúdo normal

### Padrão B — "Cartela de texto"
- Frame 0–1s: fundo preto ou desfocado + texto grande com a afirmação mais forte do trecho
- 1s+: corta para o vídeo com a fala correspondente
- Útil quando o início do trecho não tem energia visual (convidado olhando para baixo, etc.)

### Padrão C — "Zoom dramático"
- Frame 0: enquadramento médio (padrão de podcast)
- 0–0.5s: zoom rápido para close extremo no rosto
- Sinaliza: "presta atenção, esse cara vai falar algo importante"

### Padrão D — "Pergunta na tela"
- Frame 0: a pergunta do hook aparece em texto, voz do apresentador fazendo a pergunta
- Convidado responde imediatamente
- Ótimo quando o apresentador já fez uma pergunta boa — cortar desde a pergunta, não só a resposta

---

## O que NÃO fazer (erros comuns em canais de cortes)

| Erro | Por que mata a retenção |
|---|---|
| Começar com "Então como eu falava..." ou "É, voltando ao ponto..." | Sem energia, parece meio de episódio |
| Intro animada de canal nos primeiros 3s | Espectador pula antes de ver o conteúdo |
| Fade in gradual | Plataformas de short não têm paciência para fade |
| Texto de legenda pequeno demais | 70% assiste sem som — o texto precisa ser lido em 0.3s |
| Corte que começa com silêncio | Silêncio = sinal de que acabou |
| Hook que não entrega o prometido | Pior que não ter hook — gera abandono + comentário negativo |

---

## Duração ideal por plataforma

| Plataforma | Sweet spot | Máximo razoável |
|---|---|---|
| YouTube Shorts | 30–50s | 60s |
| TikTok | 15–30s | 60s |
| Instagram Reels | 15–30s | 45s |

Para o nicho de soberania (conteúdo denso, público adulto), 45–60s tende a funcionar melhor que 15s — o tema pede desenvolvimento mínimo para convencer.

---

## Referências brasileiras para estudar

### Canais de cortes que funcionam bem

| Canal | Por que estudar | Nicho |
|---|---|---|
| **Cortes do Flow** | Volume alto, consistência, legendas queimadas padronizadas | Política, cultura, negócios |
| **Cortes do PodPah** | Hooks emocionais e polêmicos, timing de corte agressivo | Entretenimento, celebridades |
| **Cortes Inteligência Ltda** | Público analítico similar ao nosso, ganchos com dados e autoridade | Política, geopolítica, economia |
| **Cortes Irmãos Dias Podcast** | Temas de soberania econômica, estilo mais sério | Economia, investimento, Brasil |

### O que observar nesses canais
1. **Primeiro frame** — como começa? Fala, cartela, pergunta?
2. **Posição da legenda** — onde está na tela, tamanho, contraste
3. **Onde o corte começa** — antes ou depois da fala mais forte?
4. **Thumbnail** — tem relação com o hook do vídeo?
5. **Títulos** — copywriting de curiosidade ou afirmação direta?

---

## Checklist de qualidade para o hook (usar no `find_clips.py` ou revisão manual)

- [ ] O vídeo começa com energia (não com "hm", "então", "como eu dizia")?
- [ ] A frase de abertura faz sentido sem contexto anterior?
- [ ] Um leigo que não conhece o convidado entenderia o que está em jogo?
- [ ] Tem legenda visível nos primeiros 2s?
- [ ] A promessa do hook é entregue dentro dos próximos 45s?
- [ ] Não começa com intro animada?

---

## Aplicação no pipeline

### No prompt `identificar_cortes.txt`
Priorizar trechos que:
- Começam com afirmação forte, dado surpreendente ou pergunta retórica
- O convidado fala com energia elevada (detectável via análise de prosódia futura)
- Contêm o "momento de virada" do argumento (não a conclusão, mas a revelação)

### No `edit.py`
- Implementar corte de 0.3–0.5s antes da fala principal (para dar respiro visual)
- Legenda deve aparecer imediatamente, sem delay
- Se o trecho começa "fraco" (pausa, hesitação): considerar Padrão B (cartela de texto)

### No `metadata.py` (geração de título)
Título deve espelhar o hook — se o hook é uma pergunta, o título pode ser a resposta parcial que gera curiosidade:
- Hook: "Por que o Brasil exporta petróleo bruto?"
- Título: "O escândalo que ninguém fala sobre o petróleo brasileiro"

---

*Pesquisa realizada em mai/2026. Atualizar se métricas do canal indicarem padrões diferentes.*
