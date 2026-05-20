import { useQueryClient, useQuery } from "@tanstack/react-query";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "cmdk";
import {
  CheckCircle2,
  Inbox,
  Library,
  Settings,
  BarChart2,
  Wrench,
  Play,
  XCircle,
  RefreshCw,
  PauseCircle,
  PlayCircle,
  Film,
  Video,
  Radio,
} from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useCommandIndex } from "@/lib/command-index";
import { api } from "@/lib/api";
import { router } from "@/lib/router";

interface Props {
  open: boolean;
  onClose: () => void;
}

function navigate(to: string, onClose: () => void) {
  void router.navigate({ to } as Parameters<typeof router.navigate>[0]);
  onClose();
}

export default function CommandPalette({ open, onClose }: Props) {
  const queryClient = useQueryClient();
  const index = useCommandIndex();

  const { data: loopState } = useQuery({
    queryKey: ["pipeline", "loop-state"],
    queryFn: api.pipeline.loopState,
    enabled: open,
    staleTime: 5_000,
  });
  const isPaused = loopState?.paused ?? false;

  const approvableClips = index.clips.filter((c) => c.status === "metadata_ready");

  function invalidateAfterAction() {
    void queryClient.invalidateQueries({ queryKey: ["clips"] });
    void queryClient.invalidateQueries({ queryKey: ["videos"] });
    void queryClient.invalidateQueries({ queryKey: ["inbox"] });
    void queryClient.invalidateQueries({ queryKey: ["stats"] });
  }

  async function handleApproveClip(id: string, label: string) {
    onClose();
    try {
      await api.clips.approve(id);
      toast.success(`Clipe aprovado: ${label}`);
      invalidateAfterAction();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro ao aprovar");
    }
  }

  async function handleRunPipeline() {
    onClose();
    try {
      await api.stages.run("auto");
      toast.success("Pipeline iniciado");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro ao iniciar pipeline");
    }
  }

  async function handleCancelPipeline() {
    onClose();
    try {
      await api.stages.cancel();
      toast.success("Cancelamento solicitado");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro");
    }
  }

  async function handleReset() {
    onClose();
    try {
      const r = await api.stages.reset();
      toast.success(`${r.reset_videos + r.reset_clips} item(s) resetados`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro");
    }
  }

  async function handlePauseLoop() {
    onClose();
    try {
      await api.pipeline.pause();
      toast.success("Pipeline loop pausado");
      void queryClient.invalidateQueries({ queryKey: ["pipeline", "loop-state"] });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro");
    }
  }

  async function handleResumeLoop() {
    onClose();
    try {
      await api.pipeline.resume();
      toast.success("Pipeline loop retomado");
      void queryClient.invalidateQueries({ queryKey: ["pipeline", "loop-state"] });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="p-0 max-w-xl overflow-hidden">
        <Command className="rounded-lg" shouldFilter>
          <CommandInput placeholder="Buscar ação, clipe, vídeo ou canal…" autoFocus />
          <CommandList className="max-h-[420px]">
            <CommandEmpty>Nenhum resultado encontrado.</CommandEmpty>

            {/* Navegação */}
            <CommandGroup heading="Navegar">
              <CommandItem keywords={["inbox", "fila"]} onSelect={() => navigate("/inbox", onClose)}>
                <Inbox size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Ir para Inbox
              </CommandItem>
              <CommandItem keywords={["biblioteca", "clipes", "videos"]} onSelect={() => navigate("/biblioteca", onClose)}>
                <Library size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Ir para Biblioteca
              </CommandItem>
              <CommandItem keywords={["operacao", "pipeline", "stages"]} onSelect={() => navigate("/operacao", onClose)}>
                <Wrench size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Ir para Operação
              </CommandItem>
              <CommandItem keywords={["stats", "estatisticas"]} onSelect={() => navigate("/stats", onClose)}>
                <BarChart2 size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Ir para Stats
              </CommandItem>
              <CommandItem keywords={["settings", "configuracoes"]} onSelect={() => navigate("/settings", onClose)}>
                <Settings size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Abrir Settings
              </CommandItem>
            </CommandGroup>

            <CommandSeparator />

            {/* Pipeline */}
            <CommandGroup heading="Pipeline">
              <CommandItem keywords={["rodar", "auto", "run"]} onSelect={() => void handleRunPipeline()}>
                <Play size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Rodar pipeline (auto)
              </CommandItem>
              <CommandItem keywords={["cancelar", "parar", "stop"]} onSelect={() => void handleCancelPipeline()}>
                <XCircle size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Cancelar pipeline
              </CommandItem>
              <CommandItem keywords={["resetar", "presos", "stuck"]} onSelect={() => void handleReset()}>
                <RefreshCw size={14} className="mr-2 shrink-0 text-muted-foreground" />
                Resetar itens presos
              </CommandItem>
              {isPaused ? (
                <CommandItem keywords={["retomar", "resume", "loop"]} onSelect={() => void handleResumeLoop()}>
                  <PlayCircle size={14} className="mr-2 shrink-0 text-muted-foreground" />
                  Retomar pipeline loop
                </CommandItem>
              ) : (
                <CommandItem keywords={["pausar", "pause", "loop"]} onSelect={() => void handlePauseLoop()}>
                  <PauseCircle size={14} className="mr-2 shrink-0 text-muted-foreground" />
                  Pausar pipeline loop
                </CommandItem>
              )}
            </CommandGroup>

            {/* Ações rápidas em clipes aprovados */}
            {approvableClips.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Aprovar clipes">
                  {approvableClips.slice(0, 8).map((clip) => {
                    const label = clip.hook ?? clip.title ?? clip.id;
                    return (
                      <CommandItem
                        key={clip.id}
                        keywords={[clip.id, clip.video_id, "aprovar", "approve"]}
                        onSelect={() => void handleApproveClip(clip.id, label)}
                      >
                        <CheckCircle2 size={14} className="mr-2 shrink-0 text-green-500" />
                        <span className="truncate max-w-[380px]">Aprovar: {label}</span>
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </>
            )}

            <CommandSeparator />

            {/* Clipes */}
            {index.clips.length > 0 && (
              <CommandGroup heading="Clipes">
                {index.clips.map((clip) => {
                  const label = clip.hook ?? clip.title ?? clip.id;
                  return (
                    <CommandItem
                      key={clip.id}
                      keywords={[clip.id, clip.video_id, clip.status]}
                      onSelect={() => {
                        void router.navigate({ to: "/clip-review/$clipId", params: { clipId: clip.id } });
                        onClose();
                      }}
                    >
                      <Film size={14} className="mr-2 shrink-0 text-muted-foreground" />
                      <span className="truncate max-w-[340px]">{label}</span>
                      <span className="ml-auto text-[11px] text-muted-foreground shrink-0">{clip.status}</span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            )}

            {/* Vídeos */}
            {index.videos.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Vídeos">
                  {index.videos.map((video) => (
                    <CommandItem
                      key={video.id}
                      keywords={[video.id, video.canal_id, video.status]}
                      onSelect={() => navigate("/biblioteca", onClose)}
                    >
                      <Video size={14} className="mr-2 shrink-0 text-muted-foreground" />
                      <span className="truncate max-w-[340px]">{video.title}</span>
                      <span className="ml-auto text-[11px] text-muted-foreground shrink-0">{video.canal_id}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}

            {/* Canais */}
            {index.canais.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Canais">
                  {index.canais.map((canal) => (
                    <CommandItem
                      key={canal.id}
                      keywords={[canal.id, canal.handle]}
                      onSelect={() => navigate("/operacao/canais", onClose)}
                    >
                      <Radio size={14} className="mr-2 shrink-0 text-muted-foreground" />
                      <span className="truncate max-w-[340px]">{canal.nome}</span>
                      <span className="ml-auto text-[11px] text-muted-foreground shrink-0">{canal.handle}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
