/*
 * Cena (spec 010): /app/cenas/:id (detalhe) e /app/perfis/:id/cenas/nova (cena nova).
 *
 * Esquerda: o formulário (CenaForm) com "Salvar". Direita: avisos, "o avatar/cenário mudou" com
 * "Remontar prompt", o prompt montado com "Copiar prompt"/"Copiar negative prompt", os ingredientes,
 * o guia de edição (texto na tela), as tomadas, "Usada em" e as anotações.
 * Ações: "Marcar como pronta" (congela o prompt), "Voltar a rascunho", "Duplicar", arquivar/restaurar
 * e o histórico. Numa cena usada, só nome, tags e notas mudam (para variar o prompt, duplique).
 * `?proposta=<id>`: a proposta de cena de um agente (spec 009) preenche o formulário sem salvar; o
 * "Salvar" humano grava com o `propostaId` e a proposta fica aplicada.
 */
import { ApiError } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, Bot, CheckCircle2, Copy, History, Link2, Loader2, PencilLine, Save, TriangleAlert, Undo2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Avisos, AvisoMudou } from "@/components/cenas/Avisos";
import { CenaForm } from "@/components/cenas/CenaForm";
import { AjustarCenaIa, iaCenaDecorador, type IaCtx } from "@/components/cenas/IaCena";
import { AnotacoesCard } from "@/components/anotacoes/AnotacoesDoItem";
import { Ingredientes } from "@/components/cenas/Ingredientes";
import { PromptPainel } from "@/components/cenas/PromptPainel";
import { Tomadas } from "@/components/cenas/Tomadas";
import { ConfirmButton } from "@/components/ConfirmButton";
import { usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { autorTexto, invalidarAnotacoes, type Anotacao } from "@/lib/anotacoes";
import {
  CAMPOS_PROMPT,
  camposDe,
  camposVazios,
  campoCenaLabel,
  
  diferencas,
  faltandoDe,
  invalidarCena,
  statusCenaLabel,
  statusCenaTone,
  useCena,
  useCenaPadroes,
  type Cena,
  type CenaCampos,
  type IaAplicacaoCena,
} from "@/lib/cenas";
import { useFormRebase } from "@/lib/ia";
import { perfilKey } from "@/lib/perfis";
import { formatDateTime } from "@/lib/tz";

const abaCenas = (perfilId: string) => `/app/perfis/${perfilId}?aba=cenas`;

// A proposta de cena aberta de `?proposta=` (só `proposta_cena` aberta conta).
function usePropostaCena() {
  const [params] = useSearchParams();
  const id = params.get("proposta");
  const q = useQuery({
    queryKey: ["anotacao", id],
    queryFn: () => api.anotacoes.get(id!).then((r) => r.anotacao),
    enabled: Boolean(id),
    retry: false,
  });
  const a = q.data;
  const valida = a && (a.tipo as string) === "proposta_cena" && a.situacao === "aberta" ? a : null;
  return { id, pendente: Boolean(id) && q.isPending, proposta: valida, invalida: Boolean(id) && (q.isError || (a && !valida)) };
}

// Os campos da proposta (camelCase de CenaIn), só os que vieram.
function camposDaProposta(a: Anotacao): Partial<CenaCampos> {
  const c = (a.campos ?? {}) as unknown as Record<string, unknown>;
  const base = camposVazios() as unknown as Record<string, unknown>;
  return Object.fromEntries(Object.entries(c).filter(([k, v]) => k in base && v !== undefined)) as Partial<CenaCampos>;
}

function FaixaProposta({ proposta }: { proposta: Anotacao }) {
  return (
    <Alert className="border-info/60" role="region" aria-label="Proposta do agente">
      <Bot className="text-info" aria-hidden="true" />
      <AlertTitle>Proposta de {autorTexto(proposta.autor)}</AlertTitle>
      <AlertDescription>
        <p>Os campos propostos já estão no formulário. Nada foi salvo: confira e clique em "Salvar".</p>
        {proposta.texto && <p className="break-words whitespace-pre-wrap">{proposta.texto}</p>}
        <p className="text-xs">{formatDateTime(proposta.createdAt)}</p>
      </AlertDescription>
    </Alert>
  );
}

function VoltarPerfil({ perfilId }: { perfilId: string }) {
  return (
    <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
      <Link to={abaCenas(perfilId)}>
        <ArrowLeft aria-hidden="true" />
        Cenas do perfil
      </Link>
    </Button>
  );
}

function usePerfilNome(perfilId: string) {
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: Boolean(perfilId) });
  return perfil.data?.perfil.name;
}

// ---------------------------------------------------------------------------------------------
// Nova cena

export function CenaNova() {
  const { id: perfilId = "" } = useParams();
  const perfilNome = usePerfilNome(perfilId);
  const p = usePropostaCena();
  usePageMeta({
    title: "Nova cena",
    breadcrumbs: [{ label: "Perfis", to: "/app/perfis" }, ...(perfilNome ? [{ label: perfilNome, to: abaCenas(perfilId) }] : [])],
  });
  if (p.pendente) return <Skeleton className="h-96 w-full rounded-xl" />;
  return <NovaForm key={p.proposta?.id ?? "nova"} perfilId={perfilId} proposta={p.proposta} propostaInvalida={Boolean(p.invalida)} />;
}


function NovaForm({
  perfilId,
  proposta,
  propostaInvalida,
}: {
  perfilId: string;
  proposta: Anotacao | null;
  propostaInvalida: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const padroes = useCenaPadroes(perfilId);
  const [valores, setValores] = useState<CenaCampos>(() => ({ ...camposVazios(), ...(proposta ? camposDaProposta(proposta) : {}) }));
  const [ia, setIa] = useState<IaAplicacaoCena[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const set = (patch: Partial<CenaCampos>) => setValores((cur) => ({ ...cur, ...patch }));
  const faltam = [!valores.nome.trim() && "nome", !valores.acao.trim() && "ação"].filter(Boolean) as string[];

  async function salvar() {
    setError(null);
    if (faltam.length) return setError(new ApiError(400, "validation_error", `Preencha: ${faltam.join(" e ")}.`));
    setBusy(true);
    try {
      const cena = await api.cenas.create(perfilId, {
        ...valores,
        nome: valores.nome.trim(),
        ...(proposta ? { propostaId: proposta.id } : {}),
        ...(ia.length ? { ia } : {}),
      });
      toast.success("Cena criada como rascunho.");
      await invalidarCena(queryClient, null, perfilId);
      if (proposta) await invalidarAnotacoes(queryClient);
      void navigate(`/app/cenas/${cena.id}`, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const iaCtx: IaCtx = {
    perfilId,
    cena: null,
    valores,
    salvar: async (patch, marcas) => {
      set(patch);
      setIa((cur) => [...cur.filter((m) => !marcas.some((x) => x.tipoCampo === m.tipoCampo)), ...marcas]);
    },
    disabled: busy,
  };

  return (
    <div className="space-y-6">
      <VoltarPerfil perfilId={perfilId} />
      <h1 className="text-xl font-bold">Nova cena</h1>
      {proposta && <FaixaProposta proposta={proposta} />}
      {propostaInvalida && (
        <Alert>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Proposta indisponível</AlertTitle>
          <AlertDescription>A proposta não existe mais ou já foi resolvida. O formulário começa vazio.</AlertDescription>
        </Alert>
      )}
      <Card className="shadow-card">
        <CardContent>
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void salvar();
            }}
            className="space-y-6"
          >
            <AjustarCenaIa ctx={iaCtx} />
            <CenaForm perfilId={perfilId} valores={valores} onChange={set} padroes={padroes.data} disabled={busy} iaCampo={iaCenaDecorador(iaCtx)} />
            {error !== null && <ApiErrorAlert error={error} />}
            <Button type="submit" disabled={busy} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Detalhe

export default function CenaDetalhe() {
  const { id = "" } = useParams();
  const q = useCena(id);
  const p = usePropostaCena();
  const cena = q.data;
  const perfilNome = usePerfilNome(cena?.perfilId ?? "");
  usePageMeta({
    title: cena?.nome ?? "Cena",
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(cena && perfilNome ? [{ label: perfilNome, to: abaCenas(cena.perfilId) }] : []),
    ],
  });

  if (q.isPending || p.pendente) {
    return (
      <div className="space-y-4" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }
  if (q.isError || !cena) return <ApiErrorAlert error={q.error} />;
  return (
    <CenaEditor
      key={`${cena.id}-${cena.version}-${p.proposta?.id ?? ""}`}
      cena={cena}
      proposta={p.proposta}
      propostaInvalida={Boolean(p.invalida)}
    />
  );
}

function CenaEditor({
  cena,
  proposta,
  propostaInvalida,
}: {
  cena: Cena;
  proposta: Anotacao | null;
  propostaInvalida: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [, setParams] = useSearchParams();
  const padroes = useCenaPadroes(cena.perfilId);
  const salvos = camposDe(cena);
  // O "Aplicar" da IA salva um campo e a versão muda (o editor remonta): os outros campos sujos voltam
  // por cima dos dados novos (spec 008, R-9).
  const rebase = useFormRebase<Partial<CenaCampos>>(`cena:${cena.id}`);
  const [valores, setValores] = useState<CenaCampos>(() => ({
    ...salvos,
    ...rebase.retomado,
    ...(proposta ? camposDaProposta(proposta) : {}),
  }));
  const [busy, setBusy] = useState<null | "salvar" | "pronta" | "rascunho" | "remontar" | "duplicar" | "arquivo">(null);
  const [error, setError] = useState<unknown>(null);
  const set = (patch: Partial<CenaCampos>) => setValores((cur) => ({ ...cur, ...patch }));
  const usada = cena.status === "usada";
  const mudancas = diferencas(salvos, valores);
  const sujo = Object.keys(mudancas).length > 0;
  const mexePrompt = Object.keys(mudancas).some((k) => CAMPOS_PROMPT.includes(k as keyof CenaCampos));
  const refresh = () => invalidarCena(queryClient, cena.id, cena.perfilId);

  async function run(kind: NonNullable<typeof busy>, fn: () => Promise<unknown>, msg: string) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      toast.success(msg);
      await refresh();
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function salvar() {
    if (!sujo && !proposta) return toast.info("Nada para salvar.");
    if (!valores.nome.trim() || !valores.acao.trim()) return setError(new ApiError(400, "validation_error", "Nome e ação são obrigatórios."));
    const ok = await run(
      "salvar",
      () => api.cenas.update(cena.id, { version: cena.version, ...mudancas, ...(proposta ? { propostaId: proposta.id } : {}) }),
      cena.status === "pronta" && mexePrompt ? "Alterações salvas. A cena voltou a rascunho." : "Alterações salvas.",
    );
    if (ok && proposta) {
      await invalidarAnotacoes(queryClient);
      setParams({}, { replace: true });
    }
  }

  const sujosMenos = (campos: (keyof CenaCampos)[]) =>
    Object.fromEntries(Object.entries(mudancas).filter(([k]) => !campos.includes(k as keyof CenaCampos))) as Partial<CenaCampos>;

  const iaCtx: IaCtx = {
    perfilId: cena.perfilId,
    cena,
    valores,
    salvar: async (patch, ia) => {
      const resto = sujosMenos(Object.keys(patch) as (keyof CenaCampos)[]);
      if (Object.keys(resto).length) rebase.guardar(resto);
      try {
        await api.cenas.update(cena.id, { version: cena.version, ...patch, ia });
      } catch (err) {
        rebase.esquecer();
        throw err;
      }
      await refresh();
    },
    disabled: busy !== null || cena.arquivada || usada,
  };

  return (
    <div className="space-y-6">
      <VoltarPerfil perfilId={cena.perfilId} />

      <Card className="shadow-card">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-bold break-words">{cena.nome}</h1>
          </CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            <Badge className={statusCenaTone[cena.status]} data-testid="cena-status">
              {statusCenaLabel[cena.status]}
            </Badge>
            {cena.arquivada && <Badge className="bg-dark text-dark-foreground">Arquivada</Badge>}
            <span>{cena.duracaoS} s</span>
            {cena.produtoNome && <span>· {cena.produtoNome}</span>}
            <span>· alterada em {formatDateTime(cena.updatedAt)}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Ações da cena">
            {!cena.arquivada && cena.status === "rascunho" && (
              <Button
                type="button"
                disabled={busy !== null || sujo}
                title={sujo ? "Salve as alterações antes" : undefined}
                aria-busy={busy === "pronta"}
                onClick={() => void run("pronta", () => api.cenas.pronta(cena.id, cena.version), "Cena pronta: o prompt foi congelado.")}
              >
                {busy === "pronta" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
                Marcar como pronta
              </Button>
            )}
            {!cena.arquivada && cena.status === "pronta" && (
              <Button
                type="button"
                variant="outline"
                disabled={busy !== null}
                aria-busy={busy === "rascunho"}
                onClick={() => void run("rascunho", () => api.cenas.rascunho(cena.id, cena.version), "A cena voltou a rascunho.")}
              >
                {busy === "rascunho" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Undo2 aria-hidden="true" />}
                Voltar a rascunho
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              disabled={busy !== null}
              aria-busy={busy === "duplicar"}
              onClick={async () => {
                setError(null);
                setBusy("duplicar");
                try {
                  const nova = await api.cenas.duplicar(cena.id);
                  toast.success("Cena duplicada como rascunho.");
                  await invalidarCena(queryClient, null, cena.perfilId);
                  void navigate(`/app/cenas/${nova.id}`);
                } catch (err) {
                  setError(err);
                } finally {
                  setBusy(null);
                }
              }}
            >
              {busy === "duplicar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Copy aria-hidden="true" />}
              Duplicar
            </Button>
            <ConfirmButton
              label={cena.arquivada ? "Restaurar" : "Arquivar"}
              icon={cena.arquivada ? ArchiveRestore : Archive}
              busy={busy === "arquivo"}
              disabled={busy !== null}
              title={cena.arquivada ? "Restaurar esta cena?" : "Arquivar esta cena?"}
              description={
                cena.arquivada
                  ? "A cena volta para a lista."
                  : usada
                    ? "A cena sai da lista e continua ligada aos vídeos em que foi usada. Nada é apagado."
                    : "A cena sai da lista; nada é apagado e dá para restaurar."
              }
              onConfirm={() =>
                void run(
                  "arquivo",
                  () => (cena.arquivada ? api.cenas.restore(cena.id, cena.version) : api.cenas.archive(cena.id, cena.version)),
                  cena.arquivada ? "Cena restaurada." : "Cena arquivada.",
                )
              }
            />
            <Button type="button" variant="ghost" asChild>
              <Link to={`/app/cenas/${cena.id}/historico`}>
                <History aria-hidden="true" />
                Histórico
              </Link>
            </Button>
          </div>
          {faltandoDe(error).length > 0 ? (
            <Alert variant="destructive">
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>A cena ainda não pode ficar pronta</AlertTitle>
              <AlertDescription>
                <p>Falta:</p>
                <ul aria-label="O que falta" className="list-disc pl-5">
                  {faltandoDe(error).map((f) => (
                    <li key={f}>{campoCenaLabel[f] ?? f}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : (
            error !== null && <ApiErrorAlert error={error} onReload={() => void refresh()} />
          )}
        </CardContent>
      </Card>

      {proposta && <FaixaProposta proposta={proposta} />}
      {propostaInvalida && (
        <Alert>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Proposta indisponível</AlertTitle>
          <AlertDescription>A proposta não existe mais ou já foi resolvida.</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
        <div className="min-w-0 space-y-6">
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PencilLine className="size-4 text-muted-foreground" aria-hidden="true" />
                <h2>Cena</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form
                noValidate
                onSubmit={(e) => {
                  e.preventDefault();
                  void salvar();
                }}
                className="space-y-6"
              >
                {usada && (
                  <Alert role="note">
                    <Link2 aria-hidden="true" />
                    <AlertTitle>Cena usada num vídeo</AlertTitle>
                    <AlertDescription>
                      Só nome, tags, notas e tomadas mudam. Para variar o prompt, duplique a cena.
                    </AlertDescription>
                  </Alert>
                )}
                {!usada && !cena.arquivada && <AjustarCenaIa ctx={iaCtx} />}
                <CenaForm
                  perfilId={cena.perfilId}
                  valores={valores}
                  onChange={set}
                  refs={{ avatar: cena.avatar, cenario: cena.cenario, produtoImagem: cena.produtoImagem }}
                  padroes={padroes.data}
                  bloquearPrompt={usada}
                  disabled={cena.arquivada || busy === "salvar"}
                  iaCampo={iaCenaDecorador(iaCtx)}
                />
                {cena.status === "pronta" && mexePrompt && (
                  <p role="status" className="text-sm text-warning-foreground">
                    Salvar esta mudança volta a cena para rascunho (o prompt deixa de estar congelado).
                  </p>
                )}
                {!cena.arquivada && (
                  <Button type="submit" disabled={busy !== null} aria-busy={busy === "salvar"}>
                    {busy === "salvar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                    Salvar
                  </Button>
                )}
              </form>
            </CardContent>
          </Card>
        </div>
        <div className="min-w-0 space-y-6">
          <Avisos avisos={cena.avisos} />
          <AvisoMudou
            avisos={cena.avisos}
            podeRemontar={!cena.arquivada && (cena.status === "pronta" || usada)}
            remontando={busy === "remontar"}
            onRemontar={() => void run("remontar", () => api.cenas.remontar(cena.id, cena.version), "Prompt remontado com o avatar e o cenário atuais.")}
          />
          <PromptPainel prompt={cena.prompt} status={cena.status} />
          <Ingredientes itens={cena.ingredientes} />
          {cena.textoTela && (
            <Card className="gap-3 shadow-card" aria-labelledby="edicao-cena">
              <CardHeader>
                <CardTitle>
                  <h2 id="edicao-cena">Edição</h2>
                </CardTitle>
                <CardDescription>Texto na tela para pôr na edição (não vai ao Flow).</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm break-words whitespace-pre-wrap">{cena.textoTela}</p>
              </CardContent>
            </Card>
          )}
          <Tomadas cena={cena} />
          <UsadaEm cena={cena} />
          <AnotacoesCard alvoTipo="cena" alvoId={cena.id} arquivado={cena.arquivada} titulo="Anotações da cena" />
        </div>
      </div>
    </div>
  );
}

function UsadaEm({ cena }: { cena: Cena }) {
  return (
    <Card className="gap-3 shadow-card" aria-labelledby="usada-em">
      <CardHeader>
        <CardTitle>
          <h2 id="usada-em">Usada em</h2>
        </CardTitle>
        <CardDescription>Vídeos próprios (Conteúdos) que usam esta cena. Ligue pelo conteúdo.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {cena.usos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum vídeo ainda.</p>
        ) : (
          <>
            <ul className="space-y-1 text-sm">
              {cena.usos.map((u) => (
                <li key={u.conteudoId}>
                  <Link to={u.link} className="font-medium underline-offset-2 hover:underline">
                    {u.titulo || "Conteúdo sem título"}
                  </Link>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">Vídeo gerado por IA: marque o selo de conteúdo de IA ao postar.</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
