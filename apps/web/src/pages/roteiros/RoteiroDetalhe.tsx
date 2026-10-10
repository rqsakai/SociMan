/*
 * /app/roteiros/:id (spec 011): o roteiro com vídeo local. Cabeçalho com o estado, o perfil, os
 * produtos, o avatar e a voz, e as ações (planejar com IA, tentar de novo, arquivar/restaurar); o erro
 * e os avisos; os portões e o modo (T048); as etapas Texto, Narração, Keyframes, Clipes e Final, em
 * abas (`?etapa=`; sem ela, a etapa onde o roteiro está); e o histórico (reverter só o dono). O
 * `useRoteiro` recarrega a cada 2 s enquanto o roteiro trabalha sozinho.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, Loader2, RotateCcw, Sparkles, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Portoes } from "@/components/roteiro/Portoes";
import { Page, usePageMeta } from "@/components/shell";
import { HistoryHeading, VersionHistory } from "@/components/VersionHistory";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { metaDetalhe, rotaEstudio } from "@/lib/estudio";
import {
  ETAPAS,
  etapaAtual,
  etapaFalhouLabel,
  formatRoteiroValue,
  invalidarRoteiro,
  modoLabel,
  portaoParado,
  roteiroFieldLabel,
  roteiroKey,
  statusRoteiroLabel,
  statusRoteiroTone,
  useRoteiro,
  useRoteiroVersoes,
  type Etapa,
  type Roteiro,
} from "@/lib/roteiros";
import { Andamentos, type RodarRoteiro } from "./etapas/comum";
import { Clipes } from "./etapas/Clipes";
import { Final } from "./etapas/Final";
import { Keyframes } from "./etapas/Keyframes";
import { Narracao } from "./etapas/Narracao";
import { Texto } from "./etapas/Texto";

const PLANEJAVEL = new Set(["rascunho", "aguardando_texto"]);

export default function RoteiroDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const detalhe = useRoteiro(id);
  const r = detalhe.data;
  const [error, setError] = useState<unknown>(null);
  usePageMeta({ title: r?.nome ?? "Vídeo", ...metaDetalhe("videos", r?.perfilId) });

  const rodar: RodarRoteiro = async (acao, ok) => {
    setError(null);
    try {
      const novo = await acao();
      if (novo && typeof novo === "object" && "posicoes" in novo) queryClient.setQueryData(roteiroKey(id), novo);
      toast.success(ok);
      await invalidarRoteiro(queryClient, id);
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  };

  if (detalhe.isPending) {
    return (
      <Page aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </Page>
    );
  }
  if (detalhe.isError || !r) {
    return (
      <Page>
        <Voltar perfilId={null} />
        <ApiErrorAlert error={detalhe.error} />
      </Page>
    );
  }
  return <RoteiroTela r={r} rodar={rodar} error={error} onReload={() => void invalidarRoteiro(queryClient, id).then(() => setError(null))} />;
}

function Voltar({ perfilId }: { perfilId: string | null }) {
  return (
    <Button type="button" variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground" asChild>
      <Link to={rotaEstudio("videos", perfilId)}>
        <ArrowLeft aria-hidden="true" />
        Voltar para os vídeos
      </Link>
    </Button>
  );
}

function RoteiroTela({ r, rodar, error, onReload }: { r: Roteiro; rodar: RodarRoteiro; error: unknown; onReload: () => void }) {
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState<string | null>(null);
  const [salvandoPortoes, setSalvandoPortoes] = useState(false);
  const etapaUrl = params.get("etapa");
  const etapa: Etapa = ETAPAS.some((e) => e.id === etapaUrl) ? (etapaUrl as Etapa) : etapaAtual(r);
  const atual = etapaAtual(r);
  const travado = r.arquivado;
  const podePlanejar = !travado && (PLANEJAVEL.has(r.status) || (r.status === "falhou" && r.etapaFalhou === "plano"));

  async function acao(nome: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(nome);
    await rodar(fn, ok);
    setBusy(null);
  }

  return (
    <Page>
      <Voltar perfilId={r.perfilId} />

      <Card className="shadow-card">
        <CardContent className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1 space-y-1.5">
            <h1 className="text-xl font-bold break-words sm:text-2xl">{r.nome}</h1>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge className={statusRoteiroTone[r.status]} data-testid="roteiro-status">
                {statusRoteiroLabel[r.status]}
              </Badge>
              {r.status === "falhou" && r.etapaFalhou && <span className="text-xs text-muted-foreground">em {etapaFalhouLabel[r.etapaFalhou]}</span>}
              {r.arquivado && <Badge className="bg-dark text-dark-foreground">Arquivado</Badge>}
              <Badge variant="outline">{r.perfilNome ?? "Perfil"}</Badge>
              <Badge variant="outline">Modo {modoLabel[r.modo].toLowerCase()}</Badge>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm" data-testid="roteiro-pecas">
              <dt className="text-muted-foreground">Produtos</dt>
              <dd className="break-words">
                {r.produtos.map((p, i) => (
                  <span key={p.produtoId}>
                    {i > 0 && " · "}
                    <Link to={`/app/produtos/${p.produtoId}`} className="underline-offset-2 hover:underline">
                      {p.nomeComercial ?? p.nome}
                    </Link>
                    {p.cor && ` (${p.cor})`}
                    {!p.aprovado && <span className="text-warning-foreground"> fora de aprovado</span>}
                  </span>
                ))}
              </dd>
              <dt className="text-muted-foreground">Avatar</dt>
              <dd>
                {r.avatar ? (
                  <Link to={`/app/assets/${r.avatar.id}`} className="underline-offset-2 hover:underline">
                    {r.avatar.nome}
                  </Link>
                ) : (
                  "Sem avatar (só produto)"
                )}
                {r.avatar?.revogado && <span className="text-destructive"> · revogado</span>}
              </dd>
              <dt className="text-muted-foreground">Voz</dt>
              <dd>
                {r.voz ? (
                  <Link to={`/app/vozes/${r.voz.id}`} className="underline-offset-2 hover:underline">
                    {r.voz.nome}
                  </Link>
                ) : (
                  "Sem voz"
                )}
                {r.voz?.revogada && <span className="text-destructive"> · revogada</span>}
              </dd>
            </dl>
          </div>
          <div className="flex flex-wrap gap-2">
            {podePlanejar && (
              <Button type="button" disabled={busy !== null} aria-busy={busy === "planejar"} onClick={() => void acao("planejar", () => api.roteiros.planejar(r.id, r.version), "Plano pedido à IA.")}>
                {busy === "planejar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
                {r.posicoes.length > 0 ? "Planejar de novo com IA" : "Planejar com IA"}
              </Button>
            )}
            {!travado && r.status === "falhou" && (
              <Button
                type="button"
                variant="outline"
                disabled={busy !== null}
                aria-busy={busy === "tentar"}
                onClick={() => void acao("tentar", () => api.roteiros.tentarDeNovo(r.id, r.version), "O roteiro tenta a etapa de novo.")}
              >
                {busy === "tentar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
                Tentar de novo
              </Button>
            )}
            <ConfirmButton
              label={r.arquivado ? "Restaurar" : "Arquivar"}
              icon={r.arquivado ? ArchiveRestore : Archive}
              busy={busy === "arquivo"}
              title={r.arquivado ? `Restaurar ${r.nome}?` : `Arquivar ${r.nome}?`}
              description={
                r.arquivado
                  ? "O roteiro volta para a lista e segue de onde parou."
                  : "O roteiro sai da lista e as gerações abertas dele são canceladas. Nada é apagado."
              }
              onConfirm={() =>
                void acao(
                  "arquivo",
                  () => (r.arquivado ? api.roteiros.restaurar(r.id, r.version) : api.roteiros.arquivar(r.id, r.version)),
                  r.arquivado ? "Roteiro restaurado." : "Roteiro arquivado.",
                )
              }
            />
          </div>
        </CardContent>
      </Card>

      {error !== null && <ApiErrorAlert error={error} onReload={onReload} />}
      {r.status === "falhou" && r.erro && (
        <Alert variant="destructive" data-testid="roteiro-erro">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Falhou {r.etapaFalhou ? `em ${etapaFalhouLabel[r.etapaFalhou]}` : ""}</AlertTitle>
          <AlertDescription>{r.erro.message}</AlertDescription>
        </Alert>
      )}
      {r.avisos.length > 0 && (
        <Alert data-testid="roteiro-avisos">
          <TriangleAlert className="text-warning" aria-hidden="true" />
          <AlertTitle>Avisos</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {r.avisos.map((a, i) => (
                <li key={`${a.code}-${i}`}>
                  {a.ordem != null && `Cena ${a.ordem + 1}: `}
                  {a.message}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Card className="shadow-card" aria-labelledby="portoes-titulo">
        <CardHeader>
          <h2 id="portoes-titulo" className="text-base font-semibold">
            Portões
          </h2>
          <CardDescription>Onde o roteiro para para você revisar. Mudar vale na hora; desligar o portão em que ele está parado aprova a etapa.</CardDescription>
        </CardHeader>
        <CardContent>
          <Portoes
            modo={r.modo}
            portoes={r.portoes}
            paradoEm={portaoParado(r.status)}
            disabled={travado || salvandoPortoes}
            salvando={salvandoPortoes}
            onChange={async (v) => {
              setSalvandoPortoes(true);
              await rodar(() => api.roteiros.controle(r.id, { version: r.version, ...v }), "Portões salvos.");
              setSalvandoPortoes(false);
            }}
          />
        </CardContent>
      </Card>

      <Andamentos geracoes={r.geracoesAbertas} filtro={(g) => g.passo === "roteiro.plano" && etapa !== "texto"} />

      <Tabs value={etapa} onValueChange={(v) => setParams(v === atual ? {} : { etapa: v }, { replace: true })}>
        <TabsList aria-label="Etapas do vídeo" className="flex-wrap">
          {ETAPAS.map((e, i) => (
            <TabsTrigger key={e.id} value={e.id} data-testid={`aba-etapa-${e.id}`}>
              {i + 1}. {e.rotulo}
              {e.id === atual && r.status !== "pronto" && <span className="ml-1 size-1.5 rounded-full bg-primary" aria-label="etapa atual" />}
            </TabsTrigger>
          ))}
        </TabsList>
        <Card className="shadow-card">
          <CardContent>
            <TabsContent value="texto">
              <Texto key={`texto-${r.id}`} roteiro={r} rodar={rodar} travado={travado} />
            </TabsContent>
            <TabsContent value="narracao">
              <Narracao key={`narracao-${r.version}`} roteiro={r} rodar={rodar} travado={travado} />
            </TabsContent>
            <TabsContent value="keyframes">
              <Keyframes roteiro={r} rodar={rodar} travado={travado} />
            </TabsContent>
            <TabsContent value="clipes">
              <Clipes roteiro={r} rodar={rodar} travado={travado} />
            </TabsContent>
            <TabsContent value="final">
              <Final roteiro={r} rodar={rodar} travado={travado} />
            </TabsContent>
          </CardContent>
        </Card>
      </Tabs>

      <HistoricoRoteiro roteiro={r} onReload={onReload} />
    </Page>
  );
}

function HistoricoRoteiro({ roteiro, onReload }: { roteiro: Roteiro; onReload: () => void }) {
  const queryClient = useQueryClient();
  const versoes = useRoteiroVersoes(roteiro.id);
  return (
    <Card className="shadow-card">
      <CardHeader>
        <HistoryHeading>Histórico</HistoryHeading>
        <CardDescription>Quem aprovou cada portão, as escolhas do modo automático ("sistema (automático)") e cada edição. Reverter é só do dono.</CardDescription>
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
            labels={roteiroFieldLabel}
            formatValue={formatRoteiroValue}
            onRevert={
              roteiro.arquivado
                ? undefined
                : async (toVersion) => {
                    await api.roteiros.reverter(roteiro.id, toVersion, roteiro.version);
                    await invalidarRoteiro(queryClient, roteiro.id);
                  }
            }
            onReload={async () => onReload()}
          />
        )}
      </CardContent>
    </Card>
  );
}
