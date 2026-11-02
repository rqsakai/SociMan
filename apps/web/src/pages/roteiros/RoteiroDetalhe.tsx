/*
 * /app/roteiros/:id (spec 011): o roteiro com vídeo local. Cabeçalho com o estado, o perfil, os
 * produtos, o avatar e a voz, e as ações (planejar com IA, tentar de novo, arquivar/restaurar); o erro
 * e os avisos; os portões e o modo (T048); as etapas Texto, Narração, Keyframes, Clipes e Final, em
 * abas (`?etapa=`; sem ela, a etapa onde o roteiro está); e o histórico (reverter só o dono). O
 * `useRoteiro` recarrega a cada 2 s enquanto o roteiro trabalha sozinho. Spec 031: o vídeo guiado
 * tem o switch "Wizard / Avançado" no topo (o wizard com o modal de cenas; o avançado é este
 * detalhe da 011, com os quadros e os trechos); os roteiros da 011 abrem sempre no avançado.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, Info, Loader2, RotateCcw, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
import { ModalCenas } from "./wizard/ModalCenas";
import { Wizard } from "./wizard/Wizard";
import { gravarModo, lerModo, PORTOES_TODOS, portoesTodosLigados, type ModoTela } from "@/lib/videoGuiado";
import { cn } from "@/lib/utils";

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
  const [params] = useSearchParams();
  const [busy, setBusy] = useState<string | null>(null);
  const etapaUrl = params.get("etapa");
  const etapa: Etapa = ETAPAS.some((e) => e.id === etapaUrl) ? (etapaUrl as Etapa) : etapaAtual(r);
  const atual = etapaAtual(r);
  const travado = r.arquivado;
  const podePlanejar = !travado && (PLANEJAVEL.has(r.status) || (r.status === "falhou" && r.etapaFalhou === "plano"));
  // Spec 031 (FR-014, FR-018, R9): o vídeo guiado abre no wizard (o chat, depois um item por vez) e
  // troca para o avançado pelo switch do topo; o último modo fica no navegador. Quem planeja no
  // guiado é o "Montar o vídeo" do chat. Os roteiros da 011 abrem sempre no avançado.
  const guiado = r.tipoVideo != null;
  const [modo, setModo] = useState<ModoTela>(() => (guiado ? (lerModo(r.id) ?? "wizard") : "avancado"));
  const wizard = guiado && modo === "wizard";
  // No wizard, o aviso de fala tem um bloco próprio com as saídas (T050).
  const avisos = wizard ? r.avisos.filter((a) => a.code !== "fala_nao_cabe") : r.avisos;

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
            {podePlanejar && !guiado && (
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
      {avisos.length > 0 && (
        <Alert data-testid="roteiro-avisos">
          <TriangleAlert className="text-warning" aria-hidden="true" />
          <AlertTitle>Avisos</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {avisos.map((a, i) => (
                <li key={`${a.code}-${i}`}>
                  {a.ordem != null && `Cena ${a.ordem + 1}: `}
                  {a.message}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <ModoSwitch
        guiado={guiado}
        modo={modo}
        onChange={(m) => {
          setModo(m);
          gravarModo(r.id, m);
        }}
      />

      {wizard ? (
        <>
          <PortoesDoWizard r={r} rodar={rodar} travado={travado} />
          <Wizard roteiro={r} rodar={rodar} travado={travado} ModalCenas={ModalCenas} />
        </>
      ) : (
        <Avancado r={r} rodar={rodar} travado={travado} etapa={etapa} atual={atual} guiado={guiado} />
      )}

      {/* O histórico mostra as frases e os prompts: só no avançado (FR-015). */}
      {!wizard && <HistoricoRoteiro roteiro={r} onReload={onReload} />}
    </Page>
  );
}

// O switch "Wizard / Avançado" (FR-014, R9). Os roteiros da 011 não têm cenário nem grade: abrem
// sempre no avançado, e o lugar do switch explica por quê (FR-018).
function ModoSwitch({ guiado, modo, onChange }: { guiado: boolean; modo: ModoTela; onChange: (m: ModoTela) => void }) {
  if (!guiado) {
    return (
      <p className="flex items-start gap-2 text-sm text-muted-foreground" data-testid="modo-so-avancado">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        Este vídeo foi criado antes do vídeo guiado (sem cenário nem grade de duração): ele abre sempre no modo avançado.
      </p>
    );
  }
  const opcoes: { id: ModoTela; rotulo: string }[] = [
    { id: "wizard", rotulo: "Wizard" },
    { id: "avancado", rotulo: "Avançado" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div role="radiogroup" aria-label="Modo da tela" className="inline-flex rounded-lg border bg-muted p-0.5" data-testid="modo-switch">
        {opcoes.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={modo === o.id}
            onClick={() => onChange(o.id)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              modo === o.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.rotulo}
          </button>
        ))}
      </div>
      <p className="min-w-0 flex-1 text-xs text-muted-foreground">
        {modo === "wizard" ? "Um passo por vez, para aprovar ou não." : "Texto, prompts, portões e mais de uma versão por item. Trocar de modo não perde nada."}
      </p>
    </div>
  );
}

// FR-035: no wizard, todos os portões ficam ligados e o modo é "revisar" (cada item espera a
// aprovação). Se o avançado desligou algum, o wizard religa todos ao abrir, uma vez, e avisa.
function PortoesDoWizard({ r, rodar, travado }: { r: Roteiro; rodar: RodarRoteiro; travado: boolean }) {
  // uma tentativa por versão do roteiro (um 409 de versão tenta de novo na próxima leitura)
  const pedido = useRef<number | null>(null);
  const precisa = !travado && r.status !== "pronto" && !portoesTodosLigados(r);
  useEffect(() => {
    if (!precisa || pedido.current === r.version) return;
    pedido.current = r.version;
    void rodar(() => api.roteiros.controle(r.id, { version: r.version, modo: "revisar", portoes: { ...PORTOES_TODOS } }), "No wizard, todos os portões ficam ligados: cada item espera a sua aprovação.");
  }, [precisa, r.id, r.version, rodar]);
  return null;
}

// O detalhe da 011: os portões e o modo, e as etapas em abas (`?etapa=`). No guiado (031), o mesmo
// avançado, com a troca de cenas por posição e, nas etapas, os quadros e os trechos.
function Avancado({ r, rodar, travado, etapa, atual, guiado }: { r: Roteiro; rodar: RodarRoteiro; travado: boolean; etapa: Etapa; atual: Etapa; guiado: boolean }) {
  const [, setParams] = useSearchParams();
  const [salvandoPortoes, setSalvandoPortoes] = useState(false);
  return (
    <>
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
            <TabsContent value="texto" className="flex flex-col gap-4">
              {guiado && r.posicoes.length > 0 && <ModalCenas roteiro={r} rodar={rodar} travado={travado} avancado />}
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
    </>
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
