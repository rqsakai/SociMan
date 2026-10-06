import { Filter } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { resultadoLabel, resultadoTone, useMcpChamadas, viaLabel, type McpChamada, type McpChamadaFilters, type McpCliente } from "@/lib/mcp";
import { formatDateTime, fromLocal, parseDateKey, toIsoWithOffset } from "@/lib/tz";

type Draft = { clienteId: string; tool: string; resultado: string; via: string; de: string; ate: string };
const vazio: Draft = { clienteId: "", tool: "", resultado: "", via: "", de: "", ate: "" };

function limiteDoDia(dia: string, fim: boolean): string | undefined {
  if (!dia) return undefined;
  const { year, month, day } = parseDateKey(dia);
  const d = fim ? fromLocal(year, month, day + 1) : fromLocal(year, month, day);
  return toIsoWithOffset(fim ? new Date(d.getTime() - 1) : d);
}

function paraFiltros(d: Draft): McpChamadaFilters {
  return {
    clienteId: d.clienteId || undefined,
    tool: d.tool.trim() || undefined,
    resultado: (d.resultado || undefined) as McpChamadaFilters["resultado"],
    via: (d.via || undefined) as McpChamadaFilters["via"],
    de: limiteDoDia(d.de, false),
    ate: limiteDoDia(d.ate, true),
  };
}

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
export function RegistroChamadasTable({ clientes }: { clientes: McpCliente[] | undefined }) {
  const [draft, setDraft] = useState<Draft>(vazio);
  const [filtros, setFiltros] = useState<McpChamadaFilters>({});
  const chamadas = useMcpChamadas(filtros);
  const itens = chamadas.data?.pages.flatMap((p) => p.chamadas);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFiltros(paraFiltros(draft));
  }

  return (
    <div className="space-y-4">
      <form onSubmit={onSubmit} className="grid gap-4 border-b pb-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(6,minmax(0,1fr))_auto] xl:items-end">
        <Field label="Cliente">
          {({ id }) => (
            <NativeSelect id={id} value={draft.clienteId} onChange={(e) => setDraft({ ...draft, clienteId: e.target.value })}>
              <option value="">Todos</option>
              {clientes?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Tool">
          {({ id }) => <Input id={id} value={draft.tool} placeholder="ex.: perfis_list" onChange={(e) => setDraft({ ...draft, tool: e.target.value })} />}
        </Field>
        <Field label="Resultado">
          {({ id }) => (
            <NativeSelect id={id} value={draft.resultado} onChange={(e) => setDraft({ ...draft, resultado: e.target.value })}>
              <option value="">Todos</option>
              {(Object.keys(resultadoLabel) as McpChamada["resultado"][]).map((r) => (
                <option key={r} value={r}>
                  {resultadoLabel[r]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Via">
          {({ id }) => (
            <NativeSelect id={id} value={draft.via} onChange={(e) => setDraft({ ...draft, via: e.target.value })}>
              <option value="">Todas</option>
              {(Object.keys(viaLabel) as McpChamada["via"][]).map((v) => (
                <option key={v} value={v}>
                  {viaLabel[v]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="De">
          {({ id }) => <Input id={id} type="date" value={draft.de} onChange={(e) => setDraft({ ...draft, de: e.target.value })} />}
        </Field>
        <Field label="Até">
          {({ id }) => <Input id={id} type="date" value={draft.ate} onChange={(e) => setDraft({ ...draft, ate: e.target.value })} />}
        </Field>
        <Button type="submit">
          <Filter aria-hidden="true" />
          Filtrar
        </Button>
      </form>
      {chamadas.isError && <ApiErrorAlert error={chamadas.error} />}
      <DataTable
        label="Registro de chamadas MCP"
        columns={columns}
        data={itens}
        loading={chamadas.isPending}
        getRowId={(c) => String(c.id)}
        search={{ placeholder: "Buscar na lista carregada", label: "Buscar no registro" }}
        emptyMessage="Nenhuma chamada encontrada."
        pagination={{
          hasMore: chamadas.hasNextPage,
          onLoadMore: () => void chamadas.fetchNextPage(),
          loadingMore: chamadas.isFetchingNextPage,
        }}
      />
    </div>
  );
}
