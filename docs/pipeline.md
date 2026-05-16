# Pipeline em detalhe

Doze etapas. Cada uma tem um estado de entrada e um estado de saída na tabela `videos` ou `clips`. Idempotente: rerodar não causa efeito colateral.

> Convenção: `status_in` é o estado que a etapa lê; `status_out_ok` é o estado se passa; `status_out_reject` se rejeitado.

---

## Stage 1 — discover

Lista vídeos novos dos canais em `config/canais.yaml`.

- **Input:** nenhum
- **Output:** novas linhas em `videos` com `status='discovered'`
- **Ferramenta:** YouTube Data API v3 (`search.list` + `videos.list`)
- **Cota:** ~1 unidade por canal por execução para listar, ~3 unidades por novo vídeo
- **Schedule:** 2x/dia (8h e 20h)
- **Idempotência:** `INSERT OR IGNORE` por `video_id`

Pseudocódigo:
```python
for canal in canais:
    novos = youtube.search().list(
        channelId=canal.channel_id,
        publishedAfter=now - 7d,
        type='video',
        order='date',
    )
    for v in novos:
        details = youtube.videos().list(id=v.id, part='snippet,contentDetails,statistics')
        insert_video(details, canal_id=canal.id, status='discovered')
```

---

## Stage 2 — triage_metadata

Triagem barata: usa só metadados (sem download). Decide se vale a pena baixar caption.

- **Input:** `videos` com `status='discovered'`
- **Output:** `status='triage_metadata_passed'` ou `'triage_metadata_rejected'`
- **Modelo:** Claude Haiku (rápido e barato)
- **Prompt:** `prompts/triagem_metadata.txt`
- **Threshold:** score >= 5/10 (configurável em `canais.yaml > parametros`)

Payload enviado ao LLM:
- Título do vídeo
- Descrição (truncada em 2000 chars)
- Tags (se houver)
- Top 20 comentários (busca via `commentThreads.list` ordenados por relevância)
- Tema primário do canal (de `canais.yaml`)

Output esperado (JSON):
```json
{
  "score": 7,
  "is_relevant": true,
  "themes_detected": ["geopolitica_brics", "industria_defesa"],
  "rationale": "Título menciona ..."
}
```

Persiste em `triage_results` com `stage='metadata'`.

---

## Stage 3 — triage_caption

Triagem com captions auto-geradas pelo YouTube. Ainda mais barato que Whisper.

- **Input:** `videos` com `status='triage_metadata_passed'`
- **Output:** `status='triage_caption_passed'` ou `'triage_caption_rejected'` (ou `'caption_unavailable'` se vai cair pro Whisper)
- **Ferramenta:** `yt-dlp --write-auto-sub --skip-download --sub-lang pt-BR --sub-format vtt`
- **Modelo:** Claude Haiku
- **Prompt:** `prompts/triagem_caption.txt`
- **Threshold:** score >= 6/10

Se caption não estiver disponível, marca como `'caption_unavailable'` e passa direto para download/transcribe (mais caro, mas necessário).

Otimização: envia caption em chunks de ~5k tokens se o vídeo for muito longo, e pede score agregado.

---

## Stage 4 — download

Baixa o vídeo aprovado para edição.

- **Input:** `videos` com `status` em `{triage_caption_passed, caption_unavailable}`
- **Output:** `status='downloaded'`
- **Ferramenta:** `yt-dlp`
- **Comando:** `yt-dlp -f 'bv*[height<=1080]+ba/b' --merge-output-format mp4 -o data/video/{id}.mp4 <url>`
- **Áudio separado** para Whisper: `yt-dlp -x --audio-format mp3 -o data/audio/{id}.mp3 <url>`

Limpeza: arquivos `data/video/*.mp4` com 7+ dias e status `uploaded_youtube` são removidos. Áudio fica permanentemente (é pequeno e útil para revisar).

---

## Stage 5 — transcribe

Whisper local com timestamps por palavra.

- **Input:** `videos` com `status='downloaded'`
- **Output:** `status='transcribed'`, JSON salvo em `data/transcripts/{id}.json`
- **Modelo:** faster-whisper large-v3
- **Idioma:** forçar `pt`
- **Word timestamps:** `word_timestamps=True` (necessário para legendas dinâmicas)

Output JSON:
```json
{
  "segments": [
    {
      "start": 12.3,
      "end": 18.7,
      "text": "...",
      "words": [{"word": "Brasil", "start": 12.3, "end": 12.8}, ...]
    }
  ],
  "language": "pt"
}
```

---

## Stage 6 — triage_transcript

Análise final do conteúdo completo, com Sonnet, antes de gastar identificação de cortes.

- **Input:** `videos` com `status='transcribed'`
- **Output:** `status='relevant'` ou `'rejected_final'`
- **Modelo:** Claude Sonnet
- **Prompt:** `prompts/triagem_transcript.txt`
- **Threshold:** score >= 7/10

Esta etapa é a última oportunidade de barrar conteúdo que parecia relevante pelos metadados mas que, no conteúdo, não é.

---

## Stage 7 — find_clips

Identifica 3-8 momentos de 30-90s relevantes ao tema **E** com potencial viral.

- **Input:** `videos` com `status='relevant'`
- **Output:** linhas em `clips` com `status='identified'`. Vídeo: `status='clips_identified'`
- **Modelo:** Claude Sonnet
- **Prompt:** `prompts/identificar_cortes.txt`

Payload: transcript com timestamps + critérios de relevância + critérios de viralização.

Output esperado:
```json
{
  "clips": [
    {
      "start_s": 423.5,
      "end_s": 489.0,
      "hook": "Por que o Brasil ainda compra fertilizante da Rússia?",
      "payoff": "Resposta: pacto comercial que data de...",
      "tema_soberania": "agronegocio_seguranca_alimentar",
      "score_viral": 8,
      "score_relevancia": 9,
      "justificativa": "..."
    }
  ]
}
```

Critérios de "viral" (no prompt):
- Hook nos primeiros 3s (afirmação forte, pergunta provocadora, número impactante)
- Pico emocional ou intelectual no meio
- Payoff/punchline ao final
- Frase memorável e citável

---

## Stage 8 — edit

Renderiza cada clip nos formatos finais.

- **Input:** `clips` com `status='identified'`
- **Output:** `status='edited'`, arquivos em `data/clips/{clip_id}_vertical.mp4` e `_horizontal.mp4`
- **Ferramenta:** ffmpeg via subprocess

Passos para o formato vertical (9:16, 1080x1920):
1. Cortar trecho: `ffmpeg -ss {start} -to {end} -i video.mp4 -c copy temp_cut.mp4`
2. Detectar bbox do rosto principal frame-a-frame (mediapipe) → série temporal suavizada
3. Crop dinâmico centrado no rosto, com fallback para centro se sem rosto detectado
4. Gerar `.ass` (Advanced SubStation) com legendas palavra-por-palavra a partir dos `word_timestamps`:
   - Fonte grande (60-80pt)
   - Highlight da palavra atual (cor diferente)
   - Sombra/contorno para legibilidade
5. Queimar legenda: `ffmpeg -vf "scale=...,crop=...,ass=legenda.ass" ...`
6. Concatenar intro (3s) + corpo + outro (3s)
7. Re-encode H.264 (`-c:v libx264 -preset medium -crf 23`) + AAC 128k

Formato horizontal (16:9, 1920x1080) é o trecho original sem reframe, mesma legenda e intro/outro, para upload opcional como vídeo longo curto.

---

## Stage 9 — thumbnail

Thumb estática para os uploads horizontais (Shorts/TikTok não usam thumb selecionada).

- **Input:** `clips` com `status='edited'`
- **Output:** `data/thumbs/{clip_id}.jpg`
- **Ferramenta:** Pillow + frame extraído por ffmpeg

Template fixo (não inventar a cada clip):
1. Frame em `start_s + 2` (passou o hook visual)
2. Overlay com gradiente escuro embaixo
3. Texto grande (1-3 palavras chave do hook) com fonte forte (ex: Anton, Bebas Neue)
4. Logo do canal no canto inferior direito

Recomendação: 3 cores fortes da identidade visual (ex: verde, amarelo, branco) usadas consistentemente.

---

## Stage 10 — metadata

Título, descrição e tags para o upload.

- **Input:** `clips` com `status='edited'`
- **Output:** `status='metadata_ready'`, campos `title/description/tags` preenchidos
- **Modelo:** Claude Sonnet
- **Prompt:** `prompts/gerar_metadata_clip.txt`

Regras hardcoded no prompt:
- Título <= 60 chars
- Descrição inclui sempre: 1 linha de hook + 3-5 linhas de contexto + link do vídeo original ("Episódio completo: ...") + créditos do canal-fonte + CTAs (inscrever, ativar sininho)
- Tags: 15 itens, mix de tema + nomes próprios + termos largos

---

## Stage 11 — upload_youtube

Upload + agendamento na conta YouTube do canal.

- **Input:** `clips` com `status='metadata_ready'`
- **Output:** `status='scheduled_youtube'`, `youtube_id` preenchido
- **Ferramenta:** `google-api-python-client` (`videos.insert`)
- **OAuth:** flow no primeiro uso, token persistido em `~/.config/canal-soberania/youtube_token.json`

Política de scheduling:
- Máximo 3 uploads/dia
- Horários fixos: 9h, 14h, 19h (BRT)
- `privacyStatus='private'` + `publishAt=<próximo slot livre>`
- Categoria: News & Politics (categoria 25)
- Default audio: not made for kids

---

## Stage 12 — upload_tiktok

No MVP: fila manual. Pipeline gera o arquivo, você sobe.

- **Input:** `clips` com `status='scheduled_youtube'` (sobe no TikTok depois que YouTube agendado)
- **Output:** `status='pending_tiktok_manual'`
- **Ação:** copia `clip_path_vertical` para `data/clips/pending_tiktok/{data}_{clip_id}.mp4`; cria arquivo `.txt` ao lado com título e descrição prontos para colar

Quando você fizer upload manual no TikTok (5min/dia via app), rode `cs mark-uploaded --platform tiktok --clip-id ...` para fechar o ciclo.

**Evolução:** Quando aprovado na TikTok Content Posting API, substitui o copy-to-folder por upload direto. Mesma interface no banco.

---

## Estados completos (máquina de estados)

```
videos.status:
  discovered
    ├─► triage_metadata_passed ──► triage_metadata_rejected
    ▼
  triage_caption_passed | caption_unavailable ──► triage_caption_rejected
    ▼
  downloaded
    ▼
  transcribed
    ▼
  relevant ──► rejected_final
    ▼
  clips_identified
    ▼
  done   (todos os clips processados)

clips.status:
  identified
    ▼
  edited
    ▼
  thumb_ready
    ▼
  metadata_ready
    ▼
  scheduled_youtube
    ▼
  pending_tiktok_manual
    ▼
  uploaded_tiktok   (estado final)
```

Erros vão para `*_error` (ex: `download_error`) com `error_message` populado, e podem ser retomados com `cs retry --status download_error`.
