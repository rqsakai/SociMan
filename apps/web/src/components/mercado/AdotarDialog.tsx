/*
 * "Adotar no catálogo" (spec 026, US6): escolhe o perfil e pede à API a cópia da ficha e das
 * imagens para o cadastro de produtos (spec 012). Sucesso → link para o produto do catálogo;
 * `ja_adotado` → link para o existente; `passo_indisponivel` → aviso de que a 012 ainda não está
 * nesta instalação.
 */
import type { MercadoProdutoDetalhe } from "@sociman/contract";
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, PackagePlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { invalidarInteresses } from "@/lib/mercado";

export function AdotarDialog({ produto, open, onOpenChange }: { produto: MercadoProdutoDetalhe; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const perfis = produto.interessesDoUsuario;
  const [perfilId, setPerfilId] = useState(perfis[0]?.perfilId ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [resultado, setResultado] = useState<{ produtoId: string; existente: boolean } | null>(null);
  const jaAdotado = produto.adotadoEm.find((a) => a.perfilId === perfilId);

  async function confirmar() {
    if (!perfilId) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.mercado.adotar(produto.id, perfilId);
      toast.success("Produto adotado no catálogo do perfil.");
      setResultado({ produtoId: r.produtoId, existente: false });
      await invalidarInteresses(queryClient);
    } catch (err) {
      if (err instanceof ApiError && err.code === "ja_adotado" && typeof (err.details as { produtoId?: unknown } | undefined)?.produtoId === "string") {
        setResultado({ produtoId: (err.details as { produtoId: string }).produtoId, existente: true });
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Adotar no catálogo</DialogTitle>
          <DialogDescription>Copia a ficha atual e as imagens para o cadastro de produtos do perfil (spec 012) e cria o vínculo com este produto do mercado.</DialogDescription>
        </DialogHeader>
        <Field label="Perfil">
          {({ id }) => (
            <NativeSelect id={id} value={perfilId} onChange={(e) => setPerfilId(e.target.value)}>
              {perfis.map((p) => (
                <option key={p.perfilId} value={p.perfilId}>
                  {p.perfilNome}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {jaAdotado && !resultado && (
          <Alert>
            <AlertTitle>Já adotado neste perfil</AlertTitle>
            <AlertDescription>
              <Link to={`/app/perfis/${perfilId}/produtos/${jaAdotado.produtoId}`} className="underline">
                Abrir o produto no catálogo
              </Link>
            </AlertDescription>
          </Alert>
        )}
        {resultado && (
          <Alert>
            <AlertTitle>{resultado.existente ? "Este perfil já tinha adotado o produto" : "Adotado"}</AlertTitle>
            <AlertDescription>
              <Link to={`/app/perfis/${perfilId}/produtos/${resultado.produtoId}`} className="underline">
                Abrir o produto no catálogo
              </Link>
            </AlertDescription>
          </Alert>
        )}
        {error !== null && <ApiErrorAlert error={error} />}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Fechar
          </Button>
          <Button type="button" disabled={busy || !perfilId || Boolean(jaAdotado) || Boolean(resultado)} aria-busy={busy} onClick={() => void confirmar()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <PackagePlus aria-hidden="true" />}
            Adotar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
