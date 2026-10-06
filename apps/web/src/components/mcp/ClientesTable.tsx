import { Gauge } from "lucide-react";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { escopoLabel, situacaoLabel, situacaoTone, vencimentoTexto, type McpCliente } from "@/lib/mcp";
import { formatAgo, formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";
import { ClienteAcoes } from "./ClienteAcoes";

const col = dataTableColumns<McpCliente>();
const columns = col.columns([
  col.accessor("nome", {
    header: "Cliente",
    cell: (c) => (
      <div className="min-w-0">
        <p className="font-semibold">{c.getValue()}</p>
        {c.row.original.descricao && <p className="text-xs text-muted-foreground">{c.row.original.descricao}</p>}
      </div>
    ),
  }),
  col.accessor((c) => escopoLabel[c.escopo], { id: "escopo", header: "Escopo" }),
  col.accessor((c) => situacaoLabel[c.situacao], {
    id: "situacao",
    header: "Situação",
    cell: (c) => {
      const cl = c.row.original;
      return (
        <div className="flex flex-wrap items-center gap-1">
          <Badge className={situacaoTone[cl.situacao]}>{c.getValue()}</Badge>
          {cl.noLimite && (
            <Badge variant="outline" className="gap-1 border-warning text-warning-foreground">
              <Gauge className="size-3" aria-hidden="true" />
              no limite
            </Badge>
          )}
          {cl.situacao === "revogado" && cl.revogadoEm && (
            <span className="text-xs text-muted-foreground">
              {formatDateTime(cl.revogadoEm)}
              {cl.revogadoPor ? ` por ${cl.revogadoPor.name}` : ""}
            </span>
          )}
        </div>
      );
    },
  }),
  col.accessor((c) => c.ultimoUsoEm ?? "", {
    id: "ultimoUso",
    header: "Último uso",
    enableGlobalFilter: false,
    cell: (c) => {
      const iso = c.row.original.ultimoUsoEm;
      return iso ? (
        <time dateTime={iso} title={formatDateTime(iso)} className="whitespace-nowrap">
          {formatAgo(iso)}
        </time>
      ) : (
        <span className="text-muted-foreground">sem uso</span>
      );
    },
  }),
  col.accessor((c) => c.uso24h.chamadas, {
    id: "uso24h",
    header: "24 h",
    enableGlobalFilter: false,
    meta: { className: "hidden md:table-cell" },
    cell: (c) => {
      const u = c.row.original.uso24h;
      return (
        <span className="whitespace-nowrap text-sm">
          {u.chamadas} chamada(s)
          <span className={cn("block text-xs", u.recusas > 0 ? "text-destructive" : "text-muted-foreground")}>{u.recusas} recusa(s)</span>
        </span>
      );
    },
  }),
  col.accessor((c) => c.expiraEm ?? "", {
    id: "vencimento",
    header: "Validade",
    enableGlobalFilter: false,
    meta: { className: "hidden lg:table-cell" },
    cell: (c) => {
      const cl = c.row.original;
      return <span className={cn("text-sm", cl.venceEmBreve && "font-medium text-warning-foreground")}>{vencimentoTexto(cl, formatDateTime)}</span>;
    },
  }),
  col.display({ id: "acoes", header: "", cell: (c) => <ClienteAcoes cliente={c.row.original} /> }),
]);

// Clientes MCP (spec 009, FR-029): escopo, situação, último uso, uso em 24 h, "no limite" e validade.
export function ClientesTable({ clientes, loading }: { clientes: McpCliente[] | undefined; loading: boolean }) {
  return (
    <DataTable
      label="Clientes MCP"
      columns={columns}
      data={clientes}
      loading={loading}
      getRowId={(c) => c.id}
      emptyMessage="Nenhum cliente ainda. Crie um para cada agente."
      initialPageSize={25}
    />
  );
}
