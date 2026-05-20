# Frontend — Canal Soberania

Documentação da camada UI: arquitetura, padrões, como estender.

**Atualizado após Onda 6** (Fase B em andamento). Ondas concluídas: 0–6. Próximas: `proximas_tarefas.md`.

---

## Stack

| Peça | Versão | Papel |
|---|---|---|
| Tauri | 2.x | Shell nativo Linux/Windows, acesso a arquivo local |
| React | 19 | Renderização |
| Vite | 7 | Dev server e build |
| Tailwind | 4 (via `@tailwindcss/vite`) | Estilização — sem `tailwind.config.js` |
| shadcn/ui | 4.7 preset Radix/Nova | Componentes base (alert-dialog, badge, button, card, dialog, input, label, scroll-area, select, separator, sheet, switch, tabs, tooltip) |
| radix-ui | 1.4 (pacote unificado) | Primitivos não-wrappados: Checkbox, ContextMenu, Slider |
| TanStack Router | 1.x | Roteamento tipado |
| TanStack Query | 5.x | Server state, cache, invalidação |
| TanStack Table | 8.x | Tabelas com sort/filter/pagination |
| sonner | 2.x | Toasts |
| cmdk | 1.x | Command palette (Ctrl+K) — implementado na Onda 7 |
| recharts | 3.x | Gráficos (bar chart na página Stats) |
| @tanstack/react-virtual | 3.x | Virtualização de listas longas (log da pipeline) |
| lucide-react | 1.x | Ícones |
| zod | 4.x | Validação de schema (disponível) |

---

## Estrutura de diretórios

```
ui/
├── src/
│   ├── main.tsx              ← entry; monta QueryClientProvider + RouterProvider
│   ├── App.tsx               ← não usado (router assume o controle)
│   ├── index.css             ← variáveis CSS Tailwind v4 + fontes
│   │
│   ├── lib/
│   │   ├── api.ts            ← cliente HTTP tipado + tipos de domínio
│   │   ├── query.ts          ← QueryClient singleton (staleTime 5s)
│   │   ├── router.tsx        ← createRouter com todas as rotas
│   │   ├── shortcuts.ts      ← hooks de teclado por contexto
│   │   ├── sse.ts            ← useSSE() — EventSource + invalidação queries
│   │   ├── status-labels.ts  ← VideoStatus / ClipStatus + meta PT-BR + cores
│   │   ├── theme.tsx         ← ThemeProvider + useTheme() (Light/Dark/System)
│   │   └── utils.ts          ← cn() helper (clsx + tailwind-merge)
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── RootLayout.tsx     ← grid 3.75rem+1fr × 1fr+1.75rem
│   │   │   ├── Sidebar.tsx        ← 5 ícones + badges TanStack Query
│   │   │   ├── StatusFooter.tsx   ← SSE dot + custo mês
│   │   │   └── CommandPalette.tsx ← cmdk dialog (placeholder até Onda 7)
│   │   └── ui/
│   │       └── *.tsx             ← shadcn/ui gerados via CLI
│   │
│   └── routes/
│       ├── index.tsx             ← redirect / → /inbox
│       ├── inbox.tsx             ← fila de revisão (cards + J/K/A/R)
│       ├── biblioteca.tsx        ← tabela de vídeos e clipes (TanStack Table)
│       ├── clip-review.tsx       ← review detalhado de um clipe
│       ├── stats.tsx             ← 4 cards + recharts + tabela por canal
│       ├── settings.tsx          ← form editável + import .env + cheatsheet
│       └── operacao/
│           ├── layout.tsx        ← sub-nav Pipeline / Discover / Canais
│           ├── pipeline.tsx      ← 4 grupos de stages + log SSE virtualizado
│           ├── discover.tsx      ← discover ad-hoc + histórico de sessão
│           └── canais.tsx        ← tabela + Sheet CRUD + switch ativo
│
├── src-tauri/
│   ├── tauri.conf.json       ← productName "Canal Soberania", 1400×900
│   └── src/                  ← código Rust Tauri (boilerplate)
│
├── package.json
└── pnpm-workspace.yaml       ← allowBuilds (pnpm 11 requer)
```

---

## lib/api.ts — cliente HTTP

Todas as chamadas à FastAPI passam por aqui. Padrão:

```ts
// 1. getToken() — tenta Tauri plugin-fs; fallback localStorage
// 2. request<T>(path, init) — injeta Bearer token e faz fetch
// 3. Funções específicas agrupadas por recurso: api.clips.*, api.videos.*, etc.
```

### Tipos exportados

| Tipo | Uso |
|---|---|
| `Video` | Resposta de `GET /videos` e `GET /videos/{id}` |
| `Clip` | Resposta de `GET /clips` e `GET /clips/{id}` |
| `InboxItem` | Item de `GET /inbox` (type: "clip" \| "video") |
| `InboxResponse` | `{ items: InboxItem[], total: number }` |
| `StatsSummary` | `{ [status: string]: number }` |
| `StatsCosts` | `{ total_usd: number }` |
| `StatsCostDetail` | Linha de `GET /stats/costs/detail` |
| `StatsByCanal` | Linha de `GET /stats/by-canal` |
| `StatsThroughput` | Linha de `GET /stats/throughput` |
| `FaceCropData` | Resposta de `GET /clips/{id}/face-crop` |
| `ClipPatch` | Body de `PATCH /clips/{id}` |
| `Canal` | Schema de canal (body de POST/PUT `/canais`) |
| `DiscoverAdhocParams` | Body de `POST /discover/adhoc` |
| `ConfigValues` | `Record<string, string \| number \| boolean>` |

### Métodos disponíveis

```ts
// Stats
api.stats.summary()             // GET /stats/summary
api.stats.costs()               // GET /stats/costs
api.stats.costsDetail()         // GET /stats/costs/detail
api.stats.byCanal()             // GET /stats/by-canal
api.stats.throughput()          // GET /stats/throughput

// Inbox
api.inbox.get()                 // GET /inbox

// Stages / Pipeline
api.stages.run(name)            // POST /stages/{name}/run
api.stages.cancel()             // POST /pipeline/cancel
api.stages.reset()              // POST /pipeline/reset

// Discover ad-hoc
api.discover.adhoc(params)      // POST /discover/adhoc

// Vídeos
api.videos.list(params?)        // GET /videos
api.videos.approve(video_id)    // POST /videos/{id}/approve
api.videos.reject(video_id)     // POST /videos/{id}/reject

// Clipes
api.clips.list(params?)         // GET /clips
api.clips.get(clip_id)          // GET /clips/{id}
api.clips.approve(clip_id)      // POST /clips/{id}/approve
api.clips.reject(clip_id)       // POST /clips/{id}/reject
api.clips.discard(clip_id)      // DELETE /clips/{id}
api.clips.patch(clip_id, data)  // PATCH /clips/{id}
api.clips.trim(id, start, end)  // POST /clips/{id}/trim
api.clips.faceCrop(clip_id)     // GET /clips/{id}/face-crop
api.clips.sourceVideoUrl(id)    // retorna string URL (não chama request)

// Canais
api.canais.list()               // GET /canais
api.canais.create(canal)        // POST /canais → 201
api.canais.update(id, canal)    // PUT /canais/{id}
api.canais.toggleAtivo(id, v)   // PATCH /canais/{id}/ativo
api.canais.remove(id)           // DELETE /canais/{id}

// Config
api.config.get()                // GET /config
api.config.put(patch)           // PUT /config → merge .env
```

`sourceVideoUrl` retorna uma URL direta (não passa por `request<T>`) porque precisa do `?token=` no query param — usada diretamente como `src` do `<video>`.

---

## lib/router.tsx — rotas

TanStack Router com árvore de rotas — `/operacao` é aninhada com três filhos:

| Path | Componente | Nota |
|---|---|---|
| `/` | redirect → `/inbox` | |
| `/inbox` | `routes/inbox.tsx` | |
| `/biblioteca` | `routes/biblioteca.tsx` | |
| `/clip-review/$clipId` | `routes/clip-review.tsx` | |
| `/operacao` | redirect → `/operacao/pipeline` | |
| `/operacao/pipeline` | `routes/operacao/pipeline.tsx` | |
| `/operacao/discover` | `routes/operacao/discover.tsx` | |
| `/operacao/canais` | `routes/operacao/canais.tsx` | |
| `/stats` | `routes/stats.tsx` | |
| `/settings` | `routes/settings.tsx` | |

**Estrutura de `routeTree`:** a chamada `operacaoRoute.addChildren([...])` é feita **inline** dentro de `rootRoute.addChildren([...])` para que o TypeScript consiga inferir a união completa de paths:

```ts
const routeTree = rootRoute.addChildren([
  indexRoute, inboxRoute, bibliotecaRoute,
  operacaoRoute.addChildren([operacaoIndexRoute, pipelineRoute, discoverRoute, canaisRoute]),
  statsRoute, settingsRoute, clipReviewRoute,
]);
```

Se `addChildren` for chamado separadamente (fora do `rootRoute.addChildren`), o TypeScript não consegue inferir `/operacao/pipeline` como path válido e as chamadas `navigate({ to: "/operacao/pipeline" })` falham na compilação.

Para adicionar uma nova rota:
1. Crie `ui/src/routes/minha-rota.tsx`
2. Em `router.tsx`: `import MyPage from "@/routes/minha-rota"`, crie `createRoute`, adicione ao `routeTree`

---

## lib/shortcuts.ts — sistema de atalhos

Três hooks, cada um para um contexto de navegação:

### `useGlobalShortcuts(onCommandPalette)`
Montado em `RootLayout`. Sempre ativo.
- `Ctrl+1..5` → navega para as 5 rotas principais
- `Ctrl+K` → abre command palette

### `useInboxShortcuts(handlers)`
Montado em `inbox.tsx`. Ativo quando `enabled = items.length > 0`.
- `J` / `K` → navega para baixo/cima na lista
- `A` → aprova item focado
- `R` → rejeita item focado

### `useClipReviewShortcuts(handlers)`
Montado em `clip-review.tsx`. Ativo quando `enabled = !isLoading && !isError`.
- `[` → define in point no tempo atual do vídeo
- `]` → define out point no tempo atual do vídeo
- `Space` → play/pause
- `A` → aprova clipe (equivale a "Aprovar e próximo")
- `R` → rejeita clipe

**Regra de guarda:** todos os handlers verificam `e.target.tagName` e ignoram quando o foco está em `INPUT` ou `TEXTAREA`. Exceção: `Space` em ClipReview é bloqueado apenas em textareas.

---

## lib/sse.ts — eventos em tempo real

`useSSE(onEvent?)` conecta ao `GET /events?token=<token>` via `EventSource` nativo.

Ao receber um evento:
- Qualquer `event_type` contendo `"clip"` → invalida `["clips"]` e `["inbox"]`
- Qualquer `event_type` contendo `"video"` → invalida `["videos"]` e `["inbox"]`
- Sempre invalida `["stats"]`
- Se `onEvent` for fornecido, chama `onEvent({ type, data })` após a invalidação

```ts
export interface SSEEvent { type: string; data: unknown; }

// Sem callback (só invalida queries — uso padrão em StatusFooter)
useSSE()

// Com callback (recebe eventos adicionalmente)
useSSE((event) => {
  if (event.type === "discover_adhoc_done") {
    const d = event.data as { handle: string; inserted: number; persisted: boolean };
    setHistory(prev => [{ handle: d.handle, inserted: d.inserted, ... }, ...prev]);
  }
})
```

O callback é guardado em `useRef` para que não re-dispare o `useEffect` ao re-render. Totalmente backward-compatible — chamadas sem argumento continuam funcionando.

O SSE é montado em `RootLayout` (ou `StatusFooter`), portanto funciona em todas as rotas. Rotas que precisam de callbacks (pipeline.tsx, discover.tsx) chamam `useSSE` novamente com callback — múltiplas instâncias são permitidas; cada uma cria sua própria conexão SSE independente.

---

## lib/status-labels.ts — mapeamento de status

Single source of truth para labels, cores e mapeamento de stages.

```ts
VIDEO_STATUS_META: Record<VideoStatus, { label: string; color: string; active: boolean }>
CLIP_STATUS_META:  Record<ClipStatus,  { label: string; color: string }>
ACTIVE_VIDEO_STATUSES: Set<VideoStatus>  // statuses em progresso ativo

// Mapeamento stage → statuses que indicam trabalho pendente
STAGE_PENDING_STATUSES: Record<string, string[]>
// Ex: "triage_metadata" → ["discovered"], "find_clips" → ["approved_for_clips"]

// Soma quantos vídeos/clips estão pendentes para um dado stage
stagePendingCount(summary: Record<string, number>, stageName: string): number
```

`stagePendingCount` é usado por `pipeline.tsx` para mostrar o badge de pendentes ao lado de cada botão de stage, consumindo `GET /stats/summary`.

**Para adicionar um novo status:** adicione ao enum `VideoStatus` ou `ClipStatus` e ao respectivo `*_STATUS_META`. O compilador TypeScript vai apontar todos os lugares que precisam de atualização.

---

## Padrões de estado (TanStack Query)

### Query keys canônicas

| Recurso | Key |
|---|---|
| Inbox | `["inbox"]` |
| Lista de vídeos | `["videos"]` |
| Um vídeo | `["video", video_id]` |
| Lista de clipes | `["clips"]` |
| Um clipe | `["clip", clip_id]` |
| Face crop | `["clip-face-crop", clip_id]` |
| Stats summary | `["stats", "summary"]` |
| Stats costs | `["stats", "costs"]` |
| Stats costs detail | `["stats", "costs-detail"]` |
| Stats por canal | `["stats", "byCanal"]` |
| Stats throughput | `["stats", "throughput"]` |
| Lista de canais | `["canais"]` |
| Config editável | `["config"]` |

**Regra:** ao mutar qualquer vídeo/clipe, invalidar `["inbox"]` e `["stats"]` além da key específica. Ao mutar canais, invalidar `["canais"]`. Ao salvar config, não há invalidação automática — o form exibe um aviso de "reiniciar backend".

### Padrão de mutação

```tsx
const mutation = useMutation({
  mutationFn: (id: string) => api.clips.approve(id),
  onSuccess: () => {
    toast.success("...");
    void queryClient.invalidateQueries({ queryKey: ["clips"] });
    void queryClient.invalidateQueries({ queryKey: ["inbox"] });
    void queryClient.invalidateQueries({ queryKey: ["stats"] });
  },
  onError: (e: Error) => toast.error(e.message),
});
```

---

## routes/inbox.tsx

Fila de revisão priorizada consumindo `GET /inbox`.

**Fluxo:**
1. `useQuery(["inbox"], api.inbox.get, { refetchInterval: 15000 })`
2. `useState<number>` para índice do item focado
3. `useInboxShortcuts` para J/K/A/R
4. `useRef<HTMLDivElement[]>` para scroll automático ao item focado
5. Dois tipos de card: `ClipCard` (hook, status, score viral, duração) e `VideoCard` (título, canal, status)
6. Mutar → `invalidateQueries(["inbox"])` + `invalidateQueries(["stats"])`

**Para navegar ao ClipReview a partir do inbox:**
```tsx
navigate({ to: "/clip-review/$clipId", params: { clipId: item.clip_id! } })
```
(ainda não implementado no card — link a adicionar na Onda 6+)

---

## routes/biblioteca.tsx

Dois tabs (Clipes / Vídeos) com TanStack Table.

**Padrão DataTable:**
```tsx
const table = useReactTable({
  data: filteredData,   // filtro client-side por search + statusFilter
  columns,
  state: { sorting, rowSelection },
  enableRowSelection: true,
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  initialState: { pagination: { pageSize: 50 } },
});
```

**Componentes reutilizáveis dentro do arquivo:**
- `StatusChip` — badge colorido por status
- `FilterChips<S>` — chips de filtro por enum de status
- `BulkToolbar` — toolbar sticky quando `rowSelection` tem itens
- `RowContextMenu` — `radix-ui` ContextMenu com approve/reject/copy/open YouTube
- `ClipGrid` — view alternativa em grid de cards 9:16

---

## routes/clip-review.tsx

Review detalhado de um clipe. Parâmetro de rota: `$clipId`.

### Layout

```
┌─────────────────────────────┬──────────────────────┐
│ breadcrumb: Inbox / hook    │                      │
├─────────────────────────────┤                      │
│                             │  Hook (textarea)     │
│  <video> + <canvas overlay> │  Score viral (1–10)  │
│                             │  In / Out (num.)     │
│  Dual-thumb Slider (in/out) │  Notas               │
│  Scrubber (posição atual)   │  ──────────────────  │
│                             │  [Aprovar e próximo] │
│  Space · [ · ] · A · R      │  [Rejeitar]          │
│                             │  [Excluir…]          │
└─────────────────────────────┴──────────────────────┘
```

### CropOverlay

`<canvas>` absoluto sobre o `<video>`. Recebe `crop_x`, `crop_width`, `source_width`, `source_height` (de `GET /clips/{id}/face-crop`). Escala os valores da resolução do vídeo-fonte para as dimensões de display via `ResizeObserver`. Desenha:
- Máscara escura (`rgba(0,0,0,0.55)`) nos lados fora do crop
- Borda branca delimitando o retângulo 9:16

**Fallback:** enquanto `faceCrop` não retorna (ou se falhar), a overlay não é renderizada (`cropData === undefined`).

### Autosave

Dois `useEffect` com `clearTimeout`:

```
hook / scoreViral → debounce 500ms → PATCH /clips/{id}
inPoint / outPoint → debounce 500ms → POST /clips/{id}/trim
```

`formInitialized` (flag de `useRef`) impede que o autosave dispare na montagem inicial antes de os valores serem carregados do servidor.

### Video src autenticado

O `<video src>` não passa por `request<T>()`, então o token precisa ir no query param:

```ts
useEffect(() => {
  void getToken().then((token) => {
    setVideoSrc(`${API_URL}/clips/${clipId}/source-video?token=${token}`);
  });
}, [clipId]);
```

O backend (`verify_token`) aceita `?token=` como alternativa ao header `Authorization: Bearer`.

### Loop A↔B

```ts
useEffect(() => {
  const v = videoRef.current;
  const check = () => { if (v.currentTime >= outPoint) v.currentTime = inPoint; };
  v.addEventListener("timeupdate", check);
  return () => v.removeEventListener("timeupdate", check);
}, [inPoint, outPoint]);
```

### "Aprovar e próximo"

```ts
approveMutation.onSuccess = async () => {
  const inbox = await api.inbox.get();
  const next = inbox.items.find(i => i.clip_id && i.clip_id !== clipId);
  if (next?.clip_id) navigate({ to: "/clip-review/$clipId", params: { clipId: next.clip_id } });
  else navigate({ to: "/inbox" });
};
```

---

## Componentes de UI disponíveis

### shadcn/ui (em `components/ui/`)

`alert-dialog`, `badge`, `button`, `card`, `dialog`, `input`, `label`, `scroll-area`, `select`, `separator`, `sheet`, `switch`, `tabs`, `tooltip`

### radix-ui (import direto do pacote unificado)

Primitivos não wrappados disponíveis como `import { Slider, Checkbox, ContextMenu, ... } from "radix-ui"`:
- `Slider.Root / Track / Range / Thumb` — usado em clip-review (in/out + scrubber + score viral)
- `Checkbox.Root / Indicator` — usado em biblioteca (bulk select)
- `ContextMenu.Root / Trigger / Content / Item / Separator / Portal` — usado em biblioteca

### Para adicionar um novo componente shadcn

```bash
cd ui && pnpm dlx shadcn@latest add <componente>
```

Gera em `ui/src/components/ui/<componente>.tsx`.

---

## Tooling de desenvolvimento

### PATH necessário (sempre que abrir terminal)

```bash
export PATH="$HOME/.local/node22/bin:$HOME/.local/share/pnpm/bin:$HOME/.cargo/bin:$PATH"
```

### Comandos frequentes

```bash
cd ui

# Type check (não compila, só valida)
pnpm tsc --noEmit

# Dev server React (sem Tauri, abre no browser)
pnpm dev

# Dev com janela Tauri (requer libs gtk instaladas)
pnpm tauri dev

# Build de produção
pnpm build
```

### Libs nativas Linux necessárias (Tauri)

```bash
sudo apt install -y libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev
```

### Testar frontend sem backend

1. Suba o backend: `cs serve` (token em `~/.config/canal-soberania/.api_token`)
2. No browser devtools: `localStorage.setItem("api_token", "<token>")`
3. Acesse `http://localhost:5173`

---

## routes/operacao/layout.tsx

Sub-nav horizontal com três abas: **Pipeline**, **Discover**, **Canais**. Envolve os filhos via `<Outlet />` de TanStack Router.

Detecção de rota ativa via `useRouterState({ select: s => s.location.pathname })` — necessário porque `useMatch` não resolve corretamente para rotas-filhas em contextos de layout. Navegação via `router.navigate({ to: path })`.

---

## routes/operacao/pipeline.tsx

Monitor de pipeline com controles de stage e log de eventos em tempo real.

### Grupos de stages

| Grupo | Stages |
|---|---|
| Triagem | discover, triage_metadata, triage_caption |
| Mídia | download, transcribe, triage_transcript |
| Produção | find_clips, edit, thumbnail, generate_metadata |
| Publicação | upload_youtube, upload_tiktok |

Cada stage tem um botão "▶" que chama `api.stages.run(name)`. Badge ao lado exibe `stagePendingCount(summary, name)` — pendentes por stage derivados de `GET /stats/summary` (poll 5s).

### Botões globais

- **Rodar tudo** → `api.stages.run("auto")`
- **Cancelar** → `api.stages.cancel()`
- **Resetar presos** → `api.stages.reset()`
- **Sync YouTube** → `api.stages.run("sync_youtube")`

### Log SSE virtualizado

`useSSE(event => { /* acumula entrada */ })` acumula eventos em `useRef<string[]>` (cap 1000). `useVirtualizer` de `@tanstack/react-virtual` renderiza apenas as linhas visíveis. Scroll automático ao final quando `filterText` está vazio. Botão **Clear** zera o buffer; input de filtro faz busca simples por `includes`.

---

## routes/operacao/discover.tsx

Form de discover ad-hoc + histórico de sessão.

- **Campos:** handle/URL do canal (obrigatório), janela em dias, máx. vídeos, switch "persistir canal no banco"
- **Submit:** `api.discover.adhoc(params)` → retorna 202 imediatamente; toast de confirmação
- **Histórico:** `useSSE(event => { if event.type === "discover_adhoc_done" → append })` — lista os últimos 50 runs da sessão com handle, quantidade inserida, flag persistido e horário

---

## routes/operacao/canais.tsx

CRUD de canais monitorados.

- Tabela com colunas: nome, handle, tema, peso, auto_publish, tolerância, ativo (switch inline)
- Switch inline chama `api.canais.toggleAtivo(id, !ativo)` + invalida `["canais"]`
- Botão "Novo canal" / ícone de edição abre `<Sheet>` lateral com form completo (todos os campos do schema `Canal`)
- `saveMutation`: chama `api.canais.create` (sem id preexistente) ou `api.canais.update`
- Excluir via `<AlertDialog>` de confirmação → `api.canais.remove`

**Campos do schema Canal:** `id` (slug, só na criação), `nome`, `handle`, `channel_url`, `tema_primario`, `peso` (0–1), `auto_publish`, `tolerancia_cortes` (baixa/media/alta), `nota`, `ativo`.

---

## routes/stats.tsx

Página de estatísticas com quatro seções.

### Cards

| Card | Fonte | Cálculo |
|---|---|---|
| Custo do mês | `GET /stats/costs` + `GET /stats/costs/detail` | `total_usd` + projeção linear (custo dos últimos 7 dias ÷ 7 × 30) |
| Clips publicados | `GET /stats/summary` | soma de `uploaded_youtube` + `scheduled_youtube` + `uploaded_tiktok` + `pending_tiktok_manual` |
| Throughput (clips/sem) | `GET /stats/throughput` | média de `clips_criados` nas últimas 4 semanas |
| Taxa de aprovação | `GET /stats/summary` | aprovados ÷ (aprovados + rejeitados) × 100 |

### Bar chart (recharts)

`ResponsiveContainer` + `BarChart` com dados de `GET /stats/throughput`. Três barras por semana: vídeos descobertos, clips criados, clips publicados. Eixo X: `semana` (formato `AAAA-SS`).

### Tabela por canal

Dados de `GET /stats/by-canal`. Colunas: canal_id, total vídeos, aprovados, clips gerados, publicados.

---

## routes/settings.tsx

Configurações do backend + preferências de UI.

### Seções

| Seção | O que contém |
|---|---|
| Aparência | Toggle de tema (Light/Dark/System) |
| Backend | Selects LLM_BACKEND, WHISPER_BACKEND, WHISPER_DEVICE; inputs Ollama URL e modelos |
| Alertas | ALERT_CHANNELS, TELEGRAM_CHAT_ID; campos SMTP |
| Pipeline | PIPELINE_LOOP_INTERVAL (número), switch DRY_RUN, select LOG_LEVEL |
| Importar .env | File picker → parse → filtrar → popular form para revisão |
| Atalhos | Cheatsheet estático dos atalhos de `shortcuts.ts` |

### Fluxo de save

1. `useQuery(["config"], api.config.get)` popula o form na montagem via `useEffect`
2. Qualquer edição marca `isDirty = true`
3. Botão "Salvar" (disabled quando não-dirty) chama `api.config.put(form)`
4. Response inclui `restart_required: true` → toast avisa "Reinicie o backend para aplicar"

### Importar .env

```ts
const reader = new FileReader();
reader.onload = (e) => {
  const text = e.target?.result as string;
  const parsed: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const m = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
    if (m && EDITABLE_KEYS.has(m[1])) parsed[m[1]] = m[2].trim();
  }
  setForm(prev => ({ ...prev, ...parsed }));
  toast.success(`${Object.keys(parsed).length} chaves importadas — revise e salve`);
};
reader.readAsText(file);
```

O form é populado para revisão; não há save automático ao importar.

---

## O que vem a seguir (Fase B restante)

### Onda 7 — Command palette + bulk ops

`CommandPalette.tsx` já está montado no layout com `cmdk` instalado. Implementar:
- Índice in-memory de vídeos + clipes + canais + ações nomeadas
- SSE atualiza índice incrementalmente
- Bulk approve/reject na Biblioteca (toolbar já presente, sem mutação ainda)

### Onda 8 — Cobertura de testes

- pytest coverage ≥ 90% no backend
- Vitest para hooks/componentes frontend
- Playwright E2E para fluxos críticos (inbox → clip-review → approve)

### Onda 9 — Eval de prompts

Dataset de 50 vídeos com ground truth → runner automático → comparação de resultados entre modelos e versões de prompt.

---

## Smoke checklist frontend

```bash
# 1. Sem erros de tipo
export PATH="$HOME/.local/node22/bin:$HOME/.local/share/pnpm/bin:$HOME/.cargo/bin:$PATH"
cd ui && pnpm tsc --noEmit

# 2. Backend rodando
cs serve &

# 3. Dev server
pnpm dev        # ou: pnpm tauri dev (se libs gtk instaladas)

# Inbox: items aparecem, J/K navega, A/R mutam e desaparecem da lista
# Biblioteca: busca filtra, clique em header ordena, checkbox → bulk toolbar
# ClipReview (/clip-review/<clip_id>): vídeo carrega, slider move, autosave tosta
# Operação/Pipeline: botões por stage, badge de pendentes, log SSE rolando
# Operação/Discover: form submit → toast, SSE → append histórico
# Operação/Canais: tabela, switch ativo, Sheet CRUD, AlertDialog excluir
# Stats: 4 cards + recharts bar chart + tabela por canal
# Settings: form populado, importar .env, salvar → toast restart
```
