/*
 * "Acompanhar neste perfil" (spec 026, US4) no detalhe do produto: seletor de perfil (só os que
 * ainda não acompanham) e nota; cria o interesse `manual` (2 fotos por dia a partir de hoje).
 */
import type { MercadoProdutoDetalhe } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Star } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { invalidarInteresses } from "@/lib/mercado";

export function AcompanharDialog({ produto, open, onOpenChange }: { produto: MercadoProdutoDetalhe; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const livres = produto.interessesDoUsuario.filter((p) => !p.interesseId);
  const [perfilId, setPerfilId] = useState(livres[0]?.perfilId ?? "");
  const [nota, setNota] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!perfilId) return;
    setBusy(true);
    setError(null);
    try {
      await api.mercado.perfilInteresseCriar(perfilId, { mercadoProdutoId: produto.id, nota: nota.trim() });
      toast.success("Produto acompanhado: duas fotos por dia a partir de hoje.");
      await invalidarInteresses(queryClient);
      onOpenChange(false);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={(e) => void submit(e)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Acompanhar neste perfil</DialogTitle>
            <DialogDescription>O perfil passa a pedir duas fotos por dia deste produto; o acompanhamento manual nunca esfria.</DialogDescription>
          </DialogHeader>
          <Field label="Perfil">
            {({ id }) => (
              <NativeSelect id={id} value={perfilId} onChange={(e) => setPerfilId(e.target.value)} required>
                {livres.length === 0 && <option value="">Todos os perfis já acompanham</option>}
                {livres.map((p) => (
                  <option key={p.perfilId} value={p.perfilId}>
                    {p.perfilNome}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Nota (opcional)">{({ id }) => <Input id={id} value={nota} onChange={(e) => setNota(e.target.value)} maxLength={2000} />}</Field>
          {error !== null && <ApiErrorAlert error={error} />}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancelar
            </Button>
            <Button type="submit" disabled={busy || !perfilId} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Star aria-hidden="true" />}
              Acompanhar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
