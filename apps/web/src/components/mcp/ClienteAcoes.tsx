import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CirclePause, CirclePlay, History, Pencil, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { VersionHistory } from "@/components/VersionHistory";
import { api } from "@/lib/api";
import { escopoLabel, invalidarMcp, mcpClienteFieldLabel, mcpClienteVersionsKey, situacaoLabel, type McpCliente, type McpEscopo, type McpSituacao } from "@/lib/mcp";
import { formatDateTime } from "@/lib/tz";
import { NovoClienteDialog } from "./NovoClienteDialog";
import { TokenUmaVezDialog } from "./TokenUmaVezDialog";

type Acao = "suspender" | "reativar" | "rotacionar" | "revogar";

// Ações de um cliente MCP na tabela (spec 009, US1): editar, suspender/reativar, rotacionar e
// revogar (os dois últimos com AlertDialog) e o histórico. Revogado é final: só o histórico.
export function ClienteAcoes({ cliente }: { cliente: McpCliente }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<Acao | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [editar, setEditar] = useState(false);
  const [historico, setHistorico] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const revogado = cliente.situacao === "revogado";

  async function run(acao: Acao, msg: string) {
    setBusy(acao);
    setError(null);
    try {
      if (acao === "rotacionar") {
        const r = await api.mcp.rotacionar(cliente.id, cliente.version);
        setToken(r.token);
      } else {
        await api.mcp[acao](cliente.id, cliente.version);
      }
      toast.success(msg);
      await invalidarMcp(queryClient, cliente.id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-end gap-1" role="group" aria-label={`Ações de ${cliente.nome}`}>
        {!revogado && (
          <Button type="button" size="sm" variant="ghost" disabled={busy !== null} onClick={() => setEditar(true)}>
            <Pencil aria-hidden="true" />
            Editar
          </Button>
        )}
        {cliente.situacao === "ativo" && (
          <Button type="button" size="sm" variant="ghost" disabled={busy !== null} aria-busy={busy === "suspender"} onClick={() => void run("suspender", `${cliente.nome} suspenso.`)}>
            <CirclePause aria-hidden="true" />
            Suspender
          </Button>
        )}
        {cliente.situacao === "suspenso" && (
          <Button type="button" size="sm" variant="ghost" disabled={busy !== null} aria-busy={busy === "reativar"} onClick={() => void run("reativar", `${cliente.nome} reativado.`)}>
            <CirclePlay aria-hidden="true" />
            Reativar
          </Button>
        )}
        {!revogado && (
          <ConfirmButton
            label="Rotacionar"
            icon={RefreshCw}
            size="sm"
            variant="ghost"
            busy={busy === "rotacionar"}
            disabled={busy !== null}
            title={`Rotacionar a credencial de ${cliente.nome}?`}
            description="A credencial atual para de valer na hora. A nova aparece uma vez; o nome, o histórico e o registro de chamadas continuam."
            onConfirm={() => run("rotacionar", "Credencial rotacionada.")}
          />
        )}
        {!revogado && (
          <ConfirmButton
            label="Revogar"
            icon={Ban}
            size="sm"
            variant="ghost"
            busy={busy === "revogar"}
            disabled={busy !== null}
            title={`Revogar ${cliente.nome}?`}
            description="O acesso acaba na hora e não volta: para reativar o agente, crie outro cliente. O cliente continua na lista, com o histórico e o registro."
            onConfirm={() => run("revogar", `${cliente.nome} revogado.`)}
          />
        )}
        <Button type="button" size="sm" variant="ghost" onClick={() => setHistorico(true)}>
          <History aria-hidden="true" />
          Histórico
        </Button>
      </div>
      {error !== null && <ApiErrorAlert error={error} onReload={() => void invalidarMcp(queryClient, cliente.id)} />}

      {editar && <NovoClienteDialog open={editar} onOpenChange={setEditar} cliente={cliente} />}
      <TokenUmaVezDialog token={token} nome={cliente.nome} rotacao onClose={() => setToken(null)} />
      <Dialog open={historico} onOpenChange={setHistorico}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Histórico de {cliente.nome}</DialogTitle>
            <DialogDescription>Criação, edições, suspensões, rotações e revogação. A credencial nunca aparece aqui.</DialogDescription>
          </DialogHeader>
          {historico && <ClienteHistorico clienteId={cliente.id} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ClienteHistorico({ clienteId }: { clienteId: string }) {
  const versions = useQuery({ queryKey: mcpClienteVersionsKey(clienteId), queryFn: () => api.mcp.versions(clienteId) });
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return (
    <VersionHistory
      versions={versions.data.items}
      labels={mcpClienteFieldLabel}
      formatValue={(field, value) => {
        if (value === null || value === undefined || value === "") return "—";
        if (field === "escopo" && typeof value === "string") return escopoLabel[value as McpEscopo] ?? value;
        if (field === "situacao" && typeof value === "string") return situacaoLabel[value as McpSituacao] ?? value;
        if (field === "expira_em" && typeof value === "string") return formatDateTime(value);
        return String(value);
      }}
    />
  );
}
