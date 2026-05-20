import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Settings } from "lucide-react";
import { useSSE } from "@/lib/sse";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

function SSEDot({ status }: { status: "connecting" | "open" | "closed" }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        status === "open" && "bg-green-500",
        status === "connecting" && "bg-yellow-400 animate-pulse",
        status === "closed" && "bg-red-500"
      )}
      title={status}
    />
  );
}

export default function StatusFooter() {
  const sseStatus = useSSE();
  const { data: costs } = useQuery({
    queryKey: ["stats", "costs"],
    queryFn: () => api.stats.costs(),
    refetchInterval: 60_000,
  });

  return (
    <footer className="col-span-2 flex items-center justify-between border-t bg-background px-3 text-xs text-muted-foreground h-7">
      <div className="flex items-center gap-1.5">
        <SSEDot status={sseStatus} />
        <span>{sseStatus === "open" ? "conectado" : sseStatus === "connecting" ? "conectando…" : "desconectado"}</span>
      </div>

      <div className="flex items-center gap-3">
        <span>
          {costs !== undefined
            ? `$${costs.total_usd.toFixed(2)} este mês`
            : "—"}
        </span>
        <Link to="/settings" className="hover:text-foreground transition-colors">
          <Settings size={12} />
        </Link>
      </div>
    </footer>
  );
}
