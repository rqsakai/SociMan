/*
 * "Agentes (MCP)" (spec 009, US1 e US5; T028/T058). Só para o dono humano.
 *
 * Abas na URL (?aba=clientes|registro):
 * - Clientes: o interruptor geral numa faixa compacta (dois níveis: MCP_HABILITADO no .env, só
 *   leitura aqui, e o botão desta tela; o aviso só quando desligado), e "Agentes conectados" com
 *   "Novo cliente" no cabeçalho (credencial mostrada uma vez) e a tabela com as ações (spec 024, R14).
 * - Registro: toda chamada MCP, com filtros e "Carregar mais".
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CirclePause, History, Plus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ClientesTable } from "@/components/mcp/ClientesTable";
import { NovoClienteDialog } from "@/components/mcp/NovoClienteDialog";
import { RegistroChamadasTable } from "@/components/mcp/RegistroChamadasTable";
import { TokenUmaVezDialog } from "@/components/mcp/TokenUmaVezDialog";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, Page, usePageMeta } from "@/components/shell";
import { VersionHistory } from "@/components/VersionHistory";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
    <Page>
      <PageHeading
        title="Agentes (MCP)"
        description="Credenciais dos agentes que acessam o SociMan pelo MCP. Eles leem e deixam propostas; aprovar, agendar, publicar e reverter continuam só com você."
      />
      <Tabs value={aba} onValueChange={(v) => setParams(v === "clientes" ? {} : { aba: v }, { replace: true })}>
        <TabsList aria-label="Seções dos agentes">
          <TabsTrigger value="clientes">Clientes</TabsTrigger>
          <TabsTrigger value="registro">Registro</TabsTrigger>
        </TabsList>
        <TabsContent value="clientes">
          <Interruptor />
          <ClientesCard clientes={clientes} />
        </TabsContent>
        <TabsContent value="registro">
          <HeaderCard title="Registro de chamadas" description="Da mais nova para a mais antiga. Os argumentos aparecem resumidos e sem segredos.">
            <RegistroChamadasTable clientes={clientes.data?.clientes} />
          </HeaderCard>
        </TabsContent>
      </Tabs>
    </Page>
  );
}

function ClientesCard({ clientes }: { clientes: ReturnType<typeof useMcpClientes> }) {
  const [novo, setNovo] = useState(false);
  const [criado, setCriado] = useState<{ nome: string; token: string } | null>(null);

  return (
    <HeaderCard
      title="Agentes conectados"
      description="Um cliente por agente, com escopo, limites e validade próprios."
      actions={
        <Button type="button" variant="secondary" size="sm" onClick={() => setNovo(true)}>
          <Plus aria-hidden="true" />
          Novo cliente
        </Button>
      }
    >
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
    <div className="space-y-3">
      <Card className="shadow-card gap-0 py-0">
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-3 py-3">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Bot className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div className="min-w-0">
              <h2 id="mcp-label" className="font-medium">
                Acesso MCP
              </h2>
              <p className="text-sm text-muted-foreground" data-testid="mcp-estado">
                {estado}
              </p>
            </div>
            <Switch
              aria-labelledby="mcp-label"
              checked={c.servidorHabilitado && c.habilitado}
              disabled={busy || !c.servidorHabilitado}
              onCheckedChange={(on) => void mudar(on)}
            />
          </div>
          <Badge
            className={c.servidorHabilitado ? "bg-success text-success-foreground" : "bg-secondary text-secondary-foreground"}
            title={c.servidorHabilitado ? "MCP_HABILITADO=true no .env do servidor." : "MCP_HABILITADO no .env do servidor está desligado."}
          >
            {c.servidorHabilitado ? "Servidor ligado" : "Servidor desligado"}
          </Badge>
          <Button type="button" variant="ghost" size="sm" aria-expanded={showHistory} onClick={() => setShowHistory((s) => !s)}>
            <History aria-hidden="true" />
            {showHistory ? "Esconder histórico" : "Histórico"}
          </Button>
        </CardContent>
        {showHistory && (
          <CardContent className="border-t py-3">
            <ConfigHistorico />
          </CardContent>
        )}
      </Card>
      {!mcpLigado(c) && (
        <Alert className="border-warning/60 bg-warning/10">
          <CirclePause aria-hidden="true" className="text-warning" />
          <AlertTitle>MCP desligado</AlertTitle>
          <AlertDescription>
            Toda chamada é recusada com "acesso MCP desligado pelo dono", e a recusa fica no registro.
            {!c.servidorHabilitado &&
              " Para ligar o servidor, quem tem acesso a ele põe MCP_HABILITADO=true no .env da raiz e reinicia a API; esta tela não liga o servidor."}
          </AlertDescription>
        </Alert>
      )}
      {error !== null && <ApiErrorAlert error={error} onReload={() => void config.refetch()} />}
    </div>
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
