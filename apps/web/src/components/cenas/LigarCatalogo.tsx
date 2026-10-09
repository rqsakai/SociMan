import { Link2, Loader2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SeletorProduto, type EscolhaProduto } from "./SeletorProduto";

// "Ligar ao catálogo" (spec 012, US4, FR-026): a cena com referência leve (nome curto e foto da
// biblioteca) passa a apontar para um produto aprovado. O save limpa a referência leve; numa cena
// pronta, mexer no produto a devolve a rascunho (regra da 010).
export function LigarCatalogo({
  perfilId,
  produtoNome,
  pronta,
  disabled,
  title,
  onLigar,
}: {
  perfilId: string;
  produtoNome: string;
  pronta: boolean;
  disabled?: boolean;
  title?: string;
  onLigar: (e: EscolhaProduto) => Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const [escolha, setEscolha] = useState<EscolhaProduto>({ produtoId: null, produtoVarianteId: null });
  const [busy, setBusy] = useState(false);

  return (
    <>
      <Button type="button" variant="outline" disabled={disabled} title={title} onClick={() => setOpen(true)}>
        <Link2 aria-hidden="true" />
        Ligar ao catálogo
      </Button>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          if (busy) return;
          if (o) setEscolha({ produtoId: null, produtoVarianteId: null });
          setOpen(o);
        }}
      >
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Ligar ao catálogo</DialogTitle>
            <DialogDescription>
              Hoje a cena aponta para "{produtoNome}" só pelo nome. Ligada a um produto aprovado, o prompt usa a descrição da ficha e a cor
              em inglês da variante, e o ingrediente passa a ser o recorte.
              {pronta && " A cena volta a rascunho."}
            </DialogDescription>
          </DialogHeader>
          <SeletorProduto perfilId={perfilId} valor={escolha} onChange={setEscolha} disabled={busy} />
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={busy || !escolha.produtoId}
              aria-busy={busy}
              onClick={async () => {
                setBusy(true);
                const ok = await onLigar(escolha);
                setBusy(false);
                if (ok) setOpen(false);
              }}
            >
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Link2 aria-hidden="true" />}
              Ligar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
