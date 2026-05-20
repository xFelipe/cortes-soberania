import { useState } from "react";
import { Command, CommandInput, CommandList, CommandEmpty } from "cmdk";
import { Dialog, DialogContent } from "@/components/ui/dialog";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CommandPalette({ open, onClose }: Props) {
  const [value, setValue] = useState("");

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="p-0 max-w-lg">
        <Command className="rounded-lg border">
          <CommandInput
            placeholder="Buscar…"
            value={value}
            onValueChange={setValue}
          />
          <CommandList className="max-h-64">
            <CommandEmpty>Implementado na Onda 4.</CommandEmpty>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
