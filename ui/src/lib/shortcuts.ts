import { useEffect } from "react";
import { router } from "./router";

const ROUTE_MAP: Record<string, string> = {
  "1": "/inbox",
  "2": "/biblioteca",
  "3": "/operacao",
  "4": "/stats",
  "5": "/settings",
};

export function useGlobalShortcuts(onCommandPalette: () => void) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!e.ctrlKey) return;

      const route = ROUTE_MAP[e.key];
      if (route) {
        e.preventDefault();
        void router.navigate({ to: route });
        return;
      }

      if (e.key === "k") {
        e.preventDefault();
        onCommandPalette();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCommandPalette]);
}
