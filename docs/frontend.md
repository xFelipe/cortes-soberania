# Frontend — Canal Soberania

Documentação da camada UI: arquitetura, padrões, como estender.

Gerado após conclusão da **Fase A** (Ondas 3–5). Próximas ondas estão em `proximas_tarefas.md`.

---

## Stack

| Peça | Versão | Papel |
|---|---|---|
| Tauri | 2.x | Shell nativo Linux/Windows, acesso a arquivo local |
| React | 19 | Renderização |
| Vite | 7 | Dev server e build |
| Tailwind | 4 (via `@tailwindcss/vite`) | Estilização — sem `tailwind.config.js` |
| shadcn/ui | 4.7 preset Radix/Nova | Componentes base (alert-dialog, badge, button, card, dialog, separator, sheet, tabs, tooltip) |
| radix-ui | 1.4 (pacote unificado) | Primitivos não-wrappados: Checkbox, ContextMenu, Slider |
| TanStack Router | 1.x | Roteamento tipado |
| TanStack Query | 5.x | Server state, cache, invalidação |
| TanStack Table | 8.x | Tabelas com sort/filter/pagination |
| sonner | 2.x | Toasts |
| cmdk | 1.x | Command palette (Ctrl+K) — implementado na Onda 7 |
| lucide-react | 1.x | Ícones |
| zod | 4.x | Validação de schema (disponível, usado na Onda 6+) |

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
│       ├── index.tsx         ← redirect / → /inbox
│       ├── inbox.tsx         ← fila de revisão (cards + J/K/A/R)
│       ├── biblioteca.tsx    ← tabela de vídeos e clipes (TanStack Table)
│       ├── clip-review.tsx   ← review detalhado de um clipe
│       ├── operacao.tsx      ← placeholder (Onda 6)
│       ├── stats.tsx         ← placeholder (Onda 6)
│       └── settings.tsx      ← tema toggle funcional
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
| `FaceCropData` | Resposta de `GET /clips/{id}/face-crop` |
| `ClipPatch` | Body de `PATCH /clips/{id}` |

### Métodos disponíveis

```ts
api.stats.summary()             // GET /stats/summary
api.stats.costs()               // GET /stats/costs
api.inbox.get()                 // GET /inbox
api.stages.run(name)            // POST /stages/{name}/run
api.stages.cancel()             // POST /pipeline/cancel
api.stages.reset()              // POST /pipeline/reset
api.videos.list(params?)        // GET /videos
api.videos.approve(video_id)    // POST /videos/{id}/approve
api.videos.reject(video_id)     // POST /videos/{id}/reject
api.clips.list(params?)         // GET /clips
api.clips.get(clip_id)          // GET /clips/{id}
api.clips.approve(clip_id)      // POST /clips/{id}/approve
api.clips.reject(clip_id)       // POST /clips/{id}/reject
api.clips.discard(clip_id)      // DELETE /clips/{id}
api.clips.patch(clip_id, data)  // PATCH /clips/{id}
api.clips.trim(id, start, end)  // POST /clips/{id}/trim
api.clips.faceCrop(clip_id)     // GET /clips/{id}/face-crop
api.clips.sourceVideoUrl(id)    // retorna string URL (não chama request)
```

`sourceVideoUrl` retorna uma URL direta (não passa por `request<T>`) porque precisa do `?token=` no query param — usada diretamente como `src` do `<video>`.

---

## lib/router.tsx — rotas

TanStack Router com rotas flat (sem aninhamento exceto pelo `rootRoute`):

| Path | Componente | Status |
|---|---|---|
| `/` | redirect → `/inbox` | ✅ |
| `/inbox` | `routes/inbox.tsx` | ✅ |
| `/biblioteca` | `routes/biblioteca.tsx` | ✅ |
| `/clip-review/$clipId` | `routes/clip-review.tsx` | ✅ |
| `/operacao` | `routes/operacao.tsx` | placeholder |
| `/stats` | `routes/stats.tsx` | placeholder |
| `/settings` | `routes/settings.tsx` | tema funcional |

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

`useSSE()` conecta ao `GET /events?token=<token>` via `EventSource` nativo.

Ao receber um evento:
- Qualquer `event_type` contendo `"clip"` → invalida `["clips"]` e `["inbox"]`
- Qualquer `event_type` contendo `"video"` → invalida `["videos"]` e `["inbox"]`
- Sempre invalida `["stats"]`

O SSE é montado em `RootLayout` (ou `StatusFooter`), portanto funciona em todas as rotas.

---

## lib/status-labels.ts — mapeamento de status

Single source of truth para labels e cores dos status em PT-BR.

```ts
VIDEO_STATUS_META: Record<VideoStatus, { label: string; color: string; active: boolean }>
CLIP_STATUS_META:  Record<ClipStatus,  { label: string; color: string }>
ACTIVE_VIDEO_STATUSES: Set<VideoStatus>  // statuses em progresso ativo
```

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

**Regra:** ao mutar qualquer vídeo/clipe, invalidar `["inbox"]` e `["stats"]` além da key específica.

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

`alert-dialog`, `badge`, `button`, `card`, `dialog`, `separator`, `sheet`, `tabs`, `tooltip`

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

## O que falta (Fase B — Onda 6+)

### Onda 6 — Operação + Stats + Settings

`routes/operacao.tsx`:
- Pipeline monitor: 12 stages com contagem de pendentes, log virtualizado
- Discover ad-hoc: form simples + histórico de runs
- CRUD de canais via `<Sheet>` (import já existe em `components/ui/sheet.tsx`)

`routes/stats.tsx`:
- 4 cards: custo+projeção, throughput, publicados, taxa aprovação
- Bar chart 4 semanas (instalar `recharts`)
- Tabela por canal

`routes/settings.tsx` (expandir):
- LLM_BACKEND / WHISPER_BACKEND toggles
- Loop interval
- Destinos de alerta
- Cheatsheet de atalhos (exibir todos os hooks de shortcuts.ts)

### Onda 7 — Command palette

`CommandPalette.tsx` já está montado no layout. Implementar:
- Índice in-memory de vídeos + clipes + canais + ações nomeadas
- SSE atualiza índice incrementalmente
- `cmdk` já está instalado

### Ligação Inbox → ClipReview

Atualmente o inbox não tem link para o ClipReview. A Onda 6 pode adicionar:
```tsx
// Em ClipCard (inbox.tsx), botão "Revisar":
<Button onClick={() => navigate({ to: "/clip-review/$clipId", params: { clipId: item.clip_id! } })}>
  Revisar
</Button>
```

---

## Smoke checklist frontend

```bash
# 1. Sem erros de tipo
cd ui && pnpm tsc --noEmit

# 2. Backend rodando
cs serve &

# 3. Dev server
pnpm dev        # ou: pnpm tauri dev (se libs gtk instaladas)

# Inbox: items aparecem, J/K navega, A/R mutam e desaparecem da lista
# Biblioteca: busca filtra, clique em header ordena, checkbox → bulk toolbar
# ClipReview (/clip-review/<clip_id>): vídeo carrega, slider move, autosave tosta
```
