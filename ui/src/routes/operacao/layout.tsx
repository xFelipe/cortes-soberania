import { Outlet, useRouter, useRouterState } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";

const TABS = [
  { path: "/operacao/pipeline", label: "Pipeline" },
  { path: "/operacao/discover", label: "Discover" },
  { path: "/operacao/canais", label: "Canais" },
  { path: "/operacao/tiktok", label: "TikTok" },
] as const;

export default function OperacaoLayout() {
  const router = useRouter();
  const location = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1 px-4 pt-4 border-b pb-0">
        {TABS.map(({ path, label }) => (
          <Button
            key={path}
            variant="ghost"
            size="sm"
            className={`rounded-b-none border-b-2 ${
              location === path
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground"
            }`}
            onClick={() => router.navigate({ to: path })}
          >
            {label}
          </Button>
        ))}
      </div>
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  );
}
