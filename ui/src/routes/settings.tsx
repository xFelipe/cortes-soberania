import { useRef, useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useTheme } from "@/lib/theme";
import { api, type ConfigValues } from "@/lib/api";

// Chaves que o endpoint /config aceita (espelha EDITABLE_KEYS no backend)
const EDITABLE_KEYS = new Set([
  "LLM_BACKEND", "WHISPER_BACKEND", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE",
  "OLLAMA_BASE_URL", "OLLAMA_MODEL_TRIAGE", "OLLAMA_MODEL_DEEP",
  "ALERT_CHANNELS", "ALERT_STUCK_THRESHOLD", "TELEGRAM_CHAT_ID",
  "SMTP_HOST", "SMTP_PORT", "SMTP_FROM", "SMTP_TO",
  "LOG_LEVEL", "DRY_RUN", "PIPELINE_LOOP_INTERVAL",
]);

const SHORTCUTS = [
  { keys: "Ctrl+1..5", desc: "Navegar entre seções" },
  { keys: "Ctrl+K", desc: "Abrir command palette" },
  { keys: "J / K", desc: "Navegar itens na Inbox" },
  { keys: "A", desc: "Aprovar item selecionado" },
  { keys: "R", desc: "Rejeitar item selecionado" },
  { keys: "[ / ]", desc: "Ajustar ponto in/out no ClipReview" },
  { keys: "Espaço", desc: "Play/pause no ClipReview" },
];

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: serverConfig, isLoading } = useQuery({
    queryKey: ["config"],
    queryFn: api.config.get,
  });

  const [form, setForm] = useState<ConfigValues>({});

  useEffect(() => {
    if (serverConfig) setForm(serverConfig);
  }, [serverConfig]);

  const saveMutation = useMutation({
    mutationFn: (patch: ConfigValues) => api.config.put(patch),
    onSuccess: () =>
      toast.success("Configurações salvas — reinicie o backend (cs serve) para aplicar."),
    onError: (e) => toast.error(String(e)),
  });

  function handleImportEnv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const parsed: ConfigValues = {};
      for (const line of text.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        const eqIdx = trimmed.indexOf("=");
        if (eqIdx < 1) continue;
        const key = trimmed.slice(0, eqIdx).trim();
        const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
        if (EDITABLE_KEYS.has(key)) parsed[key] = val;
      }
      if (Object.keys(parsed).length === 0) {
        toast.info("Nenhuma chave editável encontrada no arquivo.");
      } else {
        setForm((prev) => ({ ...prev, ...parsed }));
        toast.success(`${Object.keys(parsed).length} chave(s) importada(s) — revise e salve.`);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  function fieldStr(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function fieldBool(key: string, value: boolean) {
    setForm((prev) => ({ ...prev, [key]: String(value) }));
  }

  const dirty = JSON.stringify(form) !== JSON.stringify(serverConfig ?? {});

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      {/* Tema */}
      <Card>
        <CardHeader className="pb-2 pt-3">
          <CardTitle className="text-sm">Aparência</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            {(["system", "light", "dark"] as const).map((t) => (
              <Button
                key={t}
                variant={theme === t ? "default" : "outline"}
                size="sm"
                onClick={() => setTheme(t)}
              >
                {t === "system" ? "Sistema" : t === "light" ? "Claro" : "Escuro"}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Configurações editáveis */}
      <Card>
        <CardHeader className="pb-2 pt-3 flex-row items-center justify-between">
          <CardTitle className="text-sm">Configurações do backend</CardTitle>
          <div className="flex gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".env,text/plain"
              className="hidden"
              onChange={handleImportEnv}
            />
            <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}>
              Importar .env
            </Button>
            <Button
              size="sm"
              disabled={!dirty || saveMutation.isPending}
              onClick={() => saveMutation.mutate(form)}
            >
              Salvar
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>LLM Backend</Label>
                  <Select
                    value={String(form["LLM_BACKEND"] ?? "anthropic")}
                    onValueChange={(v) => fieldStr("LLM_BACKEND", v)}
                  >
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="anthropic">anthropic</SelectItem>
                      <SelectItem value="ollama">ollama</SelectItem>
                      <SelectItem value="hybrid">hybrid</SelectItem>
                      <SelectItem value="openai">openai</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Whisper Backend</Label>
                  <Select
                    value={String(form["WHISPER_BACKEND"] ?? "local_cpu")}
                    onValueChange={(v) => fieldStr("WHISPER_BACKEND", v)}
                  >
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="local_cpu">local_cpu</SelectItem>
                      <SelectItem value="local_cuda">local_cuda</SelectItem>
                      <SelectItem value="groq">groq</SelectItem>
                      <SelectItem value="openai">openai</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Whisper Device</Label>
                  <Input
                    className="h-8 text-sm"
                    value={String(form["WHISPER_DEVICE"] ?? "cpu")}
                    onChange={(e) => fieldStr("WHISPER_DEVICE", e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label>Log Level</Label>
                  <Select
                    value={String(form["LOG_LEVEL"] ?? "INFO")}
                    onValueChange={(v) => fieldStr("LOG_LEVEL", v)}
                  >
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="DEBUG">DEBUG</SelectItem>
                      <SelectItem value="INFO">INFO</SelectItem>
                      <SelectItem value="WARNING">WARNING</SelectItem>
                      <SelectItem value="ERROR">ERROR</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Loop interval (seg)</Label>
                  <Input
                    className="h-8 text-sm"
                    type="number"
                    value={String(form["PIPELINE_LOOP_INTERVAL"] ?? 60)}
                    onChange={(e) => fieldStr("PIPELINE_LOOP_INTERVAL", e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label>Alert stuck threshold</Label>
                  <Input
                    className="h-8 text-sm"
                    type="number"
                    value={String(form["ALERT_STUCK_THRESHOLD"] ?? 50)}
                    onChange={(e) => fieldStr("ALERT_STUCK_THRESHOLD", e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <Label>Ollama URL</Label>
                <Input
                  className="h-8 text-sm"
                  value={String(form["OLLAMA_BASE_URL"] ?? "")}
                  onChange={(e) => fieldStr("OLLAMA_BASE_URL", e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Ollama modelo triagem</Label>
                  <Input
                    className="h-8 text-sm"
                    value={String(form["OLLAMA_MODEL_TRIAGE"] ?? "")}
                    onChange={(e) => fieldStr("OLLAMA_MODEL_TRIAGE", e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Ollama modelo profundo</Label>
                  <Input
                    className="h-8 text-sm"
                    value={String(form["OLLAMA_MODEL_DEEP"] ?? "")}
                    onChange={(e) => fieldStr("OLLAMA_MODEL_DEEP", e.target.value)}
                  />
                </div>
              </div>

              <div className="border-t pt-3 space-y-3">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Alertas
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label>Canais de alerta</Label>
                    <Input
                      className="h-8 text-sm"
                      placeholder="telegram,smtp"
                      value={String(form["ALERT_CHANNELS"] ?? "telegram")}
                      onChange={(e) => fieldStr("ALERT_CHANNELS", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>Telegram Chat ID</Label>
                    <Input
                      className="h-8 text-sm"
                      value={String(form["TELEGRAM_CHAT_ID"] ?? "")}
                      onChange={(e) => fieldStr("TELEGRAM_CHAT_ID", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>SMTP Host</Label>
                    <Input
                      className="h-8 text-sm"
                      value={String(form["SMTP_HOST"] ?? "")}
                      onChange={(e) => fieldStr("SMTP_HOST", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>SMTP From</Label>
                    <Input
                      className="h-8 text-sm"
                      value={String(form["SMTP_FROM"] ?? "")}
                      onChange={(e) => fieldStr("SMTP_FROM", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1 col-span-2">
                    <Label>SMTP To</Label>
                    <Input
                      className="h-8 text-sm"
                      value={String(form["SMTP_TO"] ?? "")}
                      onChange={(e) => fieldStr("SMTP_TO", e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  id="dry_run"
                  checked={String(form["DRY_RUN"]).toLowerCase() === "true"}
                  onCheckedChange={(v) => fieldBool("DRY_RUN", v)}
                />
                <Label htmlFor="dry_run">Dry run (não escreve no banco)</Label>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Cheatsheet de atalhos */}
      <Card>
        <CardHeader className="pb-2 pt-3">
          <CardTitle className="text-sm">Atalhos de teclado</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-1">
            {SHORTCUTS.map(({ keys, desc }) => (
              <div key={keys} className="flex justify-between text-sm">
                <kbd className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">{keys}</kbd>
                <span className="text-muted-foreground">{desc}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
