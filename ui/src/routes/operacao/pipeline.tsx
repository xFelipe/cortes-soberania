import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef, useState, useEffect } from "react";
import { toast } from "sonner";
import { Play, Square, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/sse";
import { stagePendingCount } from "@/lib/status-labels";

interface LogEntry {
  id: number;
  ts: string;
  type: string;
  text: string;
}

const STAGE_GROUPS = [
  {
    label: "Triagem",
    stages: ["discover", "triage_metadata", "triage_caption"],
  },
  {
    label: "Mídia",
    stages: ["download", "transcribe", "triage_transcript"],
  },
  {
    label: "Produção",
    stages: ["find_clips", "edit", "thumbnail", "generate_metadata"],
  },
  {
    label: "Publicação",
    stages: ["upload_youtube", "upload_tiktok"],
  },
] as const;

const STAGE_LABELS: Record<string, string> = {
  discover: "Discover",
  triage_metadata: "Triagem Metadata",
  triage_caption: "Triagem Caption",
  download: "Download",
  transcribe: "Transcrever",
  triage_transcript: "Triagem Transcript",
  find_clips: "Encontrar Cortes",
  edit: "Editar",
  thumbnail: "Thumbnail",
  generate_metadata: "Gerar Metadados",
  upload_youtube: "Upload YouTube",
  upload_tiktok: "Upload TikTok",
  sync_youtube: "Sync YouTube",
};

export default function PipelinePage() {
  const qc = useQueryClient();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState("");
  const logIdRef = useRef(0);
  const parentRef = useRef<HTMLDivElement>(null);

  const { data: summary = {} } = useQuery({
    queryKey: ["stats", "summary"],
    queryFn: api.stats.summary,
    refetchInterval: 5000,
  });

  useSSE((event) => {
    const entry: LogEntry = {
      id: logIdRef.current++,
      ts: new Date().toLocaleTimeString("pt-BR"),
      type: event.type,
      text: JSON.stringify(event.data),
    };
    setLogs((prev) => {
      const next = [...prev, entry];
      return next.length > 1000 ? next.slice(-1000) : next;
    });
    qc.invalidateQueries({ queryKey: ["stats", "summary"] });
  });

  const filteredLogs = filter
    ? logs.filter((l) => l.text.toLowerCase().includes(filter.toLowerCase()) || l.type.includes(filter))
    : logs;

  const rowVirtualizer = useVirtualizer({
    count: filteredLogs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 22,
    overscan: 10,
  });

  useEffect(() => {
    if (parentRef.current && !filter) {
      parentRef.current.scrollTop = parentRef.current.scrollHeight;
    }
  }, [logs.length, filter]);

  const runMutation = useMutation({
    mutationFn: (name: string) => api.stages.run(name),
    onSuccess: (_, name) => {
      toast.success(`Stage ${name} iniciado`);
      qc.invalidateQueries({ queryKey: ["stats", "summary"] });
    },
    onError: (e) => toast.error(String(e)),
  });

  const cancelMutation = useMutation({
    mutationFn: api.stages.cancel,
    onSuccess: () => toast.info("Pipeline cancelado"),
    onError: (e) => toast.error(String(e)),
  });

  const resetMutation = useMutation({
    mutationFn: api.stages.reset,
    onSuccess: (r) => toast.success(`Reset: ${r.reset_videos}v + ${r.reset_clips}c itens liberados`),
    onError: (e) => toast.error(String(e)),
  });

  return (
    <div className="flex flex-col gap-4 p-4 h-full">
      {/* Cabeçalho de controle global */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button size="sm" onClick={() => runMutation.mutate("auto")}>
          <Play className="w-3 h-3 mr-1" /> Rodar tudo
        </Button>
        <Button size="sm" variant="outline" onClick={() => cancelMutation.mutate()}>
          <Square className="w-3 h-3 mr-1" /> Cancelar
        </Button>
        <Button size="sm" variant="outline" onClick={() => resetMutation.mutate()}>
          <RotateCcw className="w-3 h-3 mr-1" /> Resetar presos
        </Button>
        <Button size="sm" variant="outline" onClick={() => runMutation.mutate("sync_youtube")}>
          Sync YouTube
        </Button>
      </div>

      {/* Grupos de stages */}
      <div className="grid grid-cols-2 gap-3">
        {STAGE_GROUPS.map((group) => (
          <div key={group.label} className="border rounded-lg p-3">
            <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
              {group.label}
            </p>
            <div className="space-y-1">
              {group.stages.map((stage) => {
                const pending = stagePendingCount(summary, stage);
                return (
                  <div key={stage} className="flex items-center justify-between gap-2">
                    <span className="text-sm truncate">{STAGE_LABELS[stage] ?? stage}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      {pending > 0 && (
                        <Badge variant="secondary" className="text-xs px-1 py-0 h-5">
                          {pending}
                        </Badge>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 w-6 p-0"
                        onClick={() => runMutation.mutate(stage)}
                        disabled={runMutation.isPending}
                      >
                        <Play className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Log virtualizado */}
      <div className="flex-1 flex flex-col min-h-0 border rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/30">
          <span className="text-xs font-medium">Log de eventos</span>
          <Input
            className="h-6 text-xs flex-1"
            placeholder="Filtrar…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2"
            onClick={() => setLogs([])}
          >
            <Trash2 className="w-3 h-3" />
          </Button>
        </div>
        <div
          ref={parentRef}
          className="flex-1 overflow-auto font-mono text-xs"
          style={{ overflowAnchor: "none" }}
        >
          <div
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              position: "relative",
            }}
          >
            {rowVirtualizer.getVirtualItems().map((vItem) => {
              const entry = filteredLogs[vItem.index];
              return (
                <div
                  key={entry.id}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: `${vItem.size}px`,
                    transform: `translateY(${vItem.start}px)`,
                  }}
                  className="flex gap-2 px-3 items-center hover:bg-muted/20"
                >
                  <span className="text-muted-foreground shrink-0">{entry.ts}</span>
                  <span className="text-primary shrink-0">{entry.type}</span>
                  <span className="truncate text-muted-foreground">{entry.text}</span>
                </div>
              );
            })}
          </div>
          {filteredLogs.length === 0 && (
            <p className="text-center text-muted-foreground py-8 text-xs">
              Aguardando eventos do pipeline…
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
