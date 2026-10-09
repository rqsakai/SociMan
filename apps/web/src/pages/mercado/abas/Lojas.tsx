/*
 * Aba "Lojas" (spec 026, US5): os cartões de loja (ordenáveis por GMV, nome, seguidores,
 * produtos, lançamentos ou comissão; só oficiais; seguidas por um perfil) e o detalhe de uma loja
 * (`?loja=<id>`): fotos, produtos do lago por GMV e os novos em 30 dias.
 */
import { ArrowLeft } from "lucide-react";
import { CartaoLoja } from "@/components/mercado/CartaoLoja";
import { CartaoProduto } from "@/components/mercado/CartaoProduto";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { EmptyState, HeaderCard } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useFiltroUrl } from "@/lib/filtros";
import { formatInteiro, formatUmaCasa, useLoja, useLojas, type EstadoFiltroMercado } from "@/lib/mercado";
import { formatDateKey } from "@/lib/tz";
import { usePerfisAtivos } from "@/lib/usePerfis";

const ORDENS = [
  { id: "gmv", label: "GMV estimado" },
  { id: "nome", label: "Nome" },
  { id: "seguidores", label: "Seguidores" },
  { id: "nProdutos", label: "Produtos no lago" },
  { id: "lancamentos", label: "Lançamentos em 30 d" },
  { id: "comissao", label: "Comissão média" },
] as const;

export function Lojas({ estado }: { estado: EstadoFiltroMercado }) {
  const [params, set] = useFiltroUrl("lj");
  const lojaId = params.get("loja") ?? "";
  if (lojaId) return <DetalheLoja estado={estado} lojaId={lojaId} onVoltar={() => set({ loja: null })} />;
  return <ListaLojas estado={estado} params={params} set={set} />;
}

function ListaLojas({ estado, params, set }: { estado: EstadoFiltroMercado; params: URLSearchParams; set: (p: Record<string, string | null>) => void }) {
  const perfis = usePerfisAtivos();
  const ordenar = params.get("ordenar") ?? "gmv";
  const oficial = params.get("oficial") === "1";
  const seguidaPor = params.get("seguida") ?? "";
  const lojas = useLojas(estado.filtro, { ordenarLoja: ordenar, ...(oficial ? { oficial: true } : {}), ...(seguidaPor ? { seguidaPor } : {}) });
  return (
    <HeaderCard
      title="Lojas"
      description={lojas.data ? `${formatInteiro(lojas.data.total)} loja${lojas.data.total === 1 ? "" : "s"} com produtos no lago` : "Carregando…"}
      actions={
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Ordenar por" className="w-44">
            {({ id }) => (
              <NativeSelect id={id} value={ordenar} onChange={(e) => set({ ordenar: e.target.value === "gmv" ? null : e.target.value })}>
                {ORDENS.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Seguida por" className="w-44">
            {({ id }) => (
              <NativeSelect id={id} value={seguidaPor} onChange={(e) => set({ seguida: e.target.value || null })}>
                <option value="">Qualquer perfil</option>
                {perfis.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={oficial} onChange={(e) => set({ oficial: e.target.checked ? "1" : null })} />
            Só lojas oficiais
          </label>
        </div>
      }
    >
      {lojas.isPending && <Skeleton className="h-24 w-full" />}
      {lojas.isError && <ApiErrorAlert error={lojas.error} />}
      {lojas.data && lojas.data.itens.length === 0 && <EmptyState titulo="Nenhuma loja ainda" descricao="As lojas chegam com as fichas dos produtos coletados." />}
      {lojas.data && lojas.data.itens.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">
          {lojas.data.itens.map((l) => (
            <CartaoLoja key={l.id} loja={l} onAbrir={() => set({ loja: l.id })} />
          ))}
        </div>
      )}
    </HeaderCard>
  );
}

const colF = dataTableColumns<{ dataLocal: string; nota: number | null; seguidores: number | null; envioNoPrazoPct: number | null; nProdutos: number | null; vendidosTotal: number | null }>();
const colunasFotos = colF.columns([
  colF.accessor("dataLocal", { header: "Dia", cell: (c) => formatDateKey(c.getValue()) }),
  colF.accessor("nota", { header: () => <span className="block text-right">Nota</span>, cell: (c) => <span className="block text-right tabular-nums">{formatUmaCasa(c.getValue())}</span> }),
  colF.accessor("seguidores", { header: () => <span className="block text-right">Seguidores</span>, cell: (c) => <span className="block text-right tabular-nums">{formatInteiro(c.getValue())}</span> }),
  colF.accessor("envioNoPrazoPct", { header: () => <span className="block text-right">Envio no prazo</span>, cell: (c) => <span className="block text-right tabular-nums">{c.getValue() === null ? "—" : `${formatUmaCasa(c.getValue())}%`}</span> }),
  colF.accessor("nProdutos", { header: () => <span className="block text-right">Produtos</span>, cell: (c) => <span className="block text-right tabular-nums">{formatInteiro(c.getValue())}</span> }),
  colF.accessor("vendidosTotal", { header: () => <span className="block text-right">Vendidos total</span>, cell: (c) => <span className="block text-right tabular-nums">{formatInteiro(c.getValue())}</span> }),
]);

function DetalheLoja({ estado, lojaId, onVoltar }: { estado: EstadoFiltroMercado; lojaId: string; onVoltar: () => void }) {
  const q = useLoja(lojaId, estado.filtro);
  if (q.isPending) return <Skeleton className="h-48 w-full" />;
  if (q.isError) return <ApiErrorAlert error={q.error} />;
  const l = q.data;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button type="button" variant="ghost" size="sm" onClick={onVoltar}>
          <ArrowLeft aria-hidden="true" />
          Todas as lojas
        </Button>
      </div>
      <CartaoLoja loja={l} />
      <div className="grid gap-6 lg:grid-cols-2">
        <HeaderCard title="Fotos da loja" description="O que a página da loja mostrou em cada dia coletado.">
          <DataTable columns={colunasFotos} data={l.fotos} getRowId={(r) => r.dataLocal} label="Fotos da loja" empty={<p className="text-sm text-muted-foreground">Ainda sem foto da loja.</p>} />
        </HeaderCard>
        <HeaderCard title={`Novos em 30 dias (${l.novos30d.length})`} description="Produtos da loja vistos pela primeira vez há até 30 dias.">
          {l.novos30d.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum lançamento recente no lago.</p> : <div className="flex flex-col gap-2">{l.novos30d.map((p) => <CartaoProduto key={p.id} produto={p} compacto />)}</div>}
        </HeaderCard>
      </div>
      <HeaderCard title={`Produtos no lago (${l.produtos.length})`} description="Ordenados pelo GMV estimado no período.">
        {l.produtos.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum produto desta loja no lago.</p> : <div className="flex flex-col gap-2">{l.produtos.map((p) => <CartaoProduto key={p.id} produto={p} compacto />)}</div>}
      </HeaderCard>
    </div>
  );
}
