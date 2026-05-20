import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from "@/components/ui/sheet";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { api, type Canal } from "@/lib/api";

const EMPTY_CANAL: Canal = {
  id: "",
  nome: "",
  handle: "",
  channel_url: "",
  tema_primario: "soberania_nacional",
  peso: 1.0,
  auto_publish: false,
  tolerancia_cortes: "desconhecida",
  nota: "",
  ativo: true,
};

export default function CanaisPage() {
  const qc = useQueryClient();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editing, setEditing] = useState<Canal>(EMPTY_CANAL);
  const [deleteTarget, setDeleteTarget] = useState<Canal | null>(null);

  const { data: canais = [], isLoading } = useQuery({
    queryKey: ["canais"],
    queryFn: api.canais.list,
  });

  const saveMutation = useMutation({
    mutationFn: (c: Canal) =>
      c.id && canais.some((x) => x.id === c.id)
        ? api.canais.update(c.id, c)
        : api.canais.create(c),
    onSuccess: () => {
      toast.success("Canal salvo");
      qc.invalidateQueries({ queryKey: ["canais"] });
      setSheetOpen(false);
    },
    onError: (e) => toast.error(String(e)),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, ativo }: { id: string; ativo: boolean }) =>
      api.canais.toggleAtivo(id, ativo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["canais"] }),
    onError: (e) => toast.error(String(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.canais.remove(id),
    onSuccess: () => {
      toast.success("Canal removido");
      qc.invalidateQueries({ queryKey: ["canais"] });
      setDeleteTarget(null);
    },
    onError: (e) => toast.error(String(e)),
  });

  function openNew() {
    setEditing(EMPTY_CANAL);
    setSheetOpen(true);
  }

  function openEdit(c: Canal) {
    setEditing({ ...c });
    setSheetOpen(true);
  }

  function field<K extends keyof Canal>(key: K, value: Canal[K]) {
    setEditing((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">Canais monitorados</h3>
        <Button size="sm" onClick={openNew}>
          <Plus className="w-3 h-3 mr-1" /> Novo canal
        </Button>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Carregando…</p>
      ) : canais.length === 0 ? (
        <p className="text-muted-foreground text-sm">Nenhum canal cadastrado.</p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs text-muted-foreground uppercase">
              <tr>
                <th className="text-left px-3 py-2">Canal</th>
                <th className="text-left px-3 py-2">Handle</th>
                <th className="text-left px-3 py-2">Peso</th>
                <th className="text-center px-3 py-2">Auto pub.</th>
                <th className="text-center px-3 py-2">Ativo</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {canais.map((c) => (
                <tr key={c.id} className="border-t hover:bg-muted/20">
                  <td className="px-3 py-2">
                    <div>
                      <p className="font-medium">{c.nome}</p>
                      <p className="text-xs text-muted-foreground">{c.id}</p>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{c.handle}</td>
                  <td className="px-3 py-2">{c.peso}</td>
                  <td className="px-3 py-2 text-center">
                    {c.auto_publish ? (
                      <Badge variant="default" className="text-xs">sim</Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs">não</Badge>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <Switch
                      checked={c.ativo}
                      onCheckedChange={(v) => toggleMutation.mutate({ id: c.id, ativo: v })}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 w-6 p-0"
                        onClick={() => openEdit(c)}
                      >
                        <Pencil className="w-3 h-3" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 w-6 p-0 text-destructive"
                        onClick={() => setDeleteTarget(c)}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Sheet de criação/edição */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="overflow-y-auto w-[420px]">
          <SheetHeader>
            <SheetTitle>{editing.id && canais.some((c) => c.id === editing.id) ? "Editar canal" : "Novo canal"}</SheetTitle>
          </SheetHeader>
          <div className="space-y-3 py-4">
            {(
              [
                { key: "id", label: "ID (slug)", placeholder: "flow-podcast" },
                { key: "nome", label: "Nome", placeholder: "Flow Podcast" },
                { key: "handle", label: "Handle", placeholder: "@FlowPodcast" },
                { key: "channel_url", label: "URL do canal", placeholder: "https://youtube.com/@FlowPodcast" },
                { key: "tema_primario", label: "Tema primário", placeholder: "soberania_nacional" },
                { key: "tolerancia_cortes", label: "Tolerância a cortes", placeholder: "desconhecida" },
                { key: "nota", label: "Nota", placeholder: "" },
              ] as { key: keyof Canal; label: string; placeholder: string }[]
            ).map(({ key, label, placeholder }) => (
              <div key={key} className="space-y-1">
                <Label>{label}</Label>
                <Input
                  placeholder={placeholder}
                  value={String(editing[key] ?? "")}
                  onChange={(e) => field(key, e.target.value as Canal[typeof key])}
                />
              </div>
            ))}

            <div className="space-y-1">
              <Label>Peso</Label>
              <Input
                type="number"
                step="0.1"
                value={editing.peso}
                onChange={(e) => field("peso", parseFloat(e.target.value) || 1)}
              />
            </div>

            <div className="flex items-center gap-2">
              <Switch
                id="auto_publish"
                checked={editing.auto_publish}
                onCheckedChange={(v) => field("auto_publish", v)}
              />
              <Label htmlFor="auto_publish">Auto-publicar</Label>
            </div>

            <div className="flex items-center gap-2">
              <Switch
                id="ativo"
                checked={editing.ativo}
                onCheckedChange={(v) => field("ativo", v)}
              />
              <Label htmlFor="ativo">Ativo</Label>
            </div>
          </div>
          <SheetFooter>
            <Button
              onClick={() => saveMutation.mutate(editing)}
              disabled={!editing.id || !editing.nome || saveMutation.isPending}
            >
              Salvar
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {/* Dialog de confirmação de exclusão */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover canal?</AlertDialogTitle>
            <AlertDialogDescription>
              O canal <strong>{deleteTarget?.nome}</strong> será removido do banco. Esta ação não
              pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
