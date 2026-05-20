import { useState, useCallback } from "react";
import { Outlet } from "@tanstack/react-router";
import Sidebar from "./Sidebar";
import StatusFooter from "./StatusFooter";
import CommandPalette from "./CommandPalette";
import { useGlobalShortcuts } from "@/lib/shortcuts";

export default function RootLayout() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);

  useGlobalShortcuts(openPalette);

  return (
    <>
      <div className="grid grid-cols-[3.75rem_1fr] grid-rows-[1fr_1.75rem] h-screen overflow-hidden">
        <Sidebar />
        <main className="overflow-auto">
          <Outlet />
        </main>
        <StatusFooter />
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}
