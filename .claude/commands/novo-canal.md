---
description: Adiciona um novo canal ao config/canais.yaml com os campos padronizados.
argument-hint: <url-do-canal-youtube>
---

O usuário quer adicionar o canal: $ARGUMENTS

1. Inferir um `id` em snake_case a partir do handle/nome.
2. Buscar metadados básicos do canal (nome, descrição, ~5 vídeos recentes) via web fetch ou yt-dlp para entender o tema.
3. Sugerir valores para:
   - `tema_primario` (escolher da lista usada nos canais existentes)
   - `tolerancia_cortes` (alta/media/baixa/desconhecida — pesquisar se o canal tem canal de cortes oficial)
   - `peso` (1.0 padrão; ajustar se for nicho mais central que os atuais)
   - `auto_publish` (false por padrão até validar)
4. Mostrar o YAML diff proposto para `config/canais.yaml` e pedir confirmação antes de editar.
5. Após confirmação, editar o arquivo.
6. Rodar `cs discover --canal <id>` para validar.
