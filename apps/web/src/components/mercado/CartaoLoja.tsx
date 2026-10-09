/*
 * Cartão de loja (spec 026, US5): nota, seguidores, envio no prazo, nº de produtos, vendidos
 * total (observados) e GMV estimado, concentração no nº 1, lançamentos em 30 d e comissão média
 * (derivados, estimados). "Seguir loja neste perfil" escolhe o perfil (qualquer humano).
 */
import type { MercadoCartaoLoja } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Loader2, Store } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { formatBp, formatCentavos, formatInteiro, formatUmaCasa, invalidarInteresses } from "@/lib/mercado";
import { usePerfisAtivos } from "@/lib/usePerfis";
import { cn } from "@/lib/utils";
import { Estimado } from "./Estimado";

export function CartaoLoja({ loja: l, onAbrir, className }: { loja: MercadoCartaoLoja; onAbrir?: () => void; className?: string }) {
  const [seguir, setSeguir] = useState(false);
  const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${formatUmaCasa(v)}%`);
  const frac = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${formatUmaCasa(v * 100)}%`);
  return (
    <article data-loja={l.redeLojaId} className={cn("flex min-w-0 flex-col gap-2 rounded-lg border bg-card p-3 text-card-foreground", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Store className="size-4 text-muted-foreground" aria-hidden="true" />
        {onAbrir ? (
          <button type="button" className="truncate font-medium hover:underline" onClick={onAbrir}>
            {l.nome}
          </button>
        ) : (
          <span className="truncate font-medium">{l.nome}</span>
        )}
        {l.oficial && <Badge variant="outline">Loja oficial</Badge>}
        {l.seguidaPor.length > 0 && <Badge variant="secondary">seguida por {l.seguidaPor.length} perfil{l.seguidaPor.length === 1 ? "" : "is"}</Badge>}
        {l.url && (
          <a href={l.url} target="_blank" rel="noopener noreferrer" className="ml-auto inline-flex items-center gap-1 text-xs underline">
            <ExternalLink className="size-3" aria-hidden="true" />
            abrir
          </a>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <Item rotulo="Nota">{formatUmaCasa(l.nota.valor)}</Item>
        <Item rotulo="Seguidores">{formatInteiro(l.seguidores.valor)}</Item>
        <Item rotulo="Envio no prazo">{pct(l.envioNoPrazoPct.valor)}</Item>
        <Item rotulo="Produtos na loja">{formatInteiro(l.nProdutos.valor)}</Item>
        <Item rotulo="Vendidos total">
          <Estimado numero={l.vendidosTotal} formatar={formatInteiro} />
        </Item>
        <Item rotulo="GMV estimado (período)">
          <Estimado numero={l.gmvEstimadoCentavos} formatar={formatCentavos} />
        </Item>
        <Item rotulo="Concentração no nº 1">
          <Estimado numero={l.concentracaoTop1} formatar={frac} />
        </Item>
        <Item rotulo="Comissão média">
          <Estimado numero={l.comissaoMediaBp} formatar={formatBp} />
        </Item>
        <Item rotulo="No lago">
          {formatInteiro(l.nProdutosNoLago)} produto{l.nProdutosNoLago === 1 ? "" : "s"} · {formatInteiro(l.nProdutosAcompanhados)} acompanhado{l.nProdutosAcompanhados === 1 ? "" : "s"}
        </Item>
        <Item rotulo="Lançamentos em 30 d">{formatInteiro(l.lancamentos30d)}</Item>
      </dl>
      <div className="flex justify-end">
        <Button type="button" size="sm" variant="outline" onClick={() => setSeguir(true)}>
          Seguir loja neste perfil
        </Button>
      </div>
      {seguir && <SeguirLojaDialog loja={l} open={seguir} onOpenChange={setSeguir} />}
    </article>
  );
}

function Item({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="truncate tabular-nums">{children}</dd>
    </div>
  );
}

export function SeguirLojaDialog({ loja, open, onOpenChange }: { loja: MercadoCartaoLoja; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const perfis = usePerfisAtivos();
  const livres = (perfis.data ?? []).filter((p) => !loja.seguidaPor.includes(p.id));
  const [perfilId, setPerfilId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const alvo = perfilId || livres[0]?.id || "";

  async function confirmar() {
    if (!alvo) return;
    setBusy(true);
    setError(null);
    try {
      const cfg = await api.mercado.perfilConfig(alvo);
      await api.mercado.lojaSeguir(alvo, loja.id, cfg.version);
      toast.success(`${loja.nome} seguida: os produtos novos dela viram acompanhamentos do perfil.`);
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
        <DialogHeader>
          <DialogTitle>Seguir {loja.nome}</DialogTitle>
          <DialogDescription>A loja entra nas seguidas do perfil; a ficha dela é coletada e os produtos novos (até o teto diário) viram acompanhamentos automáticos.</DialogDescription>
        </DialogHeader>
        <Field label="Perfil">
          {({ id }) => (
            <NativeSelect id={id} value={alvo} onChange={(e) => setPerfilId(e.target.value)}>
              {livres.length === 0 && <option value="">Todos os perfis já seguem</option>}
              {livres.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {error !== null && <ApiErrorAlert error={error} />}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancelar
          </Button>
          <Button type="button" disabled={busy || !alvo} aria-busy={busy} onClick={() => void confirmar()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Store aria-hidden="true" />}
            Seguir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
