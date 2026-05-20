import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, XCircle, Clock, AlertTriangle, Inbox } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type InboxItem } from "@/lib/api";
import { useInboxShortcuts } from "@/lib/shortcuts";
import { CLIP_STATUS_META, VIDEO_STATUS_META } from "@/lib/status-labels";
import { cn } from "@/lib/utils";

function formatDuration(start_s?: number, end_s?: number): string {
  if (start_s === undefined || end_s === undefined) return "";
  const dur = Math.round(end_s - start_s);
  return `${dur}s`;
}

function priorityIcon(priority: number) {
  if (priority === 1) return <CheckCircle2 size={14} className="text-orange-500" />;
  if (priority === 2) return <Clock size={14} className="text-blue-400" />;
  return <AlertTriangle size={14} className="text-destructive" />;
}

function priorityLabel(priority: number, type: "clip" | "video"): string {
  if (type === "clip") return "Revisão pendente";
  if (priority === 2) return "Aguarda triagem";
  return "Erro — atenção";
}

function StatusBadge({ status, type }: { status: string; type: "clip" | "video" }) {
  const meta =
    type === "clip"
      ? CLIP_STATUS_META[status as keyof typeof CLIP_STATUS_META]
      : VIDEO_STATUS_META[status as keyof typeof VIDEO_STATUS_META];

  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium leading-none"
      style={{ backgroundColor: `${meta?.color ?? "#555"}22`, color: meta?.color ?? "#555" }}
    >
      {meta?.label ?? status}
    </span>
  );
}

interface InboxCardProps {
  item: InboxItem;
  focused: boolean;
  onApprove: () => void;
  onReject: () => void;
  approving: boolean;
  rejecting: boolean;
}

function ClipCard({ item, focused, onApprove, onReject, approving, rejecting }: InboxCardProps) {
  return (
    <div
      className={cn(
        "group rounded-lg border bg-card p-4 transition-all",
        focused
          ? "border-primary ring-1 ring-primary shadow-sm"
          : "border-border hover:border-border/80"
      )}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">{priorityIcon(item.priority)}</div>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {priorityLabel(item.priority, "clip")}
            </span>
            {item.status && <StatusBadge status={item.status} type="clip" />}
            {item.score_viral !== undefined && item.score_viral !== null && (
              <span className="text-[11px] text-muted-foreground">
                viral {item.score_viral}/10
              </span>
            )}
            {item.start_s !== undefined && item.end_s !== undefined && (
              <span className="text-[11px] text-muted-foreground">
                {formatDuration(item.start_s, item.end_s)}
              </span>
            )}
            <span className="font-mono text-[11px] text-muted-foreground/60">
              {item.clip_id}
            </span>
          </div>
          {item.hook ? (
            <p className="text-sm leading-snug">{item.hook}</p>
          ) : (
            <p className="text-sm text-muted-foreground italic">sem hook gerado</p>
          )}
        </div>
        <div className="flex shrink-0 gap-1.5 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 data-[focused=true]:opacity-100"
          data-focused={focused}>
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1 text-xs"
            onClick={onApprove}
            disabled={approving || rejecting}
          >
            <CheckCircle2 size={12} />
            Aprovar
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 text-xs text-destructive hover:text-destructive"
            onClick={onReject}
            disabled={approving || rejecting}
          >
            <XCircle size={12} />
            Rejeitar
          </Button>
        </div>
      </div>
    </div>
  );
}

function VideoCard({ item, focused, onReject, approving, rejecting }: Omit<InboxCardProps, "onApprove">) {
  return (
    <div
      className={cn(
        "group rounded-lg border bg-card p-4 transition-all",
        focused
          ? "border-primary ring-1 ring-primary shadow-sm"
          : "border-border hover:border-border/80"
      )}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">{priorityIcon(item.priority)}</div>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {priorityLabel(item.priority, "video")}
            </span>
            {item.status && <StatusBadge status={item.status} type="video" />}
            {item.canal_id && (
              <span className="text-[11px] text-muted-foreground">{item.canal_id}</span>
            )}
          </div>
          <p className="text-sm leading-snug">
            {item.title ?? item.video_id ?? "—"}
          </p>
        </div>
        {item.priority === 3 && (
          <div
            className="flex shrink-0 gap-1.5 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 data-[focused=true]:opacity-100"
            data-focused={focused}
          >
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1 text-xs text-destructive hover:text-destructive"
              onClick={onReject}
              disabled={approving || rejecting}
            >
              <XCircle size={12} />
              Ignorar
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function InboxPage() {
  const queryClient = useQueryClient();
  const [focusedIndex, setFocusedIndex] = useState(0);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  const { data, isLoading } = useQuery({
    queryKey: ["inbox"],
    queryFn: () => api.inbox.get(),
    refetchInterval: 15_000,
  });

  const items = data?.items ?? [];

  const approveMutation = useMutation<{ status: string }, Error, InboxItem>({
    mutationFn: (item: InboxItem) =>
      item.type === "clip"
        ? api.clips.approve(item.clip_id!)
        : api.videos.approve(item.video_id!),
    onSuccess: (_, item) => {
      toast.success(item.type === "clip" ? "Clipe aprovado — upload iniciado" : "Vídeo aprovado");
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const rejectMutation = useMutation<{ status: string }, Error, InboxItem>({
    mutationFn: (item: InboxItem) =>
      item.type === "clip"
        ? api.clips.reject(item.clip_id!)
        : api.videos.reject(item.video_id!),
    onSuccess: (_, item) => {
      toast.success(item.type === "clip" ? "Clipe rejeitado" : "Vídeo rejeitado");
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleApprove = useCallback(() => {
    const item = items[focusedIndex];
    if (item && !approveMutation.isPending && !rejectMutation.isPending) {
      approveMutation.mutate(item);
    }
  }, [items, focusedIndex, approveMutation, rejectMutation]);

  const handleReject = useCallback(() => {
    const item = items[focusedIndex];
    if (item && !approveMutation.isPending && !rejectMutation.isPending) {
      rejectMutation.mutate(item);
    }
  }, [items, focusedIndex, approveMutation, rejectMutation]);

  useInboxShortcuts({
    enabled: items.length > 0,
    onNext: useCallback(() => setFocusedIndex((i) => Math.min(i + 1, items.length - 1)), [items.length]),
    onPrev: useCallback(() => setFocusedIndex((i) => Math.max(i - 1, 0)), []),
    onApprove: handleApprove,
    onReject: handleReject,
  });

  // Scroll focused card into view
  useEffect(() => {
    cardRefs.current[focusedIndex]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusedIndex]);

  // Clamp index when items shrink after mutation
  useEffect(() => {
    if (items.length > 0) setFocusedIndex((i) => Math.min(i, items.length - 1));
  }, [items.length]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="text-sm text-muted-foreground">Carregando…</span>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <Inbox size={40} className="text-muted-foreground/40" />
        <p className="text-base font-medium">Inbox vazia</p>
        <p className="text-sm text-muted-foreground">
          Nenhum clipe ou vídeo aguardando atenção. Pipeline rodando.
        </p>
      </div>
    );
  }

  const clipCount = items.filter((i) => i.type === "clip").length;
  const videoCount = items.filter((i) => i.type === "video").length;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold">Inbox</h1>
          <div className="flex gap-1.5">
            {clipCount > 0 && (
              <Badge variant="destructive" className="text-[11px]">
                {clipCount} clipe{clipCount > 1 ? "s" : ""}
              </Badge>
            )}
            {videoCount > 0 && (
              <Badge variant="outline" className="text-[11px]">
                {videoCount} vídeo{videoCount > 1 ? "s" : ""}
              </Badge>
            )}
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">J/K nav · A aprovar · R rejeitar</p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-2xl space-y-2">
          {items.map((item, idx) => {
            const id = item.clip_id ?? item.video_id ?? String(idx);
            const focused = idx === focusedIndex;
            const approving =
              approveMutation.isPending &&
              (approveMutation.variables?.clip_id === item.clip_id ||
                approveMutation.variables?.video_id === item.video_id);
            const rejecting =
              rejectMutation.isPending &&
              (rejectMutation.variables?.clip_id === item.clip_id ||
                rejectMutation.variables?.video_id === item.video_id);

            return (
              <div
                key={id}
                ref={(el) => { cardRefs.current[idx] = el; }}
                onClick={() => setFocusedIndex(idx)}
              >
                {item.type === "clip" ? (
                  <ClipCard
                    item={item}
                    focused={focused}
                    onApprove={() => approveMutation.mutate(item)}
                    onReject={() => rejectMutation.mutate(item)}
                    approving={approving}
                    rejecting={rejecting}
                  />
                ) : (
                  <VideoCard
                    item={item}
                    focused={focused}
                    onReject={() => rejectMutation.mutate(item)}
                    approving={approving}
                    rejecting={rejecting}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
