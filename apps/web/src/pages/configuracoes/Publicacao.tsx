/*
 * "Envios automáticos" (spec 015, US4; T068; research R11). Só para o dono.
 *
 * O envio para a rede só acontece com os dois níveis ligados: PUBLICACAO_HABILITADA no .env do
 * servidor (só leitura aqui) e o interruptor desta tela. Ligar pede confirmação e avisa quantos
 * agendamentos vencidos vão pedir "Confirmar envio" antes de sair; "Revisar vencidos" abre a lista
 * de Conteúdos no atalho `vencidos`.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CirclePause, History, ListChecks, Loader2, Server, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PageHeading } from "@/components/PageHeading";
import { VersionHistory } from "@/components/VersionHistory";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { invalidarConteudos } from "@/lib/conteudos";
import {
  enviosLigados,
  publicacaoConfigFieldLabel,
  publicacaoConfigKey,
  publicacaoConfigVersionsKey,
  situacaoAppLabel,
  usePublicacaoConfig,
} from "@/lib/publicacao";

export default function Publicacao() {
  const queryClient = useQueryClient();
  const config = usePublicacaoConfig();
  const [confirmarLigar, setConfirmarLigar] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [showHistory, setShowHistory] = useState(false);
  const c = config.data?.config;

  async function mudar(enviosHabilitados: boolean) {
    if (!c) return;
    setError(null);
    setBusy(true);
    try {
      const r = await api.publicacao.updateConfig({ version: c.version, enviosHabilitados });
      queryClient.setQueryData(publicacaoConfigKey, r);
      await Promise.all([queryClient.invalidateQueries({ queryKey: publicacaoConfigVersionsKey }), invalidarConteudos(queryClient)]);
      if (enviosHabilitados) {
        toast.success(
          r.config.vencidos > 0
            ? `Envios automáticos ligados. ${r.config.vencidos} agendamento(s) vencido(s) pedem sua confirmação.`
            : "Envios automáticos ligados.",
        );
      } else {
        toast.success("Envios automáticos desligados. Nada sai para a rede até ligar de novo.");
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      setConfirmarLigar(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeading title="Envios automáticos" description="Controle geral do envio de rascunhos para as redes. Desligado, nada sai do SociMan." />
      {config.isPending && (
        <p aria-live="polite" className="text-sm text-muted-foreground">
          Carregando…
        </p>
      )}
      {config.isError && <ApiErrorAlert error={config.error} />}

      {c && (
        <>
          <Card className="max-w-2xl shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Interruptor</h2>
              </CardTitle>
              <CardDescription>Os envios só acontecem com o servidor e o interruptor ligados.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
                <div>
                  <p id="envios-label" className="font-medium">
                    Envios automáticos
                  </p>
                  <p className="text-sm text-muted-foreground">{c.enviosHabilitados ? "Ligado" : "Desligado"}</p>
                </div>
                <Switch
                  aria-labelledby="envios-label"
                  checked={c.enviosHabilitados}
                  disabled={busy}
                  onCheckedChange={(on) => (on ? setConfirmarLigar(true) : void mudar(false))}
                />
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
                      ? "PUBLICACAO_HABILITADA=true no .env do servidor."
                      : "Para ligar, quem tem acesso ao servidor põe PUBLICACAO_HABILITADA=true no .env da raiz e reinicia a API e o agendador. Esta tela não liga o servidor."}
                  </p>
                </div>
              </div>

              {enviosLigados(c) ? (
                <Alert>
                  <CircleCheck aria-hidden="true" />
                  <AlertTitle>Envios ativos</AlertTitle>
                  <AlertDescription>No horário, o SociMan envia os agendamentos automáticos aprovados por um dono.</AlertDescription>
                </Alert>
              ) : (
                <Alert>
                  <CirclePause aria-hidden="true" />
                  <AlertTitle>Envios pausados</AlertTitle>
                  <AlertDescription>
                    <p>Os agendamentos automáticos que chegarem ao horário ficam "Pausado" e nada é enviado.</p>
                    {c.emAndamento > 0 && <p>{c.emAndamento} envio(s) em andamento ficaram pausados e retomam ao ligar.</p>}
                  </AlertDescription>
                </Alert>
              )}

              {c.vencidos > 0 && (
                <Alert>
                  <TriangleAlert aria-hidden="true" />
                  <AlertTitle>{c.vencidos} agendamento(s) vencido(s)</AlertTitle>
                  <AlertDescription>
                    <p>Passaram do horário há mais de 1 hora sem sair. Cada um pede "Confirmar envio agora" ou um novo horário.</p>
                    <Button asChild size="sm" variant="outline" className="mt-2">
                      <Link to="/app/conteudos?atalho=vencidos">
                        <ListChecks aria-hidden="true" />
                        Revisar vencidos
                      </Link>
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
              {c.vencidos === 0 && (
                <Button asChild size="sm" variant="ghost">
                  <Link to="/app/conteudos?atalho=vencidos">
                    <ListChecks aria-hidden="true" />
                    Revisar vencidos
                  </Link>
                </Button>
              )}

              {error !== null && <ApiErrorAlert error={error} onReload={() => void config.refetch()} />}
            </CardContent>
          </Card>

          <Card className="max-w-2xl shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>App da TikTok</h2>
              </CardTitle>
              <CardDescription>Situação do app da agência no portal da TikTok e os endereços de volta do login.</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
                <dt className="font-medium">Situação</dt>
                <dd>{situacaoAppLabel[c.situacaoApp] ?? c.situacaoApp}</dd>
                <dt className="font-medium">App configurado</dt>
                <dd>{c.appConfigurado ? "Sim" : "Não (faltam TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET no .env)"}</dd>
                <dt className="font-medium">Chave das credenciais</dt>
                <dd>{c.tokensConfigurados ? "Configurada" : "Não configurada (falta SOCIMAN_TOKENS_KEY no .env)"}</dd>
                <dt className="font-medium">Login pela casa</dt>
                <dd className="break-all">{c.enderecosLogin.web ?? "—"}</dd>
                <dt className="font-medium">Login no computador</dt>
                <dd className="break-all">{c.enderecosLogin.desktop ?? "—"}</dd>
              </dl>
              {c.situacaoApp === "sandbox" && (
                <p className="mt-3 text-sm text-muted-foreground">
                  Em sandbox, só as contas liberadas no portal recebem rascunhos, e "Publicar no horário" sai só para você, com a conta privada.
                </p>
              )}
            </CardContent>
          </Card>

          <div>
            <Button type="button" variant="ghost" size="sm" aria-expanded={showHistory} onClick={() => setShowHistory((s) => !s)}>
              <History aria-hidden="true" />
              {showHistory ? "Esconder histórico" : "Histórico do interruptor"}
            </Button>
            {showHistory && <ConfigHistorico />}
          </div>
        </>
      )}

      <AlertDialog open={confirmarLigar} onOpenChange={(o) => !busy && setConfirmarLigar(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ligar os envios automáticos?</AlertDialogTitle>
            <AlertDialogDescription>
              {c && !c.servidorHabilitado
                ? "O servidor continua desligado (PUBLICACAO_HABILITADA): nada sai até ele ser ligado também. "
                : "No horário, o SociMan envia os agendamentos automáticos aprovados. "}
              {c && c.vencidos > 0
                ? `${c.vencidos} agendamento(s) vencido(s) não saem sozinhos: cada um pede sua confirmação.`
                : "Agendamentos vencidos há mais de 1 hora pedem sua confirmação antes de sair."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(e) => {
                e.preventDefault();
                void mudar(true);
              }}
            >
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              Ligar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function ConfigHistorico() {
  const versions = useQuery({ queryKey: publicacaoConfigVersionsKey, queryFn: () => api.publicacao.configVersions() });
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return (
    <VersionHistory
      versions={versions.data.items}
      labels={publicacaoConfigFieldLabel}
      formatValue={(_field, value) => (typeof value === "boolean" ? (value ? "Ligado" : "Desligado") : value === null || value === undefined ? "—" : String(value))}
    />
  );
}
