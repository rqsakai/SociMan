import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { useFiltroUrl } from "@/lib/filtros";
import { resultadoLabel, resultadoTone, useMcpChamadas, viaLabel, type McpChamada, type McpChamadaFilters, type McpCliente } from "@/lib/mcp";
import { formatDateTime, fromLocal, parseDateKey, toIsoWithOffset } from "@/lib/tz";

function limiteDoDia(dia: string, fim: boolean): string | undefined {
  if (!dia) return undefined;
  const { year, month, day } = parseDateKey(dia);
  const d = fim ? fromLocal(year, month, day + 1) : fromLocal(year, month, day);
  return toIsoWithOffset(fim ? new Date(d.getTime() - 1) : d);
}

// "2026-10-07" → "07/10/2026" (etiqueta do filtro)
const diaText = (dia: string) => dia.split("-").reverse().join("/");

const col = dataTableColumns<McpChamada>();
const columns = col.columns([
  col.accessor("ocorreuEm", {
    header: "Quando",
    enableGlobalFilter: false,
    cell: (c) => <time dateTime={c.getValue()} className="whitespace-nowrap">{formatDateTime(c.getValue())}</time>,
  }),
  col.accessor((c) => c.cliente?.nome ?? "—", { id: "cliente", header: "Cliente" }),
  col.accessor("tool", {
    header: "Tool",
    cell: (c) => (
      <span className="font-mono text-xs">
        {c.getValue()}
        {c.row.original.escrita && <span className="ml-1 font-sans text-[0.7rem] text-muted-foreground">(escrita)</span>}
      </span>
    ),
  }),
  col.accessor((c) => resultadoLabel[c.resultado], {
    id: "resultado",
    header: "Resultado",
    cell: (c) => {
      const ch = c.row.original;
      return (
        <div className="flex flex-wrap items-center gap-1">
          <Badge className={resultadoTone[ch.resultado]}>{c.getValue()}</Badge>
          {ch.codigoErro && <code className="text-xs text-muted-foreground">{ch.codigoErro}</code>}
        </div>
      );
    },
  }),
  col.accessor((c) => viaLabel[c.via], { id: "via", header: "Via", meta: { className: "hidden md:table-cell" } }),
  col.accessor("duracaoMs", {
    header: "Duração",
    enableGlobalFilter: false,
    meta: { className: "hidden md:table-cell" },
    cell: (c) => <span className="whitespace-nowrap">{c.getValue()} ms</span>,
  }),
  col.display({
    id: "item",
    header: "Item",
    cell: (c) => {
      const e = c.row.original.entidade;
      if (!e) return <span className="text-muted-foreground">—</span>;
      return e.link ? (
        <Link to={e.link} className="text-sm underline-offset-2 hover:underline">
          Abrir {e.tipo}
        </Link>
      ) : (
        <span className="text-sm">{e.tipo}</span>
      );
    },
  }),
]);

// Registro de chamadas MCP (spec 009, US5, FR-028/029): da mais nova para a mais antiga, com
// filtros no servidor e "Carregar mais" por cursor. Os argumentos chegam já mascarados pela API.
// Spec 024: os filtros ficam na URL com o prefixo `reg_` (a tela tem abas) e valem ao mudar; a busca
// da barra é o filtro por tool.
export function RegistroChamadasTable({ clientes }: { clientes: McpCliente[] | undefined }) {
  const [params, set] = useFiltroUrl("reg_");
  const clienteId = params.get("cliente") ?? "";
  const tool = params.get("tool") ?? "";
  const resultado = (params.get("resultado") ?? "") as McpChamada["resultado"] | "";
  const via = (params.get("via") ?? "") as McpChamada["via"] | "";
  const de = params.get("de") ?? "";
  const ate = params.get("ate") ?? "";
  const filtros: McpChamadaFilters = {
    clienteId: clienteId || undefined,
    tool: tool || undefined,
    resultado: resultado || undefined,
    via: via || undefined,
    de: limiteDoDia(de, false),
    ate: limiteDoDia(ate, true),
  };
  const chamadas = useMcpChamadas(filtros);
  const itens = chamadas.data?.pages.flatMap((p) => p.chamadas);

  const ativos: FiltroAtivo[] = [
    ...(tool ? [{ chave: "tool", rotulo: "Tool", valor: tool, limpar: () => set({ tool: null }) }] : []),
    ...(clienteId
      ? [{ chave: "cliente", rotulo: "Cliente", valor: clientes?.find((c) => c.id === clienteId)?.nome ?? "…", limpar: () => set({ cliente: null }) }]
      : []),
    ...(resultado ? [{ chave: "resultado", rotulo: "Resultado", valor: resultadoLabel[resultado] ?? resultado, limpar: () => set({ resultado: null }) }] : []),
    ...(via ? [{ chave: "via", rotulo: "Via", valor: viaLabel[via] ?? via, limpar: () => set({ via: null }) }] : []),
    ...(de ? [{ chave: "de", rotulo: "De", valor: diaText(de), limpar: () => set({ de: null }), mais: true }] : []),
    ...(ate ? [{ chave: "ate", rotulo: "Até", valor: diaText(ate), limpar: () => set({ ate: null }), mais: true }] : []),
  ];

  return (
    <div className="space-y-4">
      {chamadas.isError && <ApiErrorAlert error={chamadas.error} />}
      <DataTable
        label="Registro de chamadas MCP"
        columns={columns}
        data={itens}
        loading={chamadas.isPending}
        getRowId={(c) => String(c.id)}
        emptyMessage="Nenhuma chamada encontrada."
        toolbar={
          <FilterBar
            busca={{
              valor: tool,
              onChange: (v) => set({ tool: v || null }, { replace: true }),
              rotulo: "Buscar tool",
              placeholder: "Buscar tool (ex.: perfis_list)",
            }}
            principais={
              <>
                <Field label="Cliente" className="w-full sm:w-48">
                  {({ id }) => (
                    <NativeSelect id={id} value={clienteId} onChange={(e) => set({ cliente: e.target.value })}>
                      <option value="">Todos</option>
                      {clientes?.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.nome}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
                <Field label="Resultado" className="w-full sm:w-40">
                  {({ id }) => (
                    <NativeSelect id={id} value={resultado} onChange={(e) => set({ resultado: e.target.value })}>
                      <option value="">Todos</option>
                      {(Object.keys(resultadoLabel) as McpChamada["resultado"][]).map((r) => (
                        <option key={r} value={r}>
                          {resultadoLabel[r]}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
                <Field label="Via" className="w-full sm:w-40">
                  {({ id }) => (
                    <NativeSelect id={id} value={via} onChange={(e) => set({ via: e.target.value })}>
                      <option value="">Todas</option>
                      {(Object.keys(viaLabel) as McpChamada["via"][]).map((v) => (
                        <option key={v} value={v}>
                          {viaLabel[v]}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
              </>
            }
            mais={
              <>
                <Field label="De">
                  {({ id }) => <DateField id={id} value={de} onChange={(iso) => set({ de: iso || null })} />}
                </Field>
                <Field label="Até">
                  {({ id }) => <DateField id={id} value={ate} onChange={(iso) => set({ ate: iso || null })} />}
                </Field>
              </>
            }
            ativos={ativos}
            onLimpar={() => set({ tool: null, cliente: null, resultado: null, via: null, de: null, ate: null })}
          />
        }
        pagination={{
          hasMore: chamadas.hasNextPage,
          onLoadMore: () => void chamadas.fetchNextPage(),
          loadingMore: chamadas.isFetchingNextPage,
        }}
      />
    </div>
  );
}
