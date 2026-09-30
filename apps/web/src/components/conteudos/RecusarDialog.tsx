/*
 * Recusar a aprovação de um destino (spec 014, US2; só dono). O motivo é obrigatório (1 a 500) e
 * fica visível no destino até a próxima aprovação; quem pediu recebe o aviso no sino.
 */
import type { Destino } from "@sociman/contract";
import { Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { MOTIVO_MAX } from "@/lib/postagem";

export function RecusarDialog({
  destino,
  contaText,
  open,
  onOpenChange,
  onDone,
}: {
  destino: Pick<Destino, "id" | "version">;
  contaText: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: () => Promise<void>;
}) {
  const [motivo, setMotivo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (open) {
      setMotivo("");
      setError(null);
    }
  }, [open]);
  const vazio = motivo.trim().length === 0;

  async function recusar() {
    if (vazio) return;
    setBusy(true);
    setError(null);
    try {
      await api.destinos.recusar(destino.id, { version: destino.version, motivo: motivo.trim() });
      onOpenChange(false);
      await onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Recusar para {contaText}</DialogTitle>
          <DialogDescription>O conteúdo volta a "pronto" nesta conta, com o motivo visível para a equipe.</DialogDescription>
        </DialogHeader>
        <Field label="Motivo da recusa" hint={`${motivo.length}/${MOTIVO_MAX}`}>
          {({ id, describedBy }) => (
            <Textarea
              id={id}
              rows={3}
              maxLength={MOTIVO_MAX}
              value={motivo}
              aria-describedby={describedBy}
              aria-required="true"
              onChange={(e) => setMotivo(e.target.value)}
            />
          )}
        </Field>
        {error !== null && <ApiErrorAlert error={error} onReload={() => void onDone()} />}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="button" variant="destructive" disabled={vazio || busy} aria-busy={busy} onClick={() => void recusar()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <X aria-hidden="true" />}
            Recusar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
