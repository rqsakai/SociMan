import { useQueryClient } from "@tanstack/react-query";
import { Ban, CirclePause, CirclePlay, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { TokenUmaVezDialog } from "@/components/mcp/TokenUmaVezDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { clienteSituacaoLabel, clienteSituacaoTone, invalidarColeta, type ColetaCliente } from "@/lib/coleta";
import { formatAgo, formatDateTime } from "@/lib/tz";

// Coletores cadastrados (spec 026, US3): só o prefixo público do token aparece; rotacionar mostra o
// novo token uma vez; suspender/reativar; revogar é final (o registro fica).
const col = dataTableColumns<ColetaCliente>();
const columns = col.columns([
  col.accessor("nome", {
    header: "Coletor",
    cell: (c) => (
      <div className="min-w-0">
        <p className="font-semibold">{c.getValue()}</p>
        <p className="font-mono text-xs text-muted-foreground">
          {c.row.original.tokenId} · {c.row.original.mercado}
        </p>
        {c.row.original.descricao && <p className="text-xs text-muted-foreground">{c.row.original.descricao}</p>}
      </div>
    ),
  }),
  col.accessor((c) => clienteSituacaoLabel[c.situacao], {
    id: "situacao",
    header: "Situação",
    cell: (c) => <Badge className={clienteSituacaoTone[c.row.original.situacao]}>{c.getValue()}</Badge>,
  }),
  col.accessor((c) => c.ultimoContatoEm ?? "", {
    id: "contato",
    header: "Último contato",
    enableGlobalFilter: false,
    cell: (c) => {
      const cl = c.row.original;
      return cl.ultimoContatoEm ? (
        <div className="min-w-0">
          <time dateTime={cl.ultimoContatoEm} title={formatDateTime(cl.ultimoContatoEm)} className="whitespace-nowrap">
            {formatAgo(cl.ultimoContatoEm)}
          </time>
          {(cl.versaoColetor || cl.chromeVersao) && (
            <p className="text-xs text-muted-foreground">
              {cl.versaoColetor ? `coletor ${cl.versaoColetor}` : ""}
              {cl.versaoColetor && cl.chromeVersao ? " · " : ""}
              {cl.chromeVersao ? `Chrome ${cl.chromeVersao}` : ""}
            </p>
          )}
        </div>
      ) : (
        <span className="text-muted-foreground">nunca</span>
      );
    },
  }),
  col.display({ id: "acoes", header: () => <span className="sr-only">Ações</span>, cell: (c) => <Acoes cliente={c.row.original} /> }),
]);

export function ClientesColetaTable({ clientes, loading }: { clientes: ColetaCliente[] | undefined; loading: boolean }) {
  return (
    <DataTable
      columns={columns}
      data={clientes ?? []}
      loading={loading}
      getRowId={(r) => r.id}
      label="Coletores"
      empty={<p className="text-sm text-muted-foreground">Nenhum coletor cadastrado. Crie um para instalar no desktop.</p>}
    />
  );
}

type Acao = "suspenderCliente" | "reativarCliente" | "rotacionarCliente" | "revogarCliente";

function Acoes({ cliente }: { cliente: ColetaCliente }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<Acao | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [token, setToken] = useState<string | null>(null);
  const revogado = cliente.situacao === "revogado";

  async function run(acao: Acao, msg: string) {
    setBusy(acao);
    setError(null);
    try {
      if (acao === "rotacionarCliente") {
        const r = await api.coleta.rotacionarCliente(cliente.id, cliente.version);
        setToken(r.token);
      } else {
        await api.coleta[acao](cliente.id, cliente.version);
      }
      toast.success(msg);
      await invalidarColeta(queryClient);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  if (revogado) {
    return <span className="text-xs text-muted-foreground">{cliente.revogadoEm ? `revogado em ${formatDateTime(cliente.revogadoEm)}` : "revogado"}</span>;
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-end gap-1" role="group" aria-label={`Ações de ${cliente.nome}`}>
        {cliente.situacao === "ativo" && (
          <Button type="button" size="sm" variant="ghost" disabled={busy !== null} onClick={() => void run("suspenderCliente", `${cliente.nome} suspenso.`)}>
            <CirclePause aria-hidden="true" />
            Suspender
          </Button>
        )}
        {cliente.situacao === "suspenso" && (
          <Button type="button" size="sm" variant="ghost" disabled={busy !== null} onClick={() => void run("reativarCliente", `${cliente.nome} reativado.`)}>
            <CirclePlay aria-hidden="true" />
            Reativar
          </Button>
        )}
        <ConfirmButton
          label="Rotacionar"
          icon={RefreshCw}
          size="sm"
          variant="ghost"
          busy={busy === "rotacionarCliente"}
          disabled={busy !== null}
          title={`Rotacionar o token de ${cliente.nome}?`}
          description="O token atual para de valer na hora e o coletor do desktop para até receber o novo (arquivo ~/.config/sociman-coletor/token). O novo aparece uma vez."
          onConfirm={() => run("rotacionarCliente", "Token rotacionado.")}
        />
        <ConfirmButton
          label="Revogar"
          icon={Ban}
          size="sm"
          variant="ghost"
          busy={busy === "revogarCliente"}
          disabled={busy !== null}
          title={`Revogar ${cliente.nome}?`}
          description="O acesso acaba na hora e não volta: para coletar de novo, crie outro coletor. O cadastro e o histórico continuam."
          onConfirm={() => run("revogarCliente", `${cliente.nome} revogado.`)}
        />
      </div>
      {error !== null && <ApiErrorAlert error={error} onReload={() => void invalidarColeta(queryClient)} />}
      <TokenUmaVezDialog token={token} nome={cliente.nome} rotacao onClose={() => setToken(null)} />
    </div>
  );
}
