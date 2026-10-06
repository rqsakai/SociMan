/*
 * "Agentes (MCP)" (spec 009, US1 e US5; T028/T058). Só para o dono humano.
 *
 * Abas na URL (?aba=clientes|registro):
 * - Clientes: o interruptor geral (dois níveis: MCP_HABILITADO no .env, só leitura aqui, e o botão
 *   desta tela), "Novo cliente" com a credencial mostrada uma vez, e a tabela com as ações.
 * - Registro: toda chamada MCP, com filtros e "Carregar mais".
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CircleCheck, CirclePause, History, Plus, Server } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ClientesTable } from "@/components/mcp/ClientesTable";
import { NovoClienteDialog } from "@/components/mcp/NovoClienteDialog";
import { RegistroChamadasTable } from "@/components/mcp/RegistroChamadasTable";
import { TokenUmaVezDialog } from "@/components/mcp/TokenUmaVezDialog";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, usePageMeta } from "@/components/shell";
import { VersionHistory } from "@/components/VersionHistory";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { invalidarMcp, mcpConfigFieldLabel, mcpConfigKey, mcpConfigVersionsKey, mcpLigado, useMcpClientes, useMcpConfig } from "@/lib/mcp";

const ABAS = ["clientes", "registro"] as const;
type Aba = (typeof ABAS)[number];

export default function Agentes() {
  usePageMeta({ title: "Agentes (MCP)" });
  const [params, setParams] = useSearchParams();
  const pedida = params.get("aba") as Aba | null;
  const aba: Aba = pedida && ABAS.includes(pedida) ? pedida : "clientes";
  const clientes = useMcpClientes();

  return (
    <div className="flex flex-col gap-6">
      <PageHeading
        title="Agentes (MCP)"
        description="Credenciais dos agentes que acessam o SociMan pelo MCP. Eles leem e deixam propostas; aprovar, agendar, publicar e reverter continuam só com você."
      />
      <Tabs value={aba} onValueChange={(v) => setParams(v === "clientes" ? {} : { aba: v }, { replace: true })} className="gap-4">
        <TabsList aria-label="Seções dos agentes">
          <TabsTrigger value="clientes">Clientes</TabsTrigger>
          <TabsTrigger value="registro">Registro</TabsTrigger>
        </TabsList>
        <TabsContent value="clientes" className="space-y-6">
          <Interruptor />
          <ClientesCard clientes={clientes} />
        </TabsContent>
        <TabsContent value="registro">
          <HeaderCard title="Registro de chamadas" description="Da mais nova para a mais antiga. Os argumentos aparecem resumidos e sem segredos." tone="dark">
            <RegistroChamadasTable clientes={clientes.data?.clientes} />
          </HeaderCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ClientesCard({ clientes }: { clientes: ReturnType<typeof useMcpClientes> }) {
  const [novo, setNovo] = useState(false);
  const [criado, setCriado] = useState<{ nome: string; token: string } | null>(null);

  return (
    <HeaderCard title="Clientes" description="Um cliente por agente, com escopo, limites e validade próprios." tone="dark">
      <div className="mb-4 flex justify-end">
        <Button type="button" onClick={() => setNovo(true)}>
          <Plus aria-hidden="true" />
          Novo cliente
        </Button>
      </div>
      {clientes.isError && <ApiErrorAlert error={clientes.error} />}
      <ClientesTable clientes={clientes.data?.clientes} loading={clientes.isPending} />
      <NovoClienteDialog open={novo} onOpenChange={setNovo} onCriado={(c, token) => setCriado({ nome: c.nome, token })} />
      <TokenUmaVezDialog token={criado?.token ?? null} nome={criado?.nome ?? ""} onClose={() => setCriado(null)} />
    </HeaderCard>
  );
}

function Interruptor() {
  const queryClient = useQueryClient();
  const config = useMcpConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [showHistory, setShowHistory] = useState(false);
  const c = config.data;

  async function mudar(habilitado: boolean) {
    if (!c) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.mcp.updateConfig({ version: c.version, habilitado });
      queryClient.setQueryData(mcpConfigKey, r);
      await Promise.all([queryClient.invalidateQueries({ queryKey: mcpConfigVersionsKey }), invalidarMcp(queryClient)]);
      toast.success(habilitado ? "Acesso MCP ligado." : "Acesso MCP desligado. Toda chamada dos agentes é recusada.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (config.isPending) return <p className="text-sm text-muted-foreground" aria-live="polite">Carregando…</p>;
  if (config.isError) return <ApiErrorAlert error={config.error} />;
  if (!c) return null;

  const estado = !c.servidorHabilitado ? "Desligado no servidor (.env)" : c.habilitado ? "Ligado" : "Desligado";
  return (
    <Card className="max-w-2xl shadow-card">
      <CardHeader>
        <CardTitle>
          <h2 className="flex items-center gap-2">
            <Bot className="size-5" aria-hidden="true" />
            Interruptor geral
          </h2>
        </CardTitle>
        <CardDescription>Com o servidor ou este botão desligado, todo agente é recusado.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
          <div>
            <p id="mcp-label" className="font-medium">
              Acesso MCP
            </p>
            <p className="text-sm text-muted-foreground" data-testid="mcp-estado">
              {estado}
            </p>
          </div>
          <Switch aria-labelledby="mcp-label" checked={c.servidorHabilitado && c.habilitado} disabled={busy || !c.servidorHabilitado} onCheckedChange={(on) => void mudar(on)} />
        </div>
        <div className="flex items-start gap-3 rounded-lg border p-3">
          <Server className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0 space-y-1">
            <p className="font-medium">
              Servidor:{" "}
              <Badge className={c.servidorHabilitado ? "bg-success text-success-foreground" : "bg-secondary text-secondary-foreground"}>
                {c.servidorHabilitado ? "ligado" : "desligado"}
              </Badge>
            </p>
            <p className="text-sm text-muted-foreground">
              {c.servidorHabilitado
                ? "MCP_HABILITADO=true no .env do servidor."
                : "Para ligar, quem tem acesso ao servidor põe MCP_HABILITADO=true no .env da raiz e reinicia a API. Esta tela não liga o servidor."}
            </p>
          </div>
        </div>
        {mcpLigado(c) ? (
          <Alert>
            <CircleCheck aria-hidden="true" />
            <AlertTitle>MCP ligado</AlertTitle>
            <AlertDescription>Os clientes ativos acessam o SociMan dentro do escopo e dos limites de cada um.</AlertDescription>
          </Alert>
        ) : (
          <Alert>
            <CirclePause aria-hidden="true" />
            <AlertTitle>MCP desligado</AlertTitle>
            <AlertDescription>Toda chamada é recusada com "acesso MCP desligado pelo dono", e a recusa fica no registro.</AlertDescription>
          </Alert>
        )}
        {error !== null && <ApiErrorAlert error={error} onReload={() => void config.refetch()} />}
        <div>
          <Button type="button" variant="ghost" size="sm" aria-expanded={showHistory} onClick={() => setShowHistory((s) => !s)}>
            <History aria-hidden="true" />
            {showHistory ? "Esconder histórico" : "Histórico do interruptor"}
          </Button>
          {showHistory && <ConfigHistorico />}
        </div>
      </CardContent>
    </Card>
  );
}

function ConfigHistorico() {
  const versions = useQuery({ queryKey: mcpConfigVersionsKey, queryFn: () => api.mcp.configVersions() });
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return (
    <VersionHistory
      versions={versions.data.items}
      labels={mcpConfigFieldLabel}
      formatValue={(_field, value) => (typeof value === "boolean" ? (value ? "Ligado" : "Desligado") : value === null || value === undefined ? "—" : String(value))}
    />
  );
}
