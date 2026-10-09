/*
 * "Coleta de mercado" (spec 026, US3): /app/configuracoes/coleta.
 *
 * Para o dono humano: o bloco de risco (texto resumido de docs/decisoes/coleta-mercado.md) com
 * "Aceito o risco" em AlertDialog; o interruptor (desabilitado até o aceite; o nível do servidor,
 * COLETA_HABILITADA, é só leitura aqui); janela, tetos e pausas; "Pausar por N horas" e "Continuar"
 * (visível quando a rodada está pausada por captcha ou login); coletores (token mostrado uma vez);
 * rodadas e eventos recentes; o guia de instalação. O membro vê só o estado.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CirclePause, CirclePlay, History, Plus, Radar, ShieldAlert } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ClientesColetaTable } from "@/components/coleta/ClientesColetaTable";
import { NovoColetorDialog } from "@/components/coleta/NovoColetorDialog";
import { ConfirmButton } from "@/components/ConfirmButton";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { TokenUmaVezDialog } from "@/components/mcp/TokenUmaVezDialog";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, Page, usePageMeta } from "@/components/shell";
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
import { Card, CardContent } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { VersionHistory } from "@/components/VersionHistory";
import { api } from "@/lib/api";
import {
  coletaConfigFieldLabel,
  coletaConfigKey,
  coletaConfigVersionsKey,
  eventoTipoLabel,
  HORAS,
  horaLabel,
  invalidarColeta,
  rodadaEstadoLabel,
  situacaoColetaLabel,
  situacaoColetaTone,
  useColetaClientes,
  useColetaColetas,
  useColetaConfig,
  useColetaEstado,
  useColetaEventos,
  type ColetaConfig,
  type ColetaEvento,
  type ColetaResumoRodada,
} from "@/lib/coleta";
import { useEhDono } from "@/lib/conteudos";
import { formatAgo, formatDateTime } from "@/lib/tz";

export default function Coleta() {
  usePageMeta({ title: "Coleta de mercado" });
  const ehDono = useEhDono();
  return (
    <Page>
      <PageHeading
        title="Coleta de mercado"
        description="O coletor do desktop lê o TikTok Shop com a conta de afiliado do dono, em ritmo humano, e manda as fotos para cá. Ligar, pausar e os tokens ficam com o dono; todo mundo vê o estado."
      />
      <Estado />
      {ehDono ? (
        <>
          <RiscoEInterruptor />
          <div className="grid gap-6 lg:grid-cols-2">
            <Limites />
            <Coletores />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Rodadas />
            <Eventos />
          </div>
          <Guia />
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Aceite de risco, interruptor, limites e tokens ficam só com o dono.</p>
      )}
    </Page>
  );
}

function Estado() {
  const estado = useColetaEstado();
  if (estado.isPending) return <p className="text-sm text-muted-foreground" aria-live="polite">Carregando…</p>;
  if (estado.isError) return <ApiErrorAlert error={estado.error} />;
  const e = estado.data;
  const totalPaginas = e.orcamento.paginasHoje + e.orcamento.paginasRestantes;
  return (
    <Card className="shadow-card gap-0 py-0" data-testid="coleta-estado">
      <CardContent className="flex flex-wrap items-start gap-x-8 gap-y-3 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <Radar className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div>
            <h2 className="font-medium">Estado agora</h2>
            <Badge className={situacaoColetaTone[e.situacao]} data-testid="coleta-situacao">
              {situacaoColetaLabel[e.situacao]}
            </Badge>
          </div>
        </div>
        <dl className="grid flex-1 grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
          <Item rotulo={`Janela (${e.fuso})`}>
            {horaLabel(e.janela.inicio)}–{horaLabel(e.janela.fim)} {e.janela.dentro ? "" : "(fora)"}
          </Item>
          <Item rotulo="Páginas hoje">
            <span className="tabular-nums">
              {e.orcamento.paginasHoje} / {totalPaginas}
            </span>
          </Item>
          <Item rotulo="Imagens hoje">
            <span className="tabular-nums">{e.orcamento.imagensHoje}</span>
          </Item>
          <Item rotulo="Fila de hoje">
            <span className="tabular-nums">
              {e.hoje.recebidas} recebidas · {e.hoje.pendentes} pendentes · {e.hoje.falhadas} falhas
            </span>
          </Item>
          <Item rotulo="Rodada atual">{e.rodadaAtual ? `${rodadaEstadoLabel[e.rodadaAtual.estado]} desde ${formatDateTime(e.rodadaAtual.iniciadaEm)}` : "nenhuma"}</Item>
          <Item rotulo="Último resultado">{e.ultimoResultadoEm ? formatAgo(e.ultimoResultadoEm) : "—"}</Item>
          <Item rotulo="Coletores">
            {e.clientes.length === 0 ? "nenhum" : e.clientes.map((c) => `${c.nome} (${c.ultimoContatoEm ? formatAgo(c.ultimoContatoEm) : "sem contato"})`).join(", ")}
          </Item>
          <Item rotulo="Pausas">{e.pausadaAte ? `pausada até ${formatDateTime(e.pausadaAte)}` : e.continuarEm ? `continua em ${formatDateTime(e.continuarEm)}` : "—"}</Item>
        </dl>
      </CardContent>
    </Card>
  );
}

function Item({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="truncate">{children}</dd>
    </div>
  );
}

function RiscoEInterruptor() {
  const queryClient = useQueryClient();
  const config = useColetaConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [aceitar, setAceitar] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [horas, setHoras] = useState("4");
  const c = config.data;

  async function salvar(fn: () => Promise<ColetaConfig>, msg: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      queryClient.setQueryData(coletaConfigKey, r);
      await invalidarColeta(queryClient);
      toast.success(msg);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (config.isPending) return <p className="text-sm text-muted-foreground" aria-live="polite">Carregando…</p>;
  if (config.isError) return <ApiErrorAlert error={config.error} />;
  if (!c) return null;

  const ligada = c.servidorHabilitado && c.habilitada;
  const estado = !c.servidorHabilitado ? "Desligada no servidor (.env)" : c.habilitada ? "Ligada" : "Desligada";
  return (
    <div className="space-y-3">
      <Alert className={c.riscoAceito ? "" : "border-warning/60 bg-warning/10"} data-testid="coleta-risco">
        <ShieldAlert aria-hidden="true" className={c.riscoAceito ? "" : "text-warning"} />
        <AlertTitle>{c.riscoAceito ? "Risco aceito" : "Antes de ligar: o risco é da conta de afiliado"}</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>{c.textoRisco}</p>
          {c.riscoAceito ? (
            <p className="text-xs text-muted-foreground">
              Aceito em {c.riscoAceitoEm ? formatDateTime(c.riscoAceitoEm) : "—"}
              {c.riscoAceitoPor ? ` por ${c.riscoAceitoPor.name}` : ""} (texto de {c.riscoTextoVersao}).
            </p>
          ) : (
            <Button type="button" size="sm" onClick={() => setAceitar(true)} disabled={busy}>
              Aceito o risco
            </Button>
          )}
        </AlertDescription>
      </Alert>
      <AlertDialog open={aceitar} onOpenChange={setAceitar}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Aceitar o risco da coleta?</AlertDialogTitle>
            <AlertDialogDescription>
              Fica registrado quem aceitou e quando, e só então o interruptor pode ser ligado. A rede pode exigir verificação, limitar ou suspender a conta de
              afiliado do dono, e com ela a comissão. Nada aqui contorna captcha nem login.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void salvar(() => api.coleta.aceitarRisco({ version: c.version, textoVersao: c.textoRiscoVersao, confirmo: true }), "Risco aceito e registrado.")}
            >
              Aceito o risco
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Card className="shadow-card gap-0 py-0">
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-3 py-3">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Radar className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div className="min-w-0">
              <h2 id="coleta-label" className="font-medium">
                Coleta
              </h2>
              <p className="text-sm text-muted-foreground" data-testid="coleta-interruptor-estado">
                {estado}
              </p>
            </div>
            <Switch
              aria-labelledby="coleta-label"
              checked={ligada}
              disabled={busy || !c.servidorHabilitado || !c.riscoAceito}
              onCheckedChange={(on) => void salvar(() => api.coleta.salvarConfig(paraIn(c, { habilitada: on })), on ? "Coleta ligada." : "Coleta desligada: a fila fica vazia para o coletor.")}
            />
          </div>
          <Badge
            className={c.servidorHabilitado ? "bg-success text-success-foreground" : "bg-secondary text-secondary-foreground"}
            title={c.servidorHabilitado ? "COLETA_HABILITADA=true no .env do servidor." : "COLETA_HABILITADA no .env do servidor está desligado."}
          >
            {c.servidorHabilitado ? "Servidor ligado" : "Servidor desligado"}
          </Badge>
          {c.pausadaAte && new Date(c.pausadaAte) > new Date() ? (
            <Badge variant="outline">pausada até {formatDateTime(c.pausadaAte)}</Badge>
          ) : (
            <form
              className="flex items-end gap-2"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void salvar(() => api.coleta.pausar({ version: c.version, horas: Number(horas) || 1 }), `Coleta pausada por ${horas} h.`);
              }}
            >
              <Field label="Pausar por (h)" className="w-28">
                {({ id }) => <Input id={id} type="number" min={1} max={168} value={horas} onChange={(e) => setHoras(e.target.value)} />}
              </Field>
              <Button type="submit" size="sm" variant="outline" disabled={busy || !ligada}>
                <CirclePause aria-hidden="true" />
                Pausar
              </Button>
            </form>
          )}
          <ContinuarBotao busy={busy} onContinuar={() => salvar(() => api.coleta.continuar(c.version), "Coleta continua em alguns minutos.")} />
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
      {!ligada && (
        <Alert className="border-warning/60 bg-warning/10">
          <CirclePause aria-hidden="true" className="text-warning" />
          <AlertTitle>Coleta desligada</AlertTitle>
          <AlertDescription>
            O coletor recebe a fila vazia e fica parado. Nenhuma foto nova entra no lago; o que já foi coletado continua visível.
            {!c.servidorHabilitado && " Para ligar o servidor, quem tem acesso a ele põe COLETA_HABILITADA=true no .env da raiz e reinicia a API e o agendador; esta tela não liga o servidor."}
            {c.servidorHabilitado && !c.riscoAceito && " Aceite o risco acima para liberar o interruptor."}
          </AlertDescription>
        </Alert>
      )}
      {error !== null && <ApiErrorAlert error={error} onReload={() => void config.refetch()} />}
    </div>
  );
}

function ContinuarBotao({ busy, onContinuar }: { busy: boolean; onContinuar: () => Promise<void> }) {
  const estado = useColetaEstado();
  const pausada = estado.data?.situacao === "pausada_captcha" || estado.data?.situacao === "pausada_login" || estado.data?.situacao === "aguardando_continuar";
  if (!pausada) return null;
  return (
    <ConfirmButton
      label="Continuar"
      icon={CirclePlay}
      size="sm"
      busy={busy}
      title="Continuar a coleta?"
      description="Confirme só depois de resolver a verificação ou refazer o login no Chrome do desktop. O coletor espera alguns minutos e retoma a fila."
      onConfirm={onContinuar}
    />
  );
}

function paraIn(c: ColetaConfig, patch: Partial<Omit<ColetaConfig, "version">>) {
  const m = { ...c, ...patch };
  return {
    version: c.version,
    habilitada: m.habilitada,
    janelaInicio: m.janelaInicio,
    janelaFim: m.janelaFim,
    paginasDia: m.paginasDia,
    imagensDia: m.imagensDia,
    imagensPorProduto: m.imagensPorProduto,
    itensPorColeta: m.itensPorColeta,
    pausaMinS: m.pausaMinS,
    pausaMaxS: m.pausaMaxS,
  };
}

function ConfigHistorico() {
  const versions = useQuery({ queryKey: coletaConfigVersionsKey, queryFn: () => api.coleta.configVersions() });
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return (
    <VersionHistory
      versions={versions.data.items}
      labels={coletaConfigFieldLabel}
      formatValue={(field, value) => {
        if (typeof value === "boolean") return value ? "Ligada" : "Desligada";
        if (value === null || value === undefined) return "—";
        if ((field === "risco_aceito_em" || field === "pausada_ate" || field === "continuar_em") && typeof value === "string") return formatDateTime(value);
        return String(value);
      }}
    />
  );
}

function Limites() {
  const queryClient = useQueryClient();
  const config = useColetaConfig();
  const c = config.data;
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!c) return;
    setDraft({
      janelaInicio: String(c.janelaInicio),
      janelaFim: String(c.janelaFim),
      paginasDia: String(c.paginasDia),
      imagensDia: String(c.imagensDia),
      imagensPorProduto: String(c.imagensPorProduto),
      itensPorColeta: String(c.itensPorColeta),
      pausaMinS: String(c.pausaMinS),
      pausaMaxS: String(c.pausaMaxS),
    });
  }, [c]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!c) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.coleta.salvarConfig({
        version: c.version,
        habilitada: c.habilitada,
        janelaInicio: Number(draft.janelaInicio),
        janelaFim: Number(draft.janelaFim),
        paginasDia: Number(draft.paginasDia),
        imagensDia: Number(draft.imagensDia),
        imagensPorProduto: Number(draft.imagensPorProduto),
        itensPorColeta: Number(draft.itensPorColeta),
        pausaMinS: Number(draft.pausaMinS),
        pausaMaxS: Number(draft.pausaMaxS),
      });
      queryClient.setQueryData(coletaConfigKey, r);
      await invalidarColeta(queryClient);
      toast.success("Limites salvos. O coletor aplica o menor entre estes e os locais.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setDraft((d) => ({ ...d, [k]: e.target.value }));

  return (
    <HeaderCard title="Janela, tetos e pausas" description="O ritmo humano é ditado daqui: o coletor nunca passa destes limites.">
      {config.isError && <ApiErrorAlert error={config.error} />}
      <form onSubmit={(e) => void submit(e)} className="grid gap-4 sm:grid-cols-2">
        <Field label="Janela: início">
          {({ id }) => (
            <NativeSelect id={id} value={draft.janelaInicio ?? "8"} onChange={set("janelaInicio")}>
              {HORAS.map((h) => (
                <option key={h} value={h}>
                  {horaLabel(h)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Janela: fim (inclusivo)">
          {({ id }) => (
            <NativeSelect id={id} value={draft.janelaFim ?? "23"} onChange={set("janelaFim")}>
              {HORAS.map((h) => (
                <option key={h} value={h}>
                  {horaLabel(h)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Páginas por dia" hint="1 a 2000; padrão 300">
          {({ id }) => <Input id={id} type="number" min={1} max={2000} value={draft.paginasDia ?? ""} onChange={set("paginasDia")} />}
        </Field>
        <Field label="Imagens por dia" hint="0 a 20000; padrão 1500">
          {({ id }) => <Input id={id} type="number" min={0} max={20000} value={draft.imagensDia ?? ""} onChange={set("imagensDia")} />}
        </Field>
        <Field label="Imagens por produto" hint="0 a 20; padrão 9">
          {({ id }) => <Input id={id} type="number" min={0} max={20} value={draft.imagensPorProduto ?? ""} onChange={set("imagensPorProduto")} />}
        </Field>
        <Field label="Itens por rodada" hint="1 a 50; padrão 40">
          {({ id }) => <Input id={id} type="number" min={1} max={50} value={draft.itensPorColeta ?? ""} onChange={set("itensPorColeta")} />}
        </Field>
        <Field label="Pausa mínima (s)" hint="entre páginas; padrão 5">
          {({ id }) => <Input id={id} type="number" min={1} max={600} value={draft.pausaMinS ?? ""} onChange={set("pausaMinS")} />}
        </Field>
        <Field label="Pausa máxima (s)" hint="padrão 40">
          {({ id }) => <Input id={id} type="number" min={1} max={600} value={draft.pausaMaxS ?? ""} onChange={set("pausaMaxS")} />}
        </Field>
        {error !== null && (
          <div className="sm:col-span-2">
            <ApiErrorAlert error={error} onReload={() => void config.refetch()} />
          </div>
        )}
        <div className="sm:col-span-2">
          <Button type="submit" disabled={busy || !c} aria-busy={busy}>
            Salvar limites
          </Button>
        </div>
      </form>
    </HeaderCard>
  );
}

function Coletores() {
  const clientes = useColetaClientes();
  const [novo, setNovo] = useState(false);
  const [criado, setCriado] = useState<{ nome: string; token: string } | null>(null);
  return (
    <HeaderCard
      title="Coletores"
      description="Um token por desktop. Guarde-o em ~/.config/sociman-coletor/token (modo 600) no computador que roda o Chrome."
      actions={
        <Button type="button" variant="secondary" size="sm" onClick={() => setNovo(true)}>
          <Plus aria-hidden="true" />
          Novo coletor
        </Button>
      }
    >
      {clientes.isError && <ApiErrorAlert error={clientes.error} />}
      <ClientesColetaTable clientes={clientes.data?.itens} loading={clientes.isPending} />
      <NovoColetorDialog open={novo} onOpenChange={setNovo} onCriado={(c, token) => setCriado({ nome: c.nome, token })} />
      <TokenUmaVezDialog token={criado?.token ?? null} nome={criado?.nome ?? ""} onClose={() => setCriado(null)} />
    </HeaderCard>
  );
}

const colR = dataTableColumns<ColetaResumoRodada>();
const colunasRodadas = colR.columns([
  colR.accessor("iniciadaEm", { header: "Início", cell: (c) => <span className="whitespace-nowrap">{formatDateTime(c.getValue())}</span> }),
  colR.accessor((r) => rodadaEstadoLabel[r.estado], { id: "estado", header: "Estado", cell: (c) => <Badge variant="outline">{c.getValue()}</Badge> }),
  colR.accessor("paginas", { header: () => <span className="block text-right">Páginas</span>, cell: (c) => <span className="block text-right tabular-nums">{c.getValue()}</span> }),
  colR.accessor("imagens", { header: () => <span className="block text-right">Imagens</span>, cell: (c) => <span className="block text-right tabular-nums">{c.getValue()}</span> }),
  colR.accessor((r) => `${r.itensOk} / ${r.itensRepetidos} / ${r.itensErro}`, { id: "itens", header: () => <span className="block text-right">ok / repetidos / erros</span>, cell: (c) => <span className="block text-right tabular-nums">{c.getValue()}</span> }),
  colR.accessor((r) => r.terminadaEm ?? "", { id: "fim", header: "Fim", cell: (c) => <span className="whitespace-nowrap">{c.row.original.terminadaEm ? formatDateTime(c.row.original.terminadaEm) : "em andamento"}</span> }),
]);

function Rodadas() {
  const coletas = useColetaColetas();
  return (
    <HeaderCard title="Rodadas recentes" description="Cada rodada é uma sessão do coletor; o detalhe lista os itens e os eventos.">
      {coletas.isError && <ApiErrorAlert error={coletas.error} />}
      <DataTable columns={colunasRodadas} data={coletas.data?.itens ?? []} loading={coletas.isPending} getRowId={(r) => r.id} label="Rodadas" empty={<p className="text-sm text-muted-foreground">Nenhuma rodada ainda.</p>} />
    </HeaderCard>
  );
}

const colE = dataTableColumns<ColetaEvento>();
const colunasEventos = colE.columns([
  colE.accessor("ocorreuEm", { header: "Quando", cell: (c) => <span className="whitespace-nowrap">{formatDateTime(c.getValue())}</span> }),
  colE.accessor((e) => eventoTipoLabel[e.tipo], { id: "tipo", header: "Evento", cell: (c) => <Badge variant="outline">{c.getValue()}</Badge> }),
  colE.accessor((e) => (e.notificado ? "sim" : "não"), { id: "notificado", header: "Avisou" }),
]);

function Eventos() {
  const eventos = useColetaEventos();
  return (
    <HeaderCard title="Eventos recentes" description="Verificação, login perdido, bloqueio e mudança de página param a coleta e avisam no sino.">
      {eventos.isError && <ApiErrorAlert error={eventos.error} />}
      <DataTable columns={colunasEventos} data={eventos.data?.itens ?? []} loading={eventos.isPending} getRowId={(e) => String(e.id)} label="Eventos" empty={<p className="text-sm text-muted-foreground">Nenhum evento.</p>} />
    </HeaderCard>
  );
}

function Guia() {
  return (
    <HeaderCard title="Instalação no desktop" description="Resumo; o passo a passo completo está no README do coletor (apps/coletor/README.md).">
      <ol className="list-decimal space-y-1 pl-5 text-sm">
        <li>No desktop com o Chrome, instale o coletor e rode uma vez para criar o perfil dedicado e fazer o login na conta de afiliado.</li>
        <li>Crie um coletor acima, copie o token uma vez e grave em ~/.config/sociman-coletor/token (modo 600), com a URL da API e a CA da casa.</li>
        <li>Aceite o risco, ligue a coleta e rode uma coleta de teste com poucos itens antes de deixar o serviço de usuário ligado.</li>
        <li>Para parar tudo no desktop sem passar por aqui, crie o arquivo ~/.config/sociman-coletor/PARAR ou pare o serviço.</li>
      </ol>
    </HeaderCard>
  );
}
