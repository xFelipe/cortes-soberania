import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/sse";

interface RunRecord {
  handle: string;
  inserted: number;
  persisted: boolean;
  ts: string;
}

export default function DiscoverPage() {
  const [handle, setHandle] = useState("");
  const [persist, setPersist] = useState(false);
  const [janelaDias, setJanelaDias] = useState("");
  const [maxVideos, setMaxVideos] = useState("");
  const [history, setHistory] = useState<RunRecord[]>([]);

  useSSE((event) => {
    if (event.type === "discover_adhoc_done" && event.data) {
      const d = event.data as { handle?: string; inserted?: number; persisted?: boolean };
      setHistory((prev) => [
        {
          handle: d.handle ?? "?",
          inserted: d.inserted ?? 0,
          persisted: d.persisted ?? false,
          ts: new Date().toLocaleTimeString("pt-BR"),
        },
        ...prev,
      ].slice(0, 50));
    }
  });

  const mutation = useMutation({
    mutationFn: () =>
      api.discover.adhoc({
        channel_url_or_handle: handle.trim(),
        persist,
        janela_dias: janelaDias ? parseInt(janelaDias) : null,
        max_videos: maxVideos ? parseInt(maxVideos) : null,
      }),
    onSuccess: () => toast.success(`Discover iniciado para ${handle}`),
    onError: (e) => toast.error(String(e)),
  });

  return (
    <div className="p-4 max-w-lg space-y-6">
      <div className="space-y-4">
        <h3 className="font-medium">Discover ad-hoc</h3>

        <div className="space-y-1.5">
          <Label htmlFor="handle">Handle ou URL do canal</Label>
          <Input
            id="handle"
            placeholder="@NomeDoCanal ou https://youtube.com/@canal"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="janela">Janela (dias)</Label>
            <Input
              id="janela"
              type="number"
              placeholder="7"
              value={janelaDias}
              onChange={(e) => setJanelaDias(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="max">Máx. vídeos</Label>
            <Input
              id="max"
              type="number"
              placeholder="20"
              value={maxVideos}
              onChange={(e) => setMaxVideos(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Switch
            id="persist"
            checked={persist}
            onCheckedChange={setPersist}
          />
          <Label htmlFor="persist">Persistir canal no banco</Label>
        </div>

        <Button
          onClick={() => mutation.mutate()}
          disabled={!handle.trim() || mutation.isPending}
        >
          Iniciar discover
        </Button>
      </div>

      {/* Histórico da sessão */}
      {history.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
            Histórico da sessão
          </p>
          <div className="space-y-1">
            {history.map((r, i) => (
              <div key={i} className="flex items-center justify-between text-sm border rounded px-3 py-1.5">
                <span className="font-mono">{r.handle}</span>
                <div className="flex items-center gap-3 text-muted-foreground text-xs">
                  <span>{r.inserted} inseridos</span>
                  {r.persisted && <span className="text-green-600">persistido</span>}
                  <span>{r.ts}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
