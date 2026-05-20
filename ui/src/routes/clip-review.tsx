import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronLeft, CheckCircle2, XCircle, Trash2, Loader2 } from "lucide-react";
import { Slider } from "radix-ui";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { api, type ClipPatch, getToken, API_URL } from "@/lib/api";
import { useClipReviewShortcuts } from "@/lib/shortcuts";

// ── Canvas overlay: renders 9:16 crop mask over full-width video ──────────────

interface CropOverlayProps {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  cropX: number;
  cropWidth: number;
  sourceWidth: number;
  sourceHeight: number;
}

function CropOverlay({ videoRef, cropX, cropWidth, sourceWidth, sourceHeight }: CropOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    function draw() {
      if (!canvas || !video) return;
      const displayW = video.clientWidth;
      const displayH = video.clientHeight;
      canvas.width = displayW;
      canvas.height = displayH;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Scale crop coords to display size
      const scaleX = displayW / (sourceWidth || 1280);
      const scaleY = displayH / (sourceHeight || 720);
      const scale = Math.min(scaleX, scaleY);

      const displayCropX = cropX * scale + (displayW - sourceWidth * scale) / 2;
      const displayCropW = cropWidth * scale;

      ctx.clearRect(0, 0, displayW, displayH);

      // Dark mask outside crop
      ctx.fillStyle = "rgba(0,0,0,0.55)";
      ctx.fillRect(0, 0, displayCropX, displayH);
      ctx.fillRect(displayCropX + displayCropW, 0, displayW - displayCropX - displayCropW, displayH);

      // Bright border on crop
      ctx.strokeStyle = "rgba(255,255,255,0.8)";
      ctx.lineWidth = 2;
      ctx.strokeRect(displayCropX + 1, 1, displayCropW - 2, displayH - 2);
    }

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(video);
    return () => ro.disconnect();
  }, [videoRef, cropX, cropWidth, sourceWidth, sourceHeight]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}

// ── Duration formatter ────────────────────────────────────────────────────────

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ClipReviewPage() {
  const { clipId } = useParams({ from: "/clip-review/$clipId" });
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: clip, isLoading, isError } = useQuery({
    queryKey: ["clip", clipId],
    queryFn: () => api.clips.get(clipId),
  });

  const { data: cropData } = useQuery({
    queryKey: ["clip-face-crop", clipId],
    queryFn: () => api.clips.faceCrop(clipId),
    retry: false,
    staleTime: Infinity,
  });

  // ── Player state ─────────────────────────────────────────────────────────
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);

  // ── In/Out marks (start with clip's stored values) ───────────────────────
  const [inPoint, setInPoint] = useState(0);
  const [outPoint, setOutPoint] = useState(60);

  useEffect(() => {
    if (clip) {
      setInPoint(clip.start_s);
      setOutPoint(clip.end_s);
    }
  }, [clip?.clip_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Form state ───────────────────────────────────────────────────────────
  const [hook, setHook] = useState("");
  const [scoreViral, setScoreViral] = useState<number | "">(5);
  const [notas, setNotas] = useState("");
  const [formInitialized, setFormInitialized] = useState(false);

  useEffect(() => {
    if (clip && !formInitialized) {
      setHook(clip.hook ?? "");
      setScoreViral(clip.score_viral ?? 5);
      setNotas("");
      setFormInitialized(true);
    }
  }, [clip, formInitialized]);

  // ── Autosave debounce ────────────────────────────────────────────────────
  const patchMutation = useMutation({
    mutationFn: (data: ClipPatch) => api.clips.patch(clipId, data),
    onSuccess: () => toast.success("Salvo automaticamente", { duration: 1500 }),
    onError: (e: Error) => toast.error(`Erro ao salvar: ${e.message}`),
  });

  useEffect(() => {
    if (!formInitialized) return;
    const t = setTimeout(() => {
      patchMutation.mutate({
        hook: hook || null,
        score_viral: typeof scoreViral === "number" ? scoreViral : null,
      });
    }, 500);
    return () => clearTimeout(t);
  }, [hook, scoreViral]); // eslint-disable-line react-hooks/exhaustive-deps

  // Autosave trim when in/out change
  const trimMutation = useMutation({
    mutationFn: ({ s, e }: { s: number; e: number }) => api.clips.trim(clipId, s, e),
    onSuccess: () => toast.success("Trim salvo", { duration: 1500 }),
    onError: (e: Error) => toast.error(`Erro trim: ${e.message}`),
  });

  useEffect(() => {
    if (!formInitialized) return;
    const t = setTimeout(() => {
      trimMutation.mutate({ s: inPoint, e: outPoint });
    }, 500);
    return () => clearTimeout(t);
  }, [inPoint, outPoint]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Video events ─────────────────────────────────────────────────────────
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime);
    const onDur = () => setDuration(v.duration || 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onDur);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onDur);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, []);

  // ── Loop A↔B ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const check = () => {
      if (v.currentTime >= outPoint) {
        v.currentTime = inPoint;
      }
    };
    v.addEventListener("timeupdate", check);
    return () => v.removeEventListener("timeupdate", check);
  }, [inPoint, outPoint]);

  // ── Video src with auth token ─────────────────────────────────────────────
  const [videoSrc, setVideoSrc] = useState<string>("");
  useEffect(() => {
    void getToken().then((token) => {
      setVideoSrc(`${API_URL}/clips/${clipId}/source-video?token=${token}`);
    });
  }, [clipId]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const approveMutation = useMutation({
    mutationFn: () => api.clips.approve(clipId),
    onSuccess: async () => {
      toast.success("Clipe aprovado — upload iniciado");
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["clips"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
      // Navigate to next item in inbox
      const inbox = await api.inbox.get();
      const next = inbox.items.find((i) => i.clip_id && i.clip_id !== clipId);
      if (next?.clip_id) {
        void navigate({ to: "/clip-review/$clipId", params: { clipId: next.clip_id } });
      } else {
        void navigate({ to: "/inbox" });
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const rejectMutation = useMutation({
    mutationFn: () => api.clips.reject(clipId),
    onSuccess: () => {
      toast.success("Clipe rejeitado");
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["clips"] });
      void navigate({ to: "/inbox" });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const discardMutation = useMutation({
    mutationFn: () => api.clips.discard(clipId),
    onSuccess: () => {
      toast.success("Clipe excluído permanentemente");
      void queryClient.invalidateQueries({ queryKey: ["clips"] });
      void navigate({ to: "/inbox" });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // ── Shortcut callbacks ────────────────────────────────────────────────────
  const handleSetIn = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    const t = v.currentTime;
    setInPoint(Math.min(t, outPoint - 1));
  }, [outPoint]);

  const handleSetOut = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    const t = v.currentTime;
    setOutPoint(Math.max(t, inPoint + 1));
  }, [inPoint]);

  const handlePlayPause = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  }, []);

  const handleApprove = useCallback(() => {
    approveMutation.mutate();
  }, [approveMutation]);

  const handleReject = useCallback(() => {
    rejectMutation.mutate();
  }, [rejectMutation]);

  useClipReviewShortcuts({
    enabled: !isLoading && !isError,
    onSetIn: handleSetIn,
    onSetOut: handleSetOut,
    onPlayPause: handlePlayPause,
    onApprove: handleApprove,
    onReject: handleReject,
  });

  // ── Render ────────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-muted-foreground">
        <Loader2 size={16} className="animate-spin" />
        <span className="text-sm">Carregando…</span>
      </div>
    );
  }

  if (isError || !clip) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-destructive">Clipe não encontrado</p>
        <Button variant="outline" size="sm" onClick={() => void navigate({ to: "/inbox" })}>
          Voltar ao Inbox
        </Button>
      </div>
    );
  }

  const effectiveCrop = cropData ?? {
    crop_x: 0,
    crop_width: 270,
    source_width: 1280,
    source_height: 720,
  };

  const sliderMax = duration || clip.end_s + 10;
  const isBusy = approveMutation.isPending || rejectMutation.isPending || discardMutation.isPending;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 border-b px-5 py-2.5 text-sm">
        <button
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => void navigate({ to: "/inbox" })}
        >
          <ChevronLeft size={14} />
          Inbox
        </button>
        <span className="text-muted-foreground">/</span>
        <span className="font-medium truncate max-w-[260px]">
          {clip.hook ?? clip.title ?? clip.clip_id}
        </span>
      </div>

      {/* Main 2-column layout */}
      <div className="flex flex-1 min-h-0 gap-0">
        {/* Left: player + slider */}
        <div className="flex flex-1 flex-col min-w-0 border-r p-4 gap-3">
          {/* Video player + canvas overlay */}
          <div className="relative w-full flex-1 min-h-0 bg-black rounded-md overflow-hidden">
            {videoSrc ? (
              <video
                ref={videoRef}
                src={videoSrc}
                className="h-full w-full object-contain"
                controls={false}
                onClick={handlePlayPause}
                onDoubleClick={handlePlayPause}
                style={{ cursor: "pointer" }}
              />
            ) : (
              <div className="flex h-full items-center justify-center">
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            )}
            {cropData && (
              <CropOverlay
                videoRef={videoRef}
                cropX={effectiveCrop.crop_x}
                cropWidth={effectiveCrop.crop_width}
                sourceWidth={effectiveCrop.source_width}
                sourceHeight={effectiveCrop.source_height}
              />
            )}
            {/* Play/pause overlay hint */}
            <div className="absolute bottom-2 left-2 rounded bg-black/60 px-2 py-0.5 text-[11px] text-white/80">
              {fmt(currentTime)} / {fmt(sliderMax)}
              {playing ? "  ▶" : "  ⏸"}
            </div>
          </div>

          {/* In/Out dual-thumb slider */}
          <div className="flex flex-col gap-1">
            <Slider.Root
              className="relative flex h-5 w-full touch-none select-none items-center"
              value={[inPoint, outPoint]}
              min={0}
              max={sliderMax}
              step={0.1}
              onValueChange={([a, b]: [number, number]) => {
                setInPoint(a);
                setOutPoint(b);
              }}
            >
              <Slider.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-muted">
                <Slider.Range className="absolute h-full bg-primary" />
              </Slider.Track>
              <Slider.Thumb
                className="block h-4 w-4 rounded-full border-2 border-primary bg-background shadow transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
                aria-label="In point"
              />
              <Slider.Thumb
                className="block h-4 w-4 rounded-full border-2 border-primary bg-background shadow transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
                aria-label="Out point"
              />
            </Slider.Root>
            <div className="flex justify-between text-[11px] text-muted-foreground">
              <span>In: {fmt(inPoint)} — [ define início</span>
              <span>Out: {fmt(outPoint)} — ] define fim</span>
            </div>
          </div>

          {/* Current time scrubber */}
          {duration > 0 && (
            <Slider.Root
              className="relative flex h-4 w-full touch-none select-none items-center"
              value={[currentTime]}
              min={0}
              max={duration}
              step={0.05}
              onValueChange={([v]: [number]) => {
                const vid = videoRef.current;
                if (vid) vid.currentTime = v;
              }}
            >
              <Slider.Track className="relative h-1 w-full grow overflow-hidden rounded-full bg-muted">
                <Slider.Range className="absolute h-full bg-muted-foreground/60" />
              </Slider.Track>
              <Slider.Thumb
                className="block h-3 w-3 rounded-full border border-muted-foreground bg-muted-foreground shadow focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label="Current position"
              />
            </Slider.Root>
          )}

          <p className="text-center text-[11px] text-muted-foreground">
            Space play/pause · [ in · ] out · A aprovar · R rejeitar
          </p>
        </div>

        {/* Right: form + actions */}
        <div className="flex w-80 shrink-0 flex-col gap-4 overflow-y-auto p-5">
          {/* Hook */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">Hook</label>
            <textarea
              value={hook}
              onChange={(e) => setHook(e.target.value)}
              placeholder="Frase de abertura chamativa…"
              rows={4}
              className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Score viral */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">
              Score Viral
              <span className="ml-2 text-muted-foreground font-normal">
                {typeof scoreViral === "number" ? `${scoreViral}/10` : "—"}
              </span>
            </label>
            <Slider.Root
              className="relative flex h-5 w-full touch-none select-none items-center"
              value={[typeof scoreViral === "number" ? scoreViral : 5]}
              min={1}
              max={10}
              step={1}
              onValueChange={([v]: [number]) => setScoreViral(v)}
            >
              <Slider.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-muted">
                <Slider.Range className="absolute h-full bg-orange-500" />
              </Slider.Track>
              <Slider.Thumb
                className="block h-4 w-4 rounded-full border-2 border-orange-500 bg-background shadow focus-visible:outline-none"
                aria-label="Score viral"
              />
            </Slider.Root>
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>1</span><span>5</span><span>10</span>
            </div>
          </div>

          {/* In/Out numeric inputs */}
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium">In (s)</label>
              <input
                type="number"
                value={inPoint.toFixed(1)}
                min={0}
                max={outPoint - 1}
                step={0.1}
                onChange={(e) => setInPoint(Number(e.target.value))}
                className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium">Out (s)</label>
              <input
                type="number"
                value={outPoint.toFixed(1)}
                min={inPoint + 1}
                step={0.1}
                onChange={(e) => setOutPoint(Number(e.target.value))}
                className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>Duração: {fmt(outPoint - inPoint)}</span>
          </div>

          {/* Notas */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">Notas</label>
            <textarea
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
              placeholder="Observações internas…"
              rows={3}
              className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <div className="mt-auto flex flex-col gap-2 pt-2 border-t">
            <Button
              className="w-full gap-2"
              onClick={handleApprove}
              disabled={isBusy || clip.status !== "metadata_ready"}
            >
              {approveMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <CheckCircle2 size={14} />
              )}
              Aprovar e próximo
            </Button>

            <Button
              variant="outline"
              className="w-full gap-2 text-destructive hover:text-destructive"
              onClick={handleReject}
              disabled={isBusy}
            >
              <XCircle size={14} />
              Rejeitar
            </Button>

            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="ghost"
                  className="w-full gap-2 text-muted-foreground hover:text-destructive"
                  disabled={isBusy}
                >
                  <Trash2 size={14} />
                  Excluir permanentemente
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Excluir clipe?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Esta ação é irreversível. O clipe e todos os seus metadados serão
                    removidos do banco de dados.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    onClick={() => discardMutation.mutate()}
                  >
                    Excluir
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>

          {clip.status !== "metadata_ready" && (
            <p className="text-[11px] text-muted-foreground text-center">
              Status: {clip.status} — aprovação disponível somente em metadata_ready
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
