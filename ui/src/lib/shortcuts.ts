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

export interface ClipReviewShortcutHandlers {
  onSetIn: () => void;
  onSetOut: () => void;
  onPlayPause: () => void;
  onApprove: () => void;
  onReject: () => void;
  enabled: boolean;
}

export function useClipReviewShortcuts({
  onSetIn,
  onSetOut,
  onPlayPause,
  onApprove,
  onReject,
  enabled,
}: ClipReviewShortcutHandlers) {
  useEffect(() => {
    if (!enabled) return;

    function handleKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      // Allow Space in non-textarea/input; block [ ] A R in inputs
      if (tag === "TEXTAREA" || (tag === "INPUT" && e.key !== " ")) return;

      switch (e.key) {
        case "[":
          e.preventDefault();
          onSetIn();
          break;
        case "]":
          e.preventDefault();
          onSetOut();
          break;
        case " ":
          if (tag !== "TEXTAREA" && tag !== "INPUT") {
            e.preventDefault();
            onPlayPause();
          }
          break;
        case "a":
        case "A":
          if (tag !== "TEXTAREA" && tag !== "INPUT") onApprove();
          break;
        case "r":
        case "R":
          if (tag !== "TEXTAREA" && tag !== "INPUT") onReject();
          break;
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [enabled, onSetIn, onSetOut, onPlayPause, onApprove, onReject]);
}

export interface InboxShortcutHandlers {
  onNext: () => void;
  onPrev: () => void;
  onApprove: () => void;
  onReject: () => void;
  enabled: boolean;
}

export function useInboxShortcuts({
  onNext,
  onPrev,
  onApprove,
  onReject,
  enabled,
}: InboxShortcutHandlers) {
  useEffect(() => {
    if (!enabled) return;

    function handleKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      switch (e.key) {
        case "j":
        case "J":
          e.preventDefault();
          onNext();
          break;
        case "k":
        case "K":
          e.preventDefault();
          onPrev();
          break;
        case "a":
        case "A":
          onApprove();
          break;
        case "r":
        case "R":
          onReject();
          break;
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [enabled, onNext, onPrev, onApprove, onReject]);
}
