import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Clip } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/use-toast";

// ── instrucoes ────────────────────────────────────────────────────────────────

const STEPS = [
  "Abra o app TikTok e toque em "+" para novo vídeo.",
  "Selecione "Carregar" e escolha o arquivo MP4 abaixo.",
  "Cole o título e a descrição preparados abaixo.",
  "Adicione as hashtags ao final da legenda.",
  "Publique e volte aqui para marcar como enviado.",
];

// ── componente de item ────────────────────────────────────────────────────────

function TikTokItem({ clip }: { clip: Clip }) {
  const [tiktokId, setTiktokId] = useState("");
  const [expanded, setExpanded] = useState(false);
  const { toast } = useToast();
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => api.clips.markTikTokUploaded(clip.clip_id, tiktokId || undefined),
    onSuccess: () => {
      toast({ title: "Marcado como enviado", description: clip.title ?? clip.clip_id });
      qc.invalidateQueries({ queryKey: ["clips", "pending_tiktok_manual"] });
    },
    onError: () => toast({ title: "Erro ao marcar", variant: "destructive" }),
  });

  const title = clip.title ?? clip.hook ?? clip.clip_id;
  const description = clip.description ?? clip.payoff ?? "";
  const tags = Array.isArray(clip.tags) ? clip.tags : [];
  const hashtags = tags
    .slice(0, 5)
    .map((t) => `#${t.replace(/\s+/g, "")}`)
    .join(" ");

  const filename = clip.clip_path_vertical
    ? clip.clip_path_vertical.split("/").pop()
    : null;
  const filePath = clip.clip_path_vertical ?? "—";

  return (
    <div className="border rounded-lg p-4 space-y-3 bg-card">
      {/* cabeçalho */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium truncate">{title}</p>
          <p className="text-xs text-muted-foreground">{clip.clip_id}</p>
        </div>
        <Badge variant="outline" className="shrink-0 text-orange-600 border-orange-300">
          Fila TikTok
        </Badge>
      </div>

      {/* path do arquivo */}
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Arquivo para upload
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs bg-muted rounded px-2 py-1.5 truncate" title={filePath}>
            {filename ?? filePath}
          </code>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0"
            onClick={() => navigator.clipboard.writeText(filePath)}
          >
            Copiar path
          </Button>
        </div>
        <p className="text-xs text-muted-foreground break-all">{filePath}</p>
      </div>

      {/* conteúdo para colar */}
      <div>
        <button
          className="text-xs font-medium text-primary hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "▲ Ocultar legenda" : "▼ Ver título, descrição e hashtags"}
        </button>

        {expanded && (
          <div className="mt-2 space-y-2">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Título</p>
              <div className="flex items-start gap-2">
                <p className="flex-1 text-sm bg-muted rounded px-2 py-1.5">{title}</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => navigator.clipboard.writeText(title)}
                >
                  Copiar
                </Button>
              </div>
            </div>

            {description && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">Descrição</p>
                <div className="flex items-start gap-2">
                  <p className="flex-1 text-sm bg-muted rounded px-2 py-1.5 whitespace-pre-wrap">
                    {description}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0 self-start"
                    onClick={() => navigator.clipboard.writeText(description)}
                  >
                    Copiar
                  </Button>
                </div>
              </div>
            )}

            {hashtags && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">Hashtags</p>
                <div className="flex items-center gap-2">
                  <p className="flex-1 text-sm bg-muted rounded px-2 py-1.5">{hashtags}</p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() => navigator.clipboard.writeText(hashtags)}
                  >
                    Copiar
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* marcar como enviado */}
      <div className="flex items-center gap-2 pt-1 border-t">
        <Input
          placeholder="ID do TikTok (opcional)"
          className="h-8 text-xs"
          value={tiktokId}
          onChange={(e) => setTiktokId(e.target.value)}
        />
        <Button
          size="sm"
          className="shrink-0"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? "Salvando…" : "Marcar como enviado"}
        </Button>
      </div>
    </div>
  );
}

// ── página principal ──────────────────────────────────────────────────────────

export default function TikTokPage() {
  const { data: clips = [], isLoading } = useQuery({
    queryKey: ["clips", "pending_tiktok_manual"],
    queryFn: () => api.clips.list({ status: "pending_tiktok_manual" }),
    refetchInterval: 30_000,
  });

  return (
    <div className="p-4 space-y-6 max-w-2xl">
      {/* instrucoes */}
      <div className="rounded-lg border border-orange-200 bg-orange-50 dark:bg-orange-950/20 dark:border-orange-900 p-4">
        <p className="text-sm font-semibold mb-3">Como fazer o upload no TikTok</p>
        <ol className="space-y-1.5">
          {STEPS.map((step, i) => (
            <li key={i} className="flex gap-2 text-sm">
              <span className="shrink-0 font-mono text-orange-600 font-bold">{i + 1}.</span>
              <span className="text-muted-foreground">{step}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* fila */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">
            Fila de upload
            {clips.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {clips.length}
              </Badge>
            )}
          </p>
        </div>

        {isLoading && (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        )}

        {!isLoading && clips.length === 0 && (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm text-muted-foreground">
              Nenhum clipe aguardando upload no TikTok.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Clipes aparecem aqui após o stage <code>upload_tiktok</code> do pipeline.
            </p>
          </div>
        )}

        {clips.map((clip) => (
          <TikTokItem key={clip.clip_id} clip={clip} />
        ))}
      </div>
    </div>
  );
}
