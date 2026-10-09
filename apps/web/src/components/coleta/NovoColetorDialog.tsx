import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { invalidarColeta, type ColetaCliente } from "@/lib/coleta";

// Novo coletor (spec 026, US3): um token `scol_` por desktop. O token volta uma vez na resposta e
// vai direto para o diálogo "guarde agora" de quem abriu; nada fica em cache.
export function NovoColetorDialog({
  open,
  onOpenChange,
  onCriado,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCriado: (cliente: ColetaCliente, token: string) => void;
}) {
  const queryClient = useQueryClient();
  const [nome, setNome] = useState("Desktop do dono");
  const [descricao, setDescricao] = useState("");
  const [mercado, setMercado] = useState("BR");
  const [limite, setLimite] = useState("120");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.coleta.criarCliente({ nome: nome.trim(), descricao: descricao.trim(), mercado, rede: "tiktok", limitePorMinuto: Number(limite) || 120 });
      toast.success(`Coletor ${r.cliente.nome} criado.`);
      await invalidarColeta(queryClient);
      onOpenChange(false);
      onCriado(r.cliente, r.token);
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
            <DialogTitle>Novo coletor</DialogTitle>
            <DialogDescription>Um token por desktop. O mercado define o fuso e a moeda das fotos; outro país precisa de outro perfil de Chrome.</DialogDescription>
          </DialogHeader>
          <Field label="Nome">{({ id }) => <Input id={id} value={nome} onChange={(e) => setNome(e.target.value)} required maxLength={80} />}</Field>
          <Field label="Descrição (opcional)">{({ id }) => <Textarea id={id} value={descricao} onChange={(e) => setDescricao(e.target.value)} maxLength={500} rows={2} />}</Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Mercado">
              {({ id }) => (
                <NativeSelect id={id} value={mercado} onChange={(e) => setMercado(e.target.value)}>
                  <option value="BR">BR (Brasil)</option>
                </NativeSelect>
              )}
            </Field>
            <Field label="Chamadas por minuto" hint="1 a 600; padrão 120">
              {({ id }) => <Input id={id} type="number" min={1} max={600} value={limite} onChange={(e) => setLimite(e.target.value)} />}
            </Field>
          </div>
          {error !== null && <ApiErrorAlert error={error} />}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancelar
            </Button>
            <Button type="submit" disabled={busy || nome.trim() === ""} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Criar e mostrar o token
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
