import { useQuery } from "@tanstack/react-query";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Home,
  Library,
  Settings2,
  BarChart3,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { api, type StatsSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badgeKey?: keyof StatsSummary;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/inbox", label: "Inbox", icon: Home, badgeKey: "metadata_ready" },
  { to: "/biblioteca", label: "Biblioteca", icon: Library },
  { to: "/operacao", label: "Operação", icon: Settings2 },
  { to: "/stats", label: "Stats", icon: BarChart3 },
  { to: "/settings", label: "Config", icon: Settings },
];

export default function Sidebar() {
  const { location } = useRouterState();
  const { data: summary } = useQuery({
    queryKey: ["stats", "summary"],
    queryFn: () => api.stats.summary(),
    refetchInterval: 30_000,
  });

  return (
    <TooltipProvider delayDuration={300}>
      <nav className="flex flex-col items-center gap-1 py-2 border-r bg-background h-full">
        {NAV_ITEMS.map(({ to, label, icon: Icon, badgeKey }) => {
          const active = location.pathname.startsWith(to);
          const count = badgeKey && summary ? (summary[badgeKey] ?? 0) : undefined;

          return (
            <Tooltip key={to}>
              <TooltipTrigger asChild>
                <Link
                  to={to}
                  className={cn(
                    "relative flex h-12 w-12 items-center justify-center rounded-lg transition-colors",
                    "hover:bg-accent hover:text-accent-foreground",
                    active && "bg-accent text-accent-foreground border-l-2 border-primary rounded-l-none"
                  )}
                >
                  <Icon size={20} />
                  {count !== undefined && count > 0 && (
                    <Badge
                      variant="destructive"
                      className="absolute -top-1 -right-1 h-4 min-w-4 px-1 text-[10px] leading-none"
                    >
                      {count > 99 ? "99+" : count}
                    </Badge>
                  )}
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p>{label}</p>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </nav>
    </TooltipProvider>
  );
}
