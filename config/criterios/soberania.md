# Critérios de relevância — Soberania Nacional do Brasil

> **Este arquivo é a single source of truth do que entra no canal.** O prompt de triagem (`prompts/triagem_metadata.txt` e correlatos) consome este documento literalmente. Mudar aqui = mudar comportamento do filtro.

## Definição operacional

**Soberania nacional**, neste projeto, é a capacidade do Brasil de **decidir e executar políticas, produzir bens e serviços críticos, e proteger seus interesses** sem dependência estruturante de potências estrangeiras.

Um vídeo é **relevante** se, em **pelo menos 30% do tempo útil**, discute de forma substantiva um ou mais dos eixos abaixo, **com ângulo brasileiro** (foco no Brasil, não na geopolítica global em abstrato).

## Eixos temáticos (alta relevância)

### 1. Política externa e geopolítica
- Posição do Brasil em organismos internacionais (ONU, OMC, OMS)
- BRICS, BRICS+, multipolaridade
- Relações Brasil ↔ China, EUA, Rússia, União Europeia
- Mercosul, integração sul-americana
- Sanções, contra-sanções, alinhamento automático
- Diplomacia presidencial vs. Itamaraty

### 2. Defesa e Forças Armadas
- Indústria de defesa nacional (Embraer KC-390, Avibras, Taurus, Imbel)
- Projeto do submarino nuclear brasileiro
- Programa Gripen (caças)
- Cibersegurança nacional
- Amazônia Azul, vigilância de fronteiras (SISFRON, SISGAAZ)
- Orçamento e modernização das FAs

### 3. Economia soberana e indústria
- Reindustrialização, política industrial
- Desdolarização, alternativas ao SWIFT
- Política monetária e independência do Banco Central
- Dívida externa e câmbio
- Investimento estrangeiro estratégico (vs. predatório)
- Cadeias produtivas críticas (semicondutores, fertilizantes, fármacos)

### 4. Energia e recursos naturais
- Pré-sal, Petrobras como estatal estratégica
- Soberania energética (matriz, hidrelétricas, nuclear)
- Terras raras e minerais críticos
- Água como recurso estratégico
- Amazônia (preservação + presença brasileira)
- Agronegócio e segurança alimentar

### 5. Tecnologia e ciência
- Dependência tecnológica (chips, IA, software)
- Pesquisa pública (CNPq, FAPESPs, ICTs)
- Infraestrutura digital soberana (cabos submarinos, datacenters)
- IA brasileira e dados nacionais
- Espaço (INPE, AEB, programa de satélites)

### 6. Saúde soberana
- Indústria farmacêutica nacional (Butantan, Fiocruz, Hemobrás)
- Complexo Econômico-Industrial da Saúde (CEIS)
- Dependência de insumos farmacêuticos importados
- SUS como ativo estratégico

### 7. Cultura, educação e identidade
- Educação superior e ciência nacional
- Indústria cultural brasileira vs. soft power estrangeiro
- Língua portuguesa e CPLP
- História do Brasil sob ótica nacional-desenvolvimentista

## Eixos de relevância média

Tópicos que **podem** ser relevantes se ancorados em soberania, mas exigem ângulo explícito:

- Política partidária doméstica (relevante **apenas** se a discussão for sobre impacto na soberania, não fofoca)
- Eleições (relevante se sobre influência estrangeira, fraude, sistemas)
- Reformas (relevante se afetam capacidade estatal)
- Casos jurídicos (relevante se Lawfare, foreign interference)

## Exclusões explícitas (não-relevância)

Mesmo que o vídeo seja "de direita" ou "patriota" ou cite "Brasil", **não é relevante** se for sobre:

- Fofoca política, brigas pessoais entre figuras
- Religião sem ângulo de soberania
- Comentário esportivo (futebol, MMA) sem ângulo geopolítico
- Lifestyle, comportamento, autoajuda
- Comédia, entretenimento puro
- Crime comum, true crime
- Celebridades, vida pessoal
- Análise técnica de mercado financeiro sem dimensão soberana

## Sinais positivos (boost no score)

- Convidado é especialista creditado no tema (acadêmico, militar, diplomata, industrial)
- Vídeo cita dados, documentos, leis específicas
- Vídeo propõe ação política concreta para o Brasil
- Aborda dependência ou autonomia em setor específico
- Discute caso histórico relevante (ITA, Embraer, Petrobras pré-sal, etc.)

## Sinais negativos (penaliza score)

- Tom puramente lacrador ou puramente desesperançoso
- Generalidades sem dados ("o Brasil tem que ser forte")
- Teoria da conspiração sem evidência (NWO genérico, illuminati)
- Conteúdo que viola política do YouTube (discurso de ódio, desinformação eleitoral, saúde)
- Promoção de produto/curso ocupa >40% do vídeo

## Tom editorial do canal-destino

Os cortes publicados devem:

- **Soar informativos e firmes**, não panfletários
- **Evitar partidarismo explícito** (foco no tema, não em candidato/partido)
- **Citar fonte original sempre** (canal e episódio na descrição)
- **Não atacar pessoas**; focar argumentos e dados
- **Respeitar política do YouTube** sobre desinformação, eleições e discurso de ódio (relevância editorial não justifica strike)

## Calibração

A precisão do filtro deve ser revisada após cada lote de 50 vídeos processados. Anote em `docs/calibracao.md` (criar quando necessário):

- Falsos positivos (passou mas não era relevante) → ajustar prompt para excluir
- Falsos negativos (era relevante e foi reprovado) → ajustar prompt para incluir

Meta: **>= 80% de precisão** (vídeos aprovados que de fato rendem clipe publicável) ao fim da Fase 1.
