/*
 * /app/vozes/:id (spec 025, US2/US3; T028, T036; FR-031): o cadastro de uma voz do perfil.
 * Gravação: consentimento → enviar a gravação → análise com avisos → até 3 candidatos (com áudio de
 * teste, duração, transcrição e similaridade) → "Usar opção N" aprova a voz e o SociMan a envia ao
 * shop-tts ("Sincronizada em …"). Sintética: a descrição em inglês e os candidatos. Depois: "Testar"
 * com um texto livre, "Usada por" (os avatares com esta voz padrão), arquivar/restaurar, revogar (só
 * dono, na gravação) e o histórico. Recarrega a cada 2 s enquanto algo anda sozinho.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, Loader2, Sparkles, TriangleAlert, Upload } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { GeracaoAberta } from "@/components/geracao/GeracaoAberta";
import { PlayerAudio } from "@/components/geracao/PlayerAudio";
import { Page, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { Skeleton } from "@/components/ui/skeleton";
import { HistoryHeading, VersionHistory } from "@/components/VersionHistory";
import { api } from "@/lib/api";
import { geracoesApi, useCriarGeracao } from "@/lib/geracoes";
import { metaDetalhe, rotaEstudio } from "@/lib/estudio";
import { formatDateTime } from "@/lib/tz";
import {
  AUDIO_ACCEPT,
  AUDIO_MAX_BYTES,
  fmtNum,
  formatVozValue,
  invalidarVoz,
  origemVozLabel,
  sincronizacaoLabel,
  statusVozLabel,
  statusVozTone,
  useVoz,
  useVozVersoes,
  vozFieldLabel,
  vozKey,
  type Voz,
} from "@/lib/vozes";
import { PerfilBaseEditavel } from "@/components/estudio/PerfilBaseEditavel";
import { PerfilBaseGeracao } from "@/components/estudio/PerfilBaseField";
import { ConsentimentoCard } from "../assets/kit/ConsentimentoCard";
import { PedirPasso } from "../assets/kit/PedirPasso";

export default function VozDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const detail = useVoz(id);
  const voz = detail.data;
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  usePageMeta({ title: voz?.name ?? "Voz", ...metaDetalhe("vozes", voz?.perfilId) });
  const refresh = () => invalidarVoz(queryClient, id);

  if (detail.isPending) {
    return (
      <Page aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </Page>
    );
  }
  if (detail.isError || !voz) {
    return (
      <Page>
        <Voltar perfilId={null} />
        <ApiErrorAlert error={detail.error} />
      </Page>
    );
  }

  const v = voz;
  const travado = v.archived || v.revogada;
  const sincronizada = v.sincronizacao === "ok" && v.sincronizadaEm;

  async function arquivar() {
    setBusy(true);
    setError(null);
    try {
      await (v.archived ? api.vozes.restaurar(v.id, v.version) : api.vozes.arquivar(v.id, v.version));
      toast.success(v.archived ? "Voz restaurada." : "Voz arquivada.");
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page>
      <Voltar perfilId={v.perfilId} />

      <Card className="shadow-card">
        <CardContent className="flex flex-wrap items-center gap-4">
          <div className="min-w-0 flex-1 space-y-1">
            <h1 className="text-xl font-bold break-words sm:text-2xl">{v.name}</h1>
            <p className="text-sm text-muted-foreground">{v.tom}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge className={statusVozTone[v.status]} data-testid="voz-status">
                {statusVozLabel[v.status]}
              </Badge>
              <Badge variant="outline">{origemVozLabel[v.origem]}</Badge>
              {v.trocandoReferencia && <Badge variant="secondary">Trocando a referência</Badge>}
              {v.revogada && <Badge className="bg-dark text-dark-foreground" data-testid="voz-revogada">Revogada</Badge>}
              {v.archived && !v.revogada && <Badge className="bg-dark text-dark-foreground">Arquivada</Badge>}
              {v.referencia && (
                <Badge variant={sincronizada ? "secondary" : "outline"} data-testid="voz-sincronizacao">
                  {sincronizada ? `Sincronizada em ${formatDateTime(v.sincronizadaEm!)}` : sincronizacaoLabel[v.sincronizacao]}
                </Badge>
              )}
            </div>
            <PerfilBaseEditavel
              valor={v.perfilId ?? null}
              disabled={travado}
              onSalvar={async (perfilId) => {
                const nova = await api.vozes.editar(v.id, { version: v.version, perfilId });
                queryClient.setQueryData(vozKey(v.id), nova);
                await refresh();
              }}
            />
          </div>
          <ConfirmButton
            label={v.archived ? "Restaurar" : "Arquivar"}
            icon={v.archived ? ArchiveRestore : Archive}
            busy={busy}
            disabled={v.revogada}
            title={v.archived ? `Restaurar ${v.name}?` : `Arquivar ${v.name}?`}
            description={
              v.archived
                ? "A voz volta para a lista e para o seletor de voz padrão."
                : v.usadaPor.length > 0
                  ? `A voz é padrão de ${v.usadaPor.map((a) => a.name).join(", ")}; esses avatares vão mostrar "Voz padrão arquivada". Nada é apagado.`
                  : "A voz sai da lista e do seletor de voz padrão. Nada é apagado."
            }
            onConfirm={arquivar}
          />
        </CardContent>
      </Card>

      {error !== null && <ApiErrorAlert error={error} onReload={() => void refresh().then(() => setError(null))} />}

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="flex min-w-0 flex-col gap-6">
          {v.origem === "gravacao" ? <GravacaoCard voz={v} onMudou={refresh} /> : <SinteticaCard voz={v} />}
          {v.analise && <AnaliseCard voz={v} />}
          <CandidatosCard voz={v} />
          <TesteCard voz={v} />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          {v.origem === "gravacao" && (
            <ConsentimentoCard
              perfilId={v.perfilId}
              consentimento={v.consentimento}
              revogado={v.revogada}
              descricao="A voz vem da gravação de uma pessoa real: registre o consentimento dela antes de gerar os candidatos."
              oQue="a gravação"
              onRegistrar={async (body) => {
                const nova = await api.vozes.consentimentoRegistrar(v.id, { version: v.version, ...body });
                queryClient.setQueryData(vozKey(v.id), nova);
                toast.success("Consentimento registrado.");
                await refresh();
              }}
              onRevogar={async () => {
                const r = await api.vozes.consentimentoRevogar(v.id, v.version);
                queryClient.setQueryData(vozKey(v.id), r.voz);
                toast.success("Consentimento revogado. Os áudios da pessoa foram apagados.");
                await refresh();
              }}
            />
          )}
          <Card className="shadow-card" aria-labelledby="usada-por-titulo">
            <CardHeader>
              <CardTitle>
                <h2 id="usada-por-titulo">Usada por</h2>
              </CardTitle>
              <CardDescription>Os avatares que têm esta voz como voz padrão.</CardDescription>
            </CardHeader>
            <CardContent>
              {v.usadaPor.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum avatar usa esta voz.</p>
              ) : (
                <ul className="space-y-1 text-sm" aria-label="Usada por" data-testid="voz-usada-por">
                  {v.usadaPor.map((a) => (
                    <li key={a.id}>
                      <Link to={`/app/assets/${a.id}`} className="font-medium underline-offset-2 hover:underline">
                        {a.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
          {travado && (
            <p className="text-sm text-muted-foreground">{v.revogada ? "Voz revogada: não pode ser usada nem restaurada." : "Restaure a voz para gerar ou testar."}</p>
          )}
        </div>
      </div>

      <HistoricoVoz voz={v} onReload={refresh} />
    </Page>
  );
}

function Voltar({ perfilId }: { perfilId: string | null }) {
  return (
    <Button type="button" variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground" asChild>
      <Link to={rotaEstudio("vozes", perfilId)}>
        <ArrowLeft aria-hidden="true" />
        Voltar para as vozes
      </Link>
    </Button>
  );
}

// Gravação: enviar (ou trocar) o áudio e pedir os candidatos (`voz.gravacao`).
function GravacaoCard({ voz, onMudou }: { voz: Voz; onMudou: () => Promise<void> }) {
  const queryClient = useQueryClient();
  const criar = useCriarGeracao();
  const [perfilBase, setPerfilBase] = useState<string | null>(voz.perfilId ?? null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [progresso, setProgresso] = useState<number | null>(null);
  const [erroArquivo, setErroArquivo] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const travado = voz.archived || voz.revogada;
  const semConsentimento = !voz.consentimento?.registradoEm;
  const aberta = voz.geracaoAberta !== null;

  async function enviar() {
    if (!arquivo) return;
    if (arquivo.size > AUDIO_MAX_BYTES) {
      setErroArquivo("Gravação maior que 25 MB.");
      return;
    }
    setErroArquivo(null);
    setError(null);
    setProgresso(0);
    try {
      const audio = await geracoesApi.enviarAudio(voz.perfilId, arquivo, setProgresso);
      const nova = await api.vozes.editar(voz.id, { version: voz.version, gravacaoAudioId: audio.id });
      queryClient.setQueryData(vozKey(voz.id), nova);
      setArquivo(null);
      setInputKey((k) => k + 1);
      toast.success("Gravação enviada. Agora gere os candidatos.");
      await onMudou();
    } catch (err) {
      setError(err);
    } finally {
      setProgresso(null);
    }
  }

  async function gerar() {
    try {
      await criar.mutateAsync({ alvoTipo: "voz", alvoId: voz.id, passo: "voz.gravacao", instrucao: "", perfilBaseId: perfilBase });
      toast.success("Candidatos pedidos. Eles aparecem abaixo quando ficarem prontos.");
    } catch {
      // erro no alerta
    }
  }

  return (
    <Card className="shadow-card" aria-labelledby="gravacao-titulo" data-testid="voz-gravacao">
      <CardHeader>
        <CardTitle>
          <h2 id="gravacao-titulo">{voz.referencia ? "Trocar referência" : "Gravação"}</h2>
        </CardTitle>
        <CardDescription>
          Recomendado: 15 a 30 s, 2 a 4 frases completas no tom de venda, com uma pausa entre elas, num lugar silencioso. Áudio do
          WhatsApp funciona, mas sai comprimido (a análise avisa).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {voz.gravacao && (
          <div className="space-y-1">
            <p className="text-sm font-medium">Gravação atual</p>
            <PlayerAudio audio={voz.gravacao} rotulo="Gravação atual" onRenovar={() => void onMudou()} />
          </div>
        )}
        {semConsentimento && !travado && (
          <Alert>
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>Falta o consentimento</AlertTitle>
            <AlertDescription>Registre o consentimento da pessoa em "Origem e consentimento" antes de gerar os candidatos.</AlertDescription>
          </Alert>
        )}
        {!travado && !aberta && (
          <>
            <PerfilBaseGeracao value={perfilBase} onChange={setPerfilBase} />
            <Field label="Arquivo da gravação" error={erroArquivo ?? undefined} hint="WAV, M4A, OGG ou MP3, até 25 MB.">
              {({ id, describedBy }) => (
                <FileField key={inputKey} id={id} accept={AUDIO_ACCEPT} aria-describedby={describedBy} onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
              )}
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" disabled={!arquivo || progresso !== null} aria-busy={progresso !== null} onClick={() => void enviar()}>
                {progresso !== null ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
                {progresso !== null ? `Enviando ${Math.round(progresso * 100)}%` : "Enviar gravação"}
              </Button>
              <Button type="button" disabled={!voz.gravacao || criar.isPending} aria-busy={criar.isPending} onClick={() => void gerar()}>
                {criar.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
                Gerar candidatos
              </Button>
            </div>
          </>
        )}
        {error !== null && <ApiErrorAlert error={error} />}
        {criar.isError && <ApiErrorAlert error={criar.error} />}
      </CardContent>
    </Card>
  );
}

// Sintética: a descrição (inglês) e o pedido dos candidatos (`voz.design`).
function SinteticaCard({ voz }: { voz: Voz }) {
  const travado = voz.archived || voz.revogada;
  return (
    <Card className="shadow-card" aria-labelledby="sintetica-titulo" data-testid="voz-sintetica">
      <CardHeader>
        <CardTitle>
          <h2 id="sintetica-titulo">{voz.referencia ? "Trocar referência" : "Voz sintética"}</h2>
        </CardTitle>
        <CardDescription>Os candidatos saem da descrição da voz, sem limpeza de ruído.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {voz.descricao && (
          <p className="rounded-lg bg-muted/50 p-3 text-sm" lang="en">
            {voz.descricao}
          </p>
        )}
        {!travado && !voz.geracaoAberta && (
          <PedirPasso
            perfilId={voz.perfilId}
            alvoTipo="voz"
            alvoId={voz.id}
            passo="voz.design"
            instrucao={{ label: "Texto falado (opcional)", hint: "Vazio: uma fala de vendas de uns 12 s.", lang: "pt-BR" }}
            submitLabel="Gerar candidatos"
          />
        )}
      </CardContent>
    </Card>
  );
}

function AnaliseCard({ voz }: { voz: Voz }) {
  const a = voz.analise!;
  const avisos = a.avisos ?? [];
  return (
    <Card className="shadow-card" aria-labelledby="analise-titulo" data-testid="voz-analise">
      <CardHeader>
        <CardTitle>
          <h2 id="analise-titulo">Análise da gravação</h2>
        </CardTitle>
        <CardDescription>Os avisos não bloqueiam: ajudam a decidir se vale gravar de novo.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {avisos.length > 0 && (
          <ul className="space-y-1 text-sm" aria-label="Avisos da análise" data-testid="analise-avisos">
            {avisos.map((av, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
                {av}
              </li>
            ))}
          </ul>
        )}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
          <Metrica rotulo="Codec" valor={a.codec ?? "—"} />
          <Metrica rotulo="Bitrate" valor={a.bitrate ? `${Math.round(a.bitrate / 1000)} kbps` : "—"} />
          <Metrica rotulo="Amostragem" valor={a.sampleRate ? `${fmtNum(a.sampleRate / 1000)} kHz` : "—"} />
          <Metrica rotulo="Duração" valor={fmtNum(a.duracaoS, " s")} />
          <Metrica rotulo="Piso de ruído" valor={fmtNum(a.pisoRuidoDbfs, " dBFS")} />
          <Metrica rotulo="SNR" valor={fmtNum(a.snrDb, " dB")} />
          <Metrica rotulo="Clipping" valor={fmtNum(a.clippingPct, "%")} />
        </dl>
      </CardContent>
    </Card>
  );
}

function Metrica({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="tabular-nums">{valor}</dd>
    </div>
  );
}

// Candidatos (a geração aberta da voz) e a referência aprovada.
function CandidatosCard({ voz }: { voz: Voz }) {
  const queryClient = useQueryClient();
  const travado = voz.archived || voz.revogada;
  if (!voz.geracaoAberta && !voz.referencia) return null;
  return (
    <Card className="shadow-card" aria-labelledby="candidatos-titulo" data-testid="voz-candidatos">
      <CardHeader>
        <CardTitle>
          <h2 id="candidatos-titulo">Referência</h2>
        </CardTitle>
        <CardDescription>Cada candidato tem 8 a 13 s, cortado no começo e no fim de uma frase, e um áudio de teste com 2 frases de venda.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {voz.geracaoAberta && (
          <GeracaoAberta
            resumo={voz.geracaoAberta}
            alvoVersion={voz.version}
            titulo="Candidatos"
            disabled={travado}
            onEscolhido={() => void invalidarVoz(queryClient, voz.id)}
          />
        )}
        {voz.referencia && (
          <div className="space-y-1.5" data-testid="voz-referencia">
            <p className="text-sm font-medium">Referência aprovada</p>
            <PlayerAudio audio={voz.referencia} rotulo="Referência aprovada" onRenovar={() => void invalidarVoz(queryClient, voz.id)} />
            {voz.refTexto && <p className="text-sm text-muted-foreground italic">“{voz.refTexto}”</p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// "Testar": narra um texto livre com a voz (`voz.teste`); só com a voz sincronizada.
function TesteCard({ voz }: { voz: Voz }) {
  if (voz.status !== "aprovada" && !voz.referencia) return null;
  const travado = voz.archived || voz.revogada;
  const sincronizada = voz.sincronizacao === "ok";
  const andando = voz.ultimoTeste && (voz.ultimoTeste.status === "na_fila" || voz.ultimoTeste.status === "rodando");
  return (
    <Card className="shadow-card" aria-labelledby="teste-titulo" data-testid="voz-teste">
      <CardHeader>
        <CardTitle>
          <h2 id="teste-titulo">Testar</h2>
        </CardTitle>
        <CardDescription>Escreva um texto e ouça a narração com esta voz.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!sincronizada && <p className="text-sm text-muted-foreground">O teste fica disponível quando a voz estiver sincronizada com o serviço de voz.</p>}
        {sincronizada && !travado && !andando && (
          <PedirPasso
            perfilId={voz.perfilId}
            alvoTipo="voz"
            alvoId={voz.id}
            passo="voz.teste"
            texto={{ label: "Texto do teste", hint: "Até 500 caracteres." }}
            submitLabel="Testar"
          />
        )}
        {voz.ultimoTeste && <GeracaoAberta resumo={voz.ultimoTeste} titulo="Último teste" disabled={travado} />}
      </CardContent>
    </Card>
  );
}

function HistoricoVoz({ voz, onReload }: { voz: Voz; onReload: () => Promise<unknown> }) {
  const versoes = useVozVersoes(voz.id);
  return (
    <Card className="shadow-card">
      <CardHeader>
        <HistoryHeading>Histórico</HistoryHeading>
        <CardDescription>Da versão mais recente para a mais antiga. Reverter (só o dono) cria uma versão nova.</CardDescription>
      </CardHeader>
      <CardContent>
        {versoes.isPending && (
          <p aria-live="polite" className="text-sm text-muted-foreground">
            Carregando…
          </p>
        )}
        {versoes.isError && <ApiErrorAlert error={versoes.error} />}
        {versoes.data && (
          <VersionHistory
            versions={versoes.data.items}
            labels={vozFieldLabel}
            formatValue={formatVozValue}
            onRevert={
              voz.revogada
                ? undefined
                : async (toVersion) => {
                    await api.vozes.reverter(voz.id, voz.version, toVersion);
                    await onReload();
                  }
            }
            onReload={async () => {
              await onReload();
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}
