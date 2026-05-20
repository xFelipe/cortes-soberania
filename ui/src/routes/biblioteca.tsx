import React from "react";
import {
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
  type ColumnFiltersState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  XCircle,
  Trash2,
  ExternalLink,
  Copy,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  LayoutGrid,
  List,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
} from "lucide-react";
import { ContextMenu, Checkbox } from "radix-ui";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { api, type Video, type Clip } from "@/lib/api";
import {
  VIDEO_STATUS_META,
  CLIP_STATUS_META,
  type VideoStatus,
  type ClipStatus,
} from "@/lib/status-labels";
import { cn } from "@/lib/utils";

// ── Status badge ─────────────────────────────────────────────────────────────

function StatusChip({ status, type }: { status: string; type: "video" | "clip" }) {
  const meta =
    type === "clip"
      ? CLIP_STATUS_META[status as ClipStatus]
      : VIDEO_STATUS_META[status as VideoStatus];
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium leading-none"
      style={{ backgroundColor: `${meta?.color ?? "#555"}22`, color: meta?.color ?? "#555" }}
    >
      {meta?.label ?? status}
    </span>
  );
}

// ── Filter chips ──────────────────────────────────────────────────────────────

function FilterChips<S extends string>({
  statuses,
  active,
  meta,
  onChange,
}: {
  statuses: S[];
  active: S | null;
  meta: Record<S, { label: string; color: string }>;
  onChange: (s: S | null) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <button
        onClick={() => onChange(null)}
        className={cn(
          "rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors",
          active === null
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border text-muted-foreground hover:border-foreground/40"
        )}
      >
        Todos
      </button>
      {statuses.map((s) => (
        <button
          key={s}
          onClick={() => onChange(active === s ? null : s)}
          className={cn(
            "rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors",
            active === s
              ? "border-primary bg-primary text-primary-foreground"
              : "border-border text-muted-foreground hover:border-foreground/40"
          )}
          style={active === s ? {} : { borderColor: `${meta[s]?.color ?? "#555"}55` }}
        >
          {meta[s]?.label ?? s}
        </button>
      ))}
    </div>
  );
}

// ── Sort icon ─────────────────────────────────────────────────────────────────

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (!sorted) return <ArrowUpDown size={13} className="text-muted-foreground/50" />;
  return sorted === "asc" ? <ArrowUp size={13} /> : <ArrowDown size={13} />;
}

// ── Bulk toolbar ──────────────────────────────────────────────────────────────

function BulkToolbar({
  count,
  onApprove,
  onReject,
  onDiscard,
  onExport,
  onClear,
  type,
}: {
  count: number;
  onApprove?: () => void;
  onReject: () => void;
  onDiscard?: () => void;
  onExport: () => void;
  onClear: () => void;
  type: "video" | "clip";
}) {
  return (
    <div className="sticky bottom-0 z-10 flex items-center gap-2 border-t bg-background/95 px-4 py-2.5 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <span className="text-sm font-medium">
        {count} {type === "clip" ? "clipe" : "vídeo"}
        {count > 1 ? "s" : ""} selecionado{count > 1 ? "s" : ""}
      </span>
      <div className="flex gap-1.5 ml-auto">
        {onApprove && (
          <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={onApprove}>
            <CheckCircle2 size={12} />
            Aprovar
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="h-7 gap-1 text-xs text-destructive hover:text-destructive"
          onClick={onReject}
        >
          <XCircle size={12} />
          Rejeitar
        </Button>
        {onDiscard && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 text-xs text-destructive hover:text-destructive"
            onClick={onDiscard}
          >
            <Trash2 size={12} />
            Excluir
          </Button>
        )}
        <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs" onClick={onExport}>
          <ClipboardList size={12} />
          Exportar lista
        </Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onClear}>
          Limpar
        </Button>
      </div>
    </div>
  );
}

// ── Context menu wrapper ──────────────────────────────────────────────────────

function RowContextMenu({
  children,
  onApprove,
  onReject,
  onDiscard,
  youtubeId,
  itemId,
}: {
  children: React.ReactNode;
  onApprove?: () => void;
  onReject?: () => void;
  onDiscard?: () => void;
  youtubeId?: string | null;
  itemId: string;
}) {
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger asChild>{children}</ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Content
          className="z-50 min-w-[160px] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {onApprove && (
            <ContextMenu.Item
              className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none hover:bg-accent hover:text-accent-foreground"
              onSelect={onApprove}
            >
              <CheckCircle2 size={13} />
              Aprovar
            </ContextMenu.Item>
          )}
          {onReject && (
            <ContextMenu.Item
              className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none hover:bg-accent hover:text-accent-foreground"
              onSelect={onReject}
            >
              <XCircle size={13} />
              Rejeitar
            </ContextMenu.Item>
          )}
          {(onApprove || onReject) && <ContextMenu.Separator className="my-1 h-px bg-muted" />}
          {youtubeId && (
            <ContextMenu.Item
              className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none hover:bg-accent hover:text-accent-foreground"
              onSelect={() => window.open(`https://youtube.com/watch?v=${youtubeId}`, "_blank")}
            >
              <ExternalLink size={13} />
              Abrir no YouTube
            </ContextMenu.Item>
          )}
          <ContextMenu.Item
            className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none hover:bg-accent hover:text-accent-foreground"
            onSelect={() => void navigator.clipboard.writeText(itemId)}
          >
            <Copy size={13} />
            Copiar ID
          </ContextMenu.Item>
          {onDiscard && (
            <>
              <ContextMenu.Separator className="my-1 h-px bg-muted" />
              <ContextMenu.Item
                className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-destructive outline-none select-none hover:bg-destructive/10"
                onSelect={onDiscard}
              >
                <Trash2 size={13} />
                Excluir
              </ContextMenu.Item>
            </>
          )}
        </ContextMenu.Content>
      </ContextMenu.Portal>
    </ContextMenu.Root>
  );
}

// ── Videos tab ────────────────────────────────────────────────────────────────

const VIDEO_STATUSES = Object.keys(VIDEO_STATUS_META) as VideoStatus[];

function VideosTab() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<VideoStatus | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const { data: videos = [], isLoading } = useQuery({
    queryKey: ["videos"],
    queryFn: () => api.videos.list({ limit: 500 }),
    refetchInterval: 30_000,
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) => api.videos.approve(id),
    onSuccess: () => {
      toast.success("Vídeo aprovado");
      void queryClient.invalidateQueries({ queryKey: ["videos"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => api.videos.reject(id),
    onSuccess: () => {
      toast.success("Vídeo rejeitado");
      void queryClient.invalidateQueries({ queryKey: ["videos"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const columns = useMemo<ColumnDef<Video>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <Checkbox.Root
            checked={
              table.getIsAllPageRowsSelected()
                ? true
                : table.getIsSomePageRowsSelected()
                ? "indeterminate"
                : false
            }
            onCheckedChange={(v: boolean | "indeterminate") => table.toggleAllPageRowsSelected(!!v)}
            className="flex h-4 w-4 items-center justify-center rounded border border-input bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary"
          >
            <Checkbox.Indicator>
              <svg viewBox="0 0 10 10" className="h-3 w-3 fill-primary-foreground">
                <path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Checkbox.Indicator>
          </Checkbox.Root>
        ),
        cell: ({ row }) => (
          <Checkbox.Root
            checked={row.getIsSelected()}
            onCheckedChange={(v: boolean | "indeterminate") => row.toggleSelected(!!v)}
            onClick={(e: React.MouseEvent) => e.stopPropagation()}
            className="flex h-4 w-4 items-center justify-center rounded border border-input bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary"
          >
            <Checkbox.Indicator>
              <svg viewBox="0 0 10 10" className="h-3 w-3 fill-primary-foreground">
                <path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Checkbox.Indicator>
          </Checkbox.Root>
        ),
        size: 40,
      },
      {
        accessorKey: "title",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 text-xs font-medium hover:text-foreground"
            onClick={() => column.toggleSorting()}
          >
            Título
            <SortIcon sorted={column.getIsSorted()} />
          </button>
        ),
        cell: ({ row }) => (
          <span className="line-clamp-1 max-w-[380px] text-sm">{row.original.title}</span>
        ),
      },
      {
        accessorKey: "canal_id",
        header: "Canal",
        cell: ({ getValue }) => (
          <span className="text-sm text-muted-foreground">{getValue<string>()}</span>
        ),
        size: 120,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => (
          <StatusChip status={getValue<string>()} type="video" />
        ),
        size: 160,
      },
      {
        accessorKey: "score_triage",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 text-xs font-medium hover:text-foreground"
            onClick={() => column.toggleSorting()}
          >
            Score
            <SortIcon sorted={column.getIsSorted()} />
          </button>
        ),
        cell: ({ getValue }) => {
          const v = getValue<number | null>();
          return <span className="text-sm tabular-nums">{v ?? "—"}</span>;
        },
        size: 70,
      },
      {
        accessorKey: "published_at",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 text-xs font-medium hover:text-foreground"
            onClick={() => column.toggleSorting()}
          >
            Publicado
            <SortIcon sorted={column.getIsSorted()} />
          </button>
        ),
        cell: ({ getValue }) => (
          <span className="text-sm tabular-nums text-muted-foreground">
            {getValue<string>()?.slice(0, 10) ?? "—"}
          </span>
        ),
        size: 100,
      },
    ],
    []
  );

  const filteredData = useMemo(() => {
    let d = videos;
    if (statusFilter) d = d.filter((v) => v.status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      d = d.filter(
        (v) =>
          v.title.toLowerCase().includes(q) ||
          v.canal_id.toLowerCase().includes(q) ||
          v.video_id.toLowerCase().includes(q)
      );
    }
    return d;
  }, [videos, statusFilter, search]);

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, rowSelection, columnFilters },
    enableRowSelection: true,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 50 } },
  });

  const selectedIds = table
    .getSelectedRowModel()
    .rows.map((r) => r.original.video_id);
  const hasSelection = selectedIds.length > 0;

  if (isLoading) {
    return <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">Carregando…</div>;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-col gap-3 px-1 pb-3">
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por título, canal ou ID…"
            className="h-8 w-64 rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <span className="text-xs text-muted-foreground ml-auto">
            {filteredData.length} vídeo{filteredData.length !== 1 ? "s" : ""}
          </span>
        </div>
        <FilterChips
          statuses={VIDEO_STATUSES}
          active={statusFilter}
          meta={VIDEO_STATUS_META}
          onChange={setStatusFilter}
        />
      </div>

      <div className="flex-1 overflow-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    style={{ width: h.column.columnDef.size }}
                    className="px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <RowContextMenu
                key={row.id}
                itemId={row.original.video_id}
                onApprove={() => approveMutation.mutate(row.original.video_id)}
                onReject={() => rejectMutation.mutate(row.original.video_id)}
              >
                <tr
                  className={cn(
                    "border-b last:border-0 transition-colors hover:bg-muted/40",
                    row.getIsSelected() && "bg-muted/60"
                  )}
                  onClick={() => row.toggleSelected()}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-3 py-2"
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              </RowContextMenu>
            ))}
            {table.getRowModel().rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-10 text-center text-sm text-muted-foreground">
                  Nenhum vídeo encontrado
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between px-1 pt-2">
        <span className="text-xs text-muted-foreground">
          Página {table.getState().pagination.pageIndex + 1} de {table.getPageCount()}
        </span>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <ChevronLeft size={14} />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <ChevronRight size={14} />
          </Button>
        </div>
      </div>

      {hasSelection && (
        <BulkToolbar
          count={selectedIds.length}
          type="video"
          onApprove={() => {
            const ids = selectedIds;
            setRowSelection({});
            void Promise.allSettled(ids.map((id) => api.videos.approve(id))).then((results) => {
              const ok = results.filter((r) => r.status === "fulfilled").length;
              const fail = results.length - ok;
              if (fail === 0) toast.success(`${ok} vídeo${ok > 1 ? "s" : ""} aprovado${ok > 1 ? "s" : ""}`);
              else toast.warning(`${ok} aprovado${ok !== 1 ? "s" : ""}, ${fail} falhou`);
              void queryClient.invalidateQueries({ queryKey: ["videos"] });
              void queryClient.invalidateQueries({ queryKey: ["stats"] });
            });
          }}
          onReject={() => {
            const ids = selectedIds;
            setRowSelection({});
            void Promise.allSettled(ids.map((id) => api.videos.reject(id))).then((results) => {
              const ok = results.filter((r) => r.status === "fulfilled").length;
              const fail = results.length - ok;
              if (fail === 0) toast.success(`${ok} vídeo${ok > 1 ? "s" : ""} rejeitado${ok > 1 ? "s" : ""}`);
              else toast.warning(`${ok} rejeitado${ok !== 1 ? "s" : ""}, ${fail} falhou`);
              void queryClient.invalidateQueries({ queryKey: ["videos"] });
              void queryClient.invalidateQueries({ queryKey: ["stats"] });
            });
          }}
          onExport={() => {
            const selected = table.getSelectedRowModel().rows.map((r) => r.original);
            const header = "video_id,status,title,canal_id,score_triage";
            const rows = selected.map((v) =>
              [v.video_id, v.status, `"${(v.title ?? "").replace(/"/g, '""')}"`, v.canal_id, v.score_triage ?? ""].join(",")
            );
            void navigator.clipboard.writeText([header, ...rows].join("\n")).then(() => {
              toast.success(`${selected.length} item${selected.length > 1 ? "s" : ""} copiado${selected.length > 1 ? "s" : ""} (CSV)`);
            });
          }}
          onClear={() => setRowSelection({})}
        />
      )}
    </div>
  );
}

// ── Clips tab ─────────────────────────────────────────────────────────────────

const CLIP_STATUSES = Object.keys(CLIP_STATUS_META) as ClipStatus[];

function ClipGrid({ clips }: { clips: Clip[] }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
      {clips.map((clip) => (
        <div key={clip.clip_id} className="group rounded-lg border bg-card overflow-hidden">
          <div className="aspect-[9/16] bg-muted flex items-center justify-center text-[11px] text-muted-foreground">
            {clip.thumb_path ? (
              <img src={clip.thumb_path} alt="" className="h-full w-full object-cover" />
            ) : (
              "sem thumb"
            )}
          </div>
          <div className="p-2">
            <StatusChip status={clip.status} type="clip" />
            <p className="mt-1 line-clamp-2 text-[12px] leading-snug">
              {clip.hook ?? clip.title ?? clip.clip_id}
            </p>
            {clip.score_viral !== null && clip.score_viral !== undefined && (
              <p className="mt-0.5 text-[11px] text-muted-foreground">viral {clip.score_viral}/10</p>
            )}
          </div>
        </div>
      ))}
      {clips.length === 0 && (
        <p className="col-span-full py-10 text-center text-sm text-muted-foreground">
          Nenhum clipe encontrado
        </p>
      )}
    </div>
  );
}

function ClipsTab() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ClipStatus | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [viewMode, setViewMode] = useState<"table" | "grid">("table");

  const { data: clips = [], isLoading } = useQuery({
    queryKey: ["clips"],
    queryFn: () => api.clips.list({ limit: 500 }),
    refetchInterval: 30_000,
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) => api.clips.approve(id),
    onSuccess: () => {
      toast.success("Clipe aprovado — upload iniciado");
      void queryClient.invalidateQueries({ queryKey: ["clips"] });
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => api.clips.reject(id),
    onSuccess: () => {
      toast.success("Clipe rejeitado");
      void queryClient.invalidateQueries({ queryKey: ["clips"] });
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const discardMutation = useMutation({
    mutationFn: (id: string) => api.clips.discard(id),
    onSuccess: () => {
      toast.success("Clipe excluído");
      void queryClient.invalidateQueries({ queryKey: ["clips"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const columns = useMemo<ColumnDef<Clip>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <Checkbox.Root
            checked={
              table.getIsAllPageRowsSelected()
                ? true
                : table.getIsSomePageRowsSelected()
                ? "indeterminate"
                : false
            }
            onCheckedChange={(v: boolean | "indeterminate") => table.toggleAllPageRowsSelected(!!v)}
            className="flex h-4 w-4 items-center justify-center rounded border border-input bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary"
          >
            <Checkbox.Indicator>
              <svg viewBox="0 0 10 10" className="h-3 w-3 fill-primary-foreground">
                <path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Checkbox.Indicator>
          </Checkbox.Root>
        ),
        cell: ({ row }) => (
          <Checkbox.Root
            checked={row.getIsSelected()}
            onCheckedChange={(v: boolean | "indeterminate") => row.toggleSelected(!!v)}
            onClick={(e: React.MouseEvent) => e.stopPropagation()}
            className="flex h-4 w-4 items-center justify-center rounded border border-input bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary"
          >
            <Checkbox.Indicator>
              <svg viewBox="0 0 10 10" className="h-3 w-3 fill-primary-foreground">
                <path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Checkbox.Indicator>
          </Checkbox.Root>
        ),
        size: 40,
      },
      {
        accessorKey: "hook",
        header: "Hook",
        cell: ({ row }) => (
          <span className="line-clamp-1 max-w-[300px] text-sm">
            {row.original.hook ?? row.original.title ?? <span className="text-muted-foreground italic">sem hook</span>}
          </span>
        ),
      },
      {
        accessorKey: "video_id",
        header: "Vídeo",
        cell: ({ getValue }) => (
          <span className="font-mono text-[11px] text-muted-foreground">{getValue<string>()}</span>
        ),
        size: 110,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => <StatusChip status={getValue<string>()} type="clip" />,
        size: 160,
      },
      {
        accessorKey: "score_viral",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 text-xs font-medium hover:text-foreground"
            onClick={() => column.toggleSorting()}
          >
            Viral
            <SortIcon sorted={column.getIsSorted()} />
          </button>
        ),
        cell: ({ getValue }) => {
          const v = getValue<number | null>();
          return <span className="text-sm tabular-nums">{v ?? "—"}</span>;
        },
        size: 65,
      },
      {
        id: "duration",
        header: "Dur.",
        accessorFn: (r) => r.end_s - r.start_s,
        cell: ({ getValue }) => (
          <span className="text-sm tabular-nums text-muted-foreground">
            {Math.round(getValue<number>())}s
          </span>
        ),
        size: 65,
      },
      {
        accessorKey: "created_at",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 text-xs font-medium hover:text-foreground"
            onClick={() => column.toggleSorting()}
          >
            Criado
            <SortIcon sorted={column.getIsSorted()} />
          </button>
        ),
        cell: ({ getValue }) => (
          <span className="text-sm tabular-nums text-muted-foreground">
            {(getValue<string | null>() ?? "").slice(0, 10) || "—"}
          </span>
        ),
        size: 100,
      },
    ],
    []
  );

  const filteredData = useMemo(() => {
    let d = clips;
    if (statusFilter) d = d.filter((c) => c.status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      d = d.filter(
        (c) =>
          (c.hook ?? "").toLowerCase().includes(q) ||
          (c.title ?? "").toLowerCase().includes(q) ||
          c.video_id.toLowerCase().includes(q) ||
          c.clip_id.toLowerCase().includes(q)
      );
    }
    return d;
  }, [clips, statusFilter, search]);

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, rowSelection },
    enableRowSelection: true,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 50 } },
  });

  const selectedIds = table.getSelectedRowModel().rows.map((r) => r.original.clip_id);
  const hasSelection = selectedIds.length > 0;

  if (isLoading) {
    return <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">Carregando…</div>;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-col gap-3 px-1 pb-3">
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por hook, título, vídeo ou ID…"
            className="h-8 w-72 rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <div className="flex gap-1 ml-auto">
            <Button
              variant={viewMode === "table" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setViewMode("table")}
            >
              <List size={14} />
            </Button>
            <Button
              variant={viewMode === "grid" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setViewMode("grid")}
            >
              <LayoutGrid size={14} />
            </Button>
            <span className="ml-2 text-xs text-muted-foreground self-center">
              {filteredData.length} clipe{filteredData.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
        <FilterChips
          statuses={CLIP_STATUSES}
          active={statusFilter}
          meta={CLIP_STATUS_META}
          onChange={setStatusFilter}
        />
      </div>

      {viewMode === "grid" ? (
        <div className="flex-1 overflow-auto">
          <ClipGrid clips={filteredData} />
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((h) => (
                      <th
                        key={h.id}
                        style={{ width: h.column.columnDef.size }}
                        className="px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <RowContextMenu
                    key={row.id}
                    itemId={row.original.clip_id}
                    youtubeId={row.original.youtube_id}
                    onApprove={
                      row.original.status === "metadata_ready"
                        ? () => approveMutation.mutate(row.original.clip_id)
                        : undefined
                    }
                    onReject={() => rejectMutation.mutate(row.original.clip_id)}
                    onDiscard={() => discardMutation.mutate(row.original.clip_id)}
                  >
                    <tr
                      className={cn(
                        "border-b last:border-0 transition-colors hover:bg-muted/40",
                        row.getIsSelected() && "bg-muted/60"
                      )}
                      onClick={() => row.toggleSelected()}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-3 py-2">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  </RowContextMenu>
                ))}
                {table.getRowModel().rows.length === 0 && (
                  <tr>
                    <td colSpan={columns.length} className="py-10 text-center text-sm text-muted-foreground">
                      Nenhum clipe encontrado
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-1 pt-2">
            <span className="text-xs text-muted-foreground">
              Página {table.getState().pagination.pageIndex + 1} de {table.getPageCount()}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => table.previousPage()}
                disabled={!table.getCanPreviousPage()}
              >
                <ChevronLeft size={14} />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => table.nextPage()}
                disabled={!table.getCanNextPage()}
              >
                <ChevronRight size={14} />
              </Button>
            </div>
          </div>
        </>
      )}

      {hasSelection && (
        <BulkToolbar
          count={selectedIds.length}
          type="clip"
          onApprove={() => {
            const ids = selectedIds;
            setRowSelection({});
            void Promise.allSettled(ids.map((id) => api.clips.approve(id))).then((results) => {
              const ok = results.filter((r) => r.status === "fulfilled").length;
              const fail = results.length - ok;
              if (fail === 0) toast.success(`${ok} clipe${ok > 1 ? "s" : ""} aprovado${ok > 1 ? "s" : ""} — upload iniciado`);
              else toast.warning(`${ok} aprovado${ok !== 1 ? "s" : ""}, ${fail} falhou`);
              void queryClient.invalidateQueries({ queryKey: ["clips"] });
              void queryClient.invalidateQueries({ queryKey: ["inbox"] });
              void queryClient.invalidateQueries({ queryKey: ["stats"] });
            });
          }}
          onReject={() => {
            const ids = selectedIds;
            setRowSelection({});
            void Promise.allSettled(ids.map((id) => api.clips.reject(id))).then((results) => {
              const ok = results.filter((r) => r.status === "fulfilled").length;
              const fail = results.length - ok;
              if (fail === 0) toast.success(`${ok} clipe${ok > 1 ? "s" : ""} rejeitado${ok > 1 ? "s" : ""}`);
              else toast.warning(`${ok} rejeitado${ok !== 1 ? "s" : ""}, ${fail} falhou`);
              void queryClient.invalidateQueries({ queryKey: ["clips"] });
              void queryClient.invalidateQueries({ queryKey: ["inbox"] });
              void queryClient.invalidateQueries({ queryKey: ["stats"] });
            });
          }}
          onDiscard={() => {
            const ids = selectedIds;
            setRowSelection({});
            void Promise.allSettled(ids.map((id) => api.clips.discard(id))).then((results) => {
              const ok = results.filter((r) => r.status === "fulfilled").length;
              const fail = results.length - ok;
              if (fail === 0) toast.success(`${ok} clipe${ok > 1 ? "s" : ""} excluído${ok > 1 ? "s" : ""}`);
              else toast.warning(`${ok} excluído${ok !== 1 ? "s" : ""}, ${fail} falhou`);
              void queryClient.invalidateQueries({ queryKey: ["clips"] });
              void queryClient.invalidateQueries({ queryKey: ["stats"] });
            });
          }}
          onExport={() => {
            const selected = table.getSelectedRowModel().rows.map((r) => r.original);
            const header = "clip_id,status,hook,video_id,score_viral";
            const rows = selected.map((c) =>
              [c.clip_id, c.status, `"${(c.hook ?? c.title ?? "").replace(/"/g, '""')}"`, c.video_id, c.score_viral ?? ""].join(",")
            );
            void navigator.clipboard.writeText([header, ...rows].join("\n")).then(() => {
              toast.success(`${selected.length} item${selected.length > 1 ? "s" : ""} copiado${selected.length > 1 ? "s" : ""} (CSV)`);
            });
          }}
          onClear={() => setRowSelection({})}
        />
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BibliotecaPage() {
  return (
    <div className="flex h-full flex-col p-6">
      <Tabs defaultValue="clips" className="flex flex-1 flex-col min-h-0">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-sm font-semibold">Biblioteca</h1>
          <TabsList className="h-8">
            <TabsTrigger value="clips" className="text-xs px-3 h-6">Clipes</TabsTrigger>
            <TabsTrigger value="videos" className="text-xs px-3 h-6">Vídeos</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="clips" className="flex-1 mt-0 min-h-0">
          <ClipsTab />
        </TabsContent>
        <TabsContent value="videos" className="flex-1 mt-0 min-h-0">
          <VideosTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
