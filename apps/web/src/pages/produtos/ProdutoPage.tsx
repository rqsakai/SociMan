/*
 * /app/produtos/:id (spec 012, US1–US3 e US5; T029, T033, T042): o cadastro de um produto do TikTok
 * Shop. Cabeçalho com estado, origem da ficha, Aprovar e Arquivar/Restaurar; o que falta para aprovar;
 * o andamento da ficha e dos recortes; a folha de revisão (originais | recortes | flats); o flat lay de
 * cada variante com as opções lado a lado; a ficha editável; as variantes; os dados; "Onde é usado" e
 * o histórico. O `useProduto` recarrega a cada 2 s enquanto houver passo na fila ou rodando. Toda
 * mutação manda a `version` lida (409 `version_conflict` com "Recarregar").
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, CheckCircle2, FilePen, Loader2, Package, RefreshCw, Save, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { AnotacoesCard } from "@/components/anotacoes/AnotacoesDoItem";
import { ConfirmButton } from "@/components/ConfirmButton";
import { AndamentoGeracao } from "@/components/geracao/AndamentoGeracao";
import { FichaForm } from "@/components/produtos/FichaForm";
import { FolhaRevisao } from "@/components/produtos/FolhaRevisao";
import { prepararFoto } from "@/components/produtos/NovoProdutoDialog";
import { PassoGeracao } from "@/components/produtos/PassoGeracao";
import { useRascunho } from "@/components/produtos/useRascunho";
import { VarianteCard } from "@/components/produtos/VarianteCard";
import { Page, usePageMeta } from "@/components/shell";
import { HistoryHeading, VersionHistory } from "@/components/VersionHistory";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { perfilKey } from "@/lib/perfis";
import {
  adicionarVariante,
  estadoProdutoLabel,
  estadoProdutoTone,
  fichaPorLabel,
  FOTO_ACCEPT,
  FOTOS_MAX,
  formatProdutoValue,
  invalidarProduto,
  LIM,
  numeracao,
  passoAberto,
  pendenciasDoErro,
  pendenciaTexto,
  produtoFieldLabel,
  produtoKey,
  ultimoPasso,
  useProduto,
  useProdutoVersoes,
  variantesArquivadas,
  variantesAtivas,
  type Produto,
  type ProdutoPendencia,
  type ProdutoVariante,
} from "@/lib/produtos";

type Rodar = (acao: () => Promise<unknown>, ok: string) => Promise<boolean>;

export default function ProdutoPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const detail = useProduto(id);
  const produto = detail.data;
  const perfilId = produto?.perfilId ?? "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: perfilId !== "" });
  const perfilName = perfil.data?.perfil.name;
  const [error, setError] = useState<unknown>(null);
  const [aprovando, setAprovando] = useState(false);
  const [manual, setManual] = useState(false);
  usePageMeta({
    title: produto ? (produto.ficha?.nomeComercial ?? produto.name) : "Produto",
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(perfilName ? [{ label: perfilName, to: `/app/perfis/${perfilId}?aba=produtos` }] : []),
    ],
  });

  const refresh = () => invalidarProduto(queryClient, id, perfilId || undefined);

  const rodar: Rodar = async (acao, ok) => {
    setError(null);
    try {
      await acao();
      toast.success(ok);
      await refresh();
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  };

  if (detail.isPending) {
    return (
      <Page aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </Page>
    );
  }
  if (detail.isError || !produto) {
    return (
      <Page>
        <Voltar perfilId={null} />
        <ApiErrorAlert error={detail.error} />
      </Page>
    );
  }

  const p = produto;
  const arquivado = p.estado === "arquivado";
  const ativas = variantesAtivas(p);
  const numero = numeracao(p);
  const capa = ativas[0] ? (ativas[0].recorte ?? ativas[0].original) : null;
  const titulo = p.ficha?.nomeComercial ?? p.name;
  const passoFicha = ultimoPasso(p, "produto.ficha");
  const fichaAberta = Boolean(passoFicha && passoAberto(passoFicha.status));
  const pendenciasErro = pendenciasDoErro(error);

  async function aprovar() {
    setAprovando(true);
    await rodar(() => api.produtos.aprovar(p.id, p.version), "Produto aprovado. Ele já aparece nos seletores.");
    setAprovando(false);
  }

  return (
    <Page>
      <Voltar perfilId={p.perfilId} />

      <Card className="shadow-card">
        <CardContent className="flex flex-wrap items-center gap-4">
          <div className="flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-xl border bg-white">
            {capa ? <img src={capa.thumbUrl} alt="" className="size-full object-contain" /> : <Package className="size-8 text-muted-foreground" aria-hidden="true" />}
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <h1 className="text-xl font-bold break-words sm:text-2xl">{titulo}</h1>
            {titulo !== p.name && <p className="text-sm break-words text-muted-foreground">{p.name}</p>}
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge className={estadoProdutoTone[p.estado]} data-testid="estado-produto">
                {estadoProdutoLabel[p.estado]}
              </Badge>
              {p.fichaPor && (
                <Badge variant="outline" data-testid="ficha-por">
                  {fichaPorLabel[p.fichaPor]}
                </Badge>
              )}
              {p.ficha?.categoria && <Badge variant="secondary">{p.ficha.categoria}</Badge>}
              <span className="text-xs text-muted-foreground">
                {ativas.length} {ativas.length === 1 ? "variante" : "variantes"}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {p.estado === "revisao" && (
              <Button type="button" onClick={() => void aprovar()} disabled={aprovando} aria-busy={aprovando}>
                {aprovando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
                Aprovar
              </Button>
            )}
            <ArquivarProduto produto={p} rodar={rodar} />
          </div>
        </CardContent>
      </Card>

      {error !== null && (
        <div className="space-y-1">
          <ApiErrorAlert error={error} onReload={() => void refresh().then(() => setError(null))} />
          {pendenciasErro.length > 0 && <ListaPendencias pendencias={pendenciasErro} numero={numero} testId="pendencias-erro" />}
        </div>
      )}

      {arquivado && (
        <p role="status" className="rounded-lg border p-3 text-sm text-muted-foreground">
          Produto arquivado: fora da lista padrão e dos seletores. Restaure para editar; ele volta ao estado anterior, sem gerar nada de novo.
        </p>
      )}

      {!arquivado && p.estado !== "aprovado" && p.pendencias.length > 0 && (
        <Card className="shadow-card" aria-labelledby="pendencias-titulo">
          <CardHeader>
            <CardTitle>
              <h2 id="pendencias-titulo">O que falta para aprovar</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ListaPendencias pendencias={p.pendencias} numero={numero} testId="pendencias" />
          </CardContent>
        </Card>
      )}

      <AndamentoCard produto={p} rodar={rodar} disabled={arquivado} />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="flex min-w-0 flex-col gap-6">
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Folha de revisão</h2>
              </CardTitle>
              <CardDescription>Originais, recortes e flats, numerados por variante. Clique numa imagem para abrir no tamanho real.</CardDescription>
            </CardHeader>
            <CardContent>
              <FolhaRevisao produto={p} />
            </CardContent>
          </Card>

          <FlatCard produto={p} rodar={rodar} disabled={arquivado} />

          <Card className="shadow-card" aria-labelledby="ficha-titulo">
            <CardHeader>
              <CardTitle>
                <h2 id="ficha-titulo">Ficha técnica</h2>
              </CardTitle>
              <CardDescription>
                As palavras exatas para os prompts. Os campos em inglês vão literais para as cenas; editar a ficha de um produto aprovado
                o devolve para revisão.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {p.ficha || manual ? (
                <FichaForm key={p.id} produto={p} manual={manual} disabled={arquivado} />
              ) : fichaAberta ? (
                <p className="text-sm text-muted-foreground" aria-live="polite">
                  O Claude está escrevendo a ficha a partir das fotos. Acompanhe em "Andamento".
                </p>
              ) : (
                <SemFicha produto={p} rodar={rodar} onManual={() => setManual(true)} disabled={arquivado} />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <VariantesCard produto={p} rodar={rodar} disabled={arquivado} />
          <DadosCard key={p.id} produto={p} disabled={arquivado} onErro={setError} />
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Onde é usado</h2>
              </CardTitle>
              <CardDescription>As cenas ligadas a este produto. Não impedem arquivar.</CardDescription>
            </CardHeader>
            <CardContent>
              {p.usos.length === 0 ? (
                <p className="text-sm text-muted-foreground">Não é usado em nenhuma cena.</p>
              ) : (
                <ul className="space-y-1.5" aria-label="Onde é usado">
                  {p.usos.map((u) => (
                    <li key={u.href} className="flex flex-wrap items-center gap-2 text-sm">
                      <Link to={u.href} className="font-medium hover:underline">
                        {u.rotulo}
                      </Link>
                      <Badge variant="secondary">só informativo</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <AnotacoesCard alvoTipo="produto" alvoId={p.id} arquivado={arquivado} titulo="Anotações do produto" />
      <HistoricoCard produto={p} onReload={refresh} />
    </Page>
  );
}

function Voltar({ perfilId }: { perfilId: string | null }) {
  return (
    <Button type="button" variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground" asChild>
      <Link to={perfilId ? `/app/perfis/${perfilId}?aba=produtos` : "/app/perfis"}>
        <ArrowLeft aria-hidden="true" />
        {perfilId ? "Voltar para os produtos" : "Perfis"}
      </Link>
    </Button>
  );
}

function ListaPendencias({ pendencias, numero, testId }: { pendencias: ProdutoPendencia[]; numero: (id: string) => number | null; testId: string }) {
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm" data-testid={testId} aria-label="Pendências para aprovar">
      {pendencias.map((pd, i) => (
        <li key={`${pd.motivo}-${pd.varianteId ?? ""}-${i}`}>{pendenciaTexto(pd, numero)}</li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------------------------
// Arquivar e restaurar (T042)

function ArquivarProduto({ produto, rodar }: { produto: Produto; rodar: Rodar }) {
  const [cancelar, setCancelar] = useState(false);
  const [busy, setBusy] = useState(false);
  const abertas = produto.passos.filter((g) => passoAberto(g.status) || g.status === "revisao").length;

  if (produto.estado === "arquivado") {
    return (
      <ConfirmButton
        label="Restaurar"
        icon={ArchiveRestore}
        busy={busy}
        title={`Restaurar ${produto.ficha?.nomeComercial ?? produto.name}?`}
        description="O produto volta ao estado de antes do arquivamento, sem gerar nada de novo."
        onConfirm={async () => {
          setBusy(true);
          await rodar(() => api.produtos.restaurar(produto.id, produto.version), "Produto restaurado.");
          setBusy(false);
        }}
      />
    );
  }

  return (
    <AlertDialog onOpenChange={(o) => o && setCancelar(false)}>
      <AlertDialogTrigger asChild>
        <Button type="button" variant="outline" disabled={busy} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Archive aria-hidden="true" />}
          Arquivar
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Arquivar {produto.ficha?.nomeComercial ?? produto.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            O produto sai da lista padrão e dos seletores. As imagens e a ficha continuam guardadas, as cenas ligadas continuam funcionando
            e dá para restaurar depois.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <label className="flex items-start gap-2 text-sm">
          <Checkbox checked={cancelar} onCheckedChange={(v) => setCancelar(v === true)} className="mt-0.5" />
          <span>
            Cancelar gerações em andamento
            <span className="block text-xs text-muted-foreground">
              {abertas > 0 ? `${abertas} ${abertas === 1 ? "geração aberta" : "gerações abertas"} neste produto.` : "Nenhuma geração aberta agora."}
            </span>
          </span>
        </label>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => {
              setBusy(true);
              void rodar(() => api.produtos.arquivar(produto.id, produto.version, cancelar), "Produto arquivado.").finally(() => setBusy(false));
            }}
          >
            Arquivar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------------------------
// Andamento da ficha e dos recortes (T029). O flat fica no FlatCard, por variante.

function AndamentoCard({ produto, rodar, disabled }: { produto: Produto; rodar: Rodar; disabled: boolean }) {
  const numero = numeracao(produto);
  const mostrar = (s: string) => s === "na_fila" || s === "rodando" || s === "falhou" || s === "cancelada";
  const ficha = ultimoPasso(produto, "produto.ficha");
  const itens = [
    ...(ficha && !produto.ficha && mostrar(ficha.status) ? [{ passo: ficha, titulo: "Ficha técnica (Claude)" }] : []),
    ...variantesAtivas(produto).flatMap((v) => {
      const r = ultimoPasso(produto, "produto.recorte", v.id);
      return r && mostrar(r.status) ? [{ passo: r, titulo: `Recorte da variante ${numero(v.id) ?? "?"}` }] : [];
    }),
  ];
  if (itens.length === 0) return null;
  return (
    <Card className="shadow-card" aria-labelledby="andamento-titulo">
      <CardHeader>
        <CardTitle>
          <h2 id="andamento-titulo">Andamento</h2>
        </CardTitle>
        <CardDescription>A ficha sai antes de qualquer passo de imagem. Uma falha num recorte não pede a ficha de novo.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {itens.map(({ passo, titulo }) => (
          <div key={passo.id} className="space-y-2">
            <PassoGeracao produto={produto} passo={passo} titulo={titulo} disabled={disabled} />
            {passo.status === "cancelada" && passo.passo === "produto.recorte" && passo.varianteId && !disabled && (
              <RefazerRecorte produto={produto} varianteId={passo.varianteId} numero={numero(passo.varianteId)} rodar={rodar} />
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// Recorte cancelado: uma geração nova de recorte para a variante (a ficha e os outros recortes ficam).
function RefazerRecorte({ produto, varianteId, numero, rodar }: { produto: Produto; varianteId: string; numero: number | null; rodar: Rodar }) {
  const [busy, setBusy] = useState(false);
  return (
    <ConfirmButton
      label="Refazer recorte"
      icon={RefreshCw}
      size="sm"
      busy={busy}
      title={`Refazer o recorte da variante ${numero ?? ""}?`.replace(" ?", "?")}
      description="Nasce uma geração nova de recorte para esta variante. A ficha e os outros recortes continuam como estão."
      onConfirm={async () => {
        setBusy(true);
        await rodar(() => api.produtos.refazerRecorte(produto.id, varianteId, produto.version), "Novo recorte na fila.");
        setBusy(false);
      }}
    />
  );
}

// Sem ficha e sem pedido aberto: a ficha falhou, foi cancelada ou o produto ainda não tem foto.
function SemFicha({ produto, rodar, onManual, disabled }: { produto: Produto; rodar: Rodar; onManual: () => void; disabled: boolean }) {
  const [busy, setBusy] = useState(false);
  const ultimo = ultimoPasso(produto, "produto.ficha");
  // o pedido de novo só vale sem pedido não final (o `falhou` tem "Tentar de novo" no Andamento)
  const podePedir = variantesAtivas(produto).length > 0 && (!ultimo || ultimo.status === "cancelada" || ultimo.status === "descartada");
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {ultimo?.status === "falhou"
          ? "A ficha não saiu. Tente de novo em \"Andamento\" ou preencha à mão."
          : ultimo?.status === "cancelada"
            ? "O pedido da ficha foi cancelado. Peça de novo ao Claude ou preencha à mão."
            : variantesAtivas(produto).length === 0
              ? "Envie pelo menos uma foto em \"Variantes\" para o SociMan pedir a ficha."
              : "Ainda sem ficha."}
      </p>
      {!disabled && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={onManual}>
            <FilePen aria-hidden="true" />
            Preencher à mão
          </Button>
          {podePedir && (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              aria-busy={busy}
              onClick={async () => {
                setBusy(true);
                await rodar(() => api.produtos.pedirFicha(produto.id, produto.version), "Ficha pedida ao Claude.");
                setBusy(false);
              }}
            >
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
              Pedir ficha de novo
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Flat lay por variante (T029): andamento, opções lado a lado com "Usar opção N" e "Gerar outras",
// "Tentar de novo" e "Cancelar geração" (componentes da 021); "Refazer flat" na variante com flat.

function FlatCard({ produto, rodar, disabled }: { produto: Produto; rodar: Rodar; disabled: boolean }) {
  const ativas = variantesAtivas(produto);
  const precisa = Boolean(produto.ficha?.precisaFlat);
  const algum = ativas.some((v) => v.flat || ultimoPasso(produto, "produto.flat", v.id));
  if (!precisa && !algum) return null;
  return (
    <Card className="shadow-card" aria-labelledby="flat-titulo">
      <CardHeader>
        <CardTitle>
          <h2 id="flat-titulo">Flat lay</h2>
        </CardTitle>
        <CardDescription>
          {precisa
            ? "O item deitado sobre fundo branco, visto de cima, sem volume de manequim. Escolha uma opção por variante."
            : "Este produto não usa flat lay: os flats guardados não vão para o render."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {ativas.map((v, i) => (
          <FlatVariante key={v.id} produto={produto} variante={v} numero={i + 1} rodar={rodar} disabled={disabled || !precisa} />
        ))}
      </CardContent>
    </Card>
  );
}

function FlatVariante({ produto, variante, numero, rodar, disabled }: { produto: Produto; variante: ProdutoVariante; numero: number; rodar: Rodar; disabled: boolean }) {
  const [busy, setBusy] = useState(false);
  const ultimo = ultimoPasso(produto, "produto.flat", variante.id);
  const vivo = ultimo && (passoAberto(ultimo.status) || ultimo.status === "revisao" || ultimo.status === "falhou");
  const titulo = `Flat da variante ${numero}${variante.corPt ? ` (${variante.corPt})` : ""}`;

  async function refazer() {
    setBusy(true);
    await rodar(() => api.produtos.refazerFlat(produto.id, variante.id, produto.version), "Novo flat na fila.");
    setBusy(false);
  }

  return (
    <section aria-label={titulo} className="space-y-3 border-b pb-6 last:border-0 last:pb-0" data-testid={`flat-variante-${numero}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{titulo}</h3>
        {!disabled && !vivo && variante.recorte && (
          <ConfirmButton
            label={variante.flat ? "Refazer flat" : "Gerar flat"}
            icon={RefreshCw}
            size="sm"
            busy={busy}
            title={variante.flat ? `Refazer o flat da variante ${numero}?` : `Gerar o flat da variante ${numero}?`}
            description={
              variante.flat
                ? "Nasce uma geração nova, com seeds novas. O flat atual só muda quando você escolher uma das novas opções. Num produto aprovado, ele volta para revisão."
                : "Nasce uma geração com 2 opções a partir do recorte e da ficha desta variante."
            }
            onConfirm={refazer}
          />
        )}
      </div>
      {variante.flat && (
        <div className="flex items-center gap-3">
          <img src={variante.flat.thumbUrl} alt={`Flat atual da variante ${numero}`} className="size-20 rounded-md border bg-white object-contain" />
          <span className="text-xs text-muted-foreground">Flat atual{variante.avisos.includes("flat_desatualizado") ? ": feito com a ficha anterior." : "."}</span>
        </div>
      )}
      {!variante.recorte && !vivo && <p className="text-xs text-muted-foreground">O flat sai depois do recorte desta variante.</p>}
      {vivo && ultimo && <PassoGeracao produto={produto} passo={ultimo} titulo={variante.flat ? "Novas opções" : "Opções"} disabled={disabled} />}
      {!vivo && !variante.flat && ultimo?.status === "cancelada" && <p className="text-xs text-muted-foreground">A última geração foi cancelada.</p>}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
// Variantes (T033): ordem, arquivar/restaurar e uma foto nova (até 6 ativas).

function VariantesCard({ produto, rodar, disabled }: { produto: Produto; rodar: Rodar; disabled: boolean }) {
  const queryClient = useQueryClient();
  const ativas = variantesAtivas(produto);
  const arquivadas = variantesArquivadas(produto);
  const [inputKey, setInputKey] = useState(0);
  const [enviando, setEnviando] = useState<number | null>(null);
  const [erroFoto, setErroFoto] = useState<string | null>(null);

  function mover(i: number, delta: -1 | 1) {
    const ids = ativas.map((v) => v.id);
    const j = i + delta;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j]!, ids[i]!];
    void rodar(() => api.produtos.variantesOrdenar(produto.id, produto.version, ids), "Ordem das variantes salva.");
  }

  async function enviar(arquivo: File | undefined) {
    setInputKey((k) => k + 1);
    setErroFoto(null);
    if (!arquivo) return;
    const foto = await prepararFoto(arquivo);
    if (foto.erro) {
      setErroFoto(foto.erro);
      return;
    }
    setEnviando(0);
    await rodar(async () => {
      const novo = await adicionarVariante(produto.id, produto.version, arquivo, setEnviando);
      queryClient.setQueryData(produtoKey(produto.id), novo);
    }, "Variante adicionada. O recorte já foi pedido.");
    setEnviando(null);
  }

  return (
    <Card className="shadow-card" aria-labelledby="variantes-titulo">
      <CardHeader>
        <CardTitle>
          <h2 id="variantes-titulo">
            Variantes ({ativas.length}/{FOTOS_MAX})
          </h2>
        </CardTitle>
        <CardDescription>Uma por cor. As cores se editam na ficha.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ol className="space-y-2" aria-label="Variantes ativas">
          {ativas.map((v, i) => (
            <VarianteCard
              key={v.id}
              variante={v}
              numero={i + 1}
              total={ativas.length}
              disabled={disabled}
              onMover={(d) => mover(i, d)}
              onArquivar={async () => {
                await rodar(() => api.produtos.varianteArquivar(produto.id, v.id, produto.version), `Variante ${i + 1} arquivada.`);
              }}
            />
          ))}
        </ol>
        {!disabled && ativas.length < FOTOS_MAX && (
          <Field label="Adicionar variante" error={erroFoto ?? undefined} hint="Uma foto PNG, JPG ou WebP, com no mínimo 512 × 512 e até 20 MB.">
            {({ id, describedBy }) => (
              <FileField
                key={inputKey}
                id={id}
                accept={FOTO_ACCEPT}
                disabled={enviando !== null}
                aria-describedby={describedBy}
                rotuloBotao={enviando !== null ? `Enviando ${Math.round(enviando * 100)}%` : "Escolher foto"}
                onChange={(e) => void enviar(e.target.files?.[0])}
              />
            )}
          </Field>
        )}
        {arquivadas.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Arquivadas</h3>
            <ul className="space-y-2" aria-label="Variantes arquivadas">
              {arquivadas.map((v) => (
                <VarianteCard
                  key={v.id}
                  variante={v}
                  numero={null}
                  total={ativas.length}
                  disabled={disabled}
                  onRestaurar={async () => {
                    await rodar(() => api.produtos.varianteRestaurar(produto.id, v.id, produto.version), "Variante restaurada.");
                  }}
                />
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------------------------
// Dados do cadastro: nome interno, observação e link da loja (não mudam o estado).

function DadosCard({ produto, disabled, onErro }: { produto: Produto; disabled: boolean; onErro: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const r = useRascunho({ name: produto.name, obs: produto.obs, urlLoja: produto.urlLoja ?? "" }, produto.version);
  const [busy, setBusy] = useState(false);
  const [erros, setErros] = useState<Record<string, string>>({});
  const d = r.valor;

  async function salvar(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!d.name.trim()) errs.name = "Informe o nome";
    if (d.urlLoja.trim() && !/^https:\/\/\S+$/.test(d.urlLoja.trim())) errs.urlLoja = "Use um link que comece com https://";
    setErros(errs);
    if (Object.keys(errs).length > 0) return;
    setBusy(true);
    onErro(null);
    try {
      const novo = await api.produtos.editar(produto.id, {
        version: r.versao,
        name: d.name.trim(),
        obs: d.obs.trim(),
        urlLoja: d.urlLoja.trim() || null,
      });
      queryClient.setQueryData(produtoKey(produto.id), novo);
      r.reiniciar({ name: novo.name, obs: novo.obs, urlLoja: novo.urlLoja ?? "" }, novo.version);
      toast.success("Dados salvos.");
      await invalidarProduto(queryClient, produto.id, produto.perfilId);
    } catch (err) {
      onErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Dados</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={(e) => void salvar(e)} className="space-y-4" noValidate>
          <Field label="Nome interno" error={erros.name}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                value={d.name}
                maxLength={LIM.nome}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => r.setValor({ ...d, name: e.target.value })}
              />
            )}
          </Field>
          <Field label="Observação" hint="Também é o lugar de registrar a origem das fotos.">
            {({ id, describedBy }) => (
              <Textarea id={id} rows={3} value={d.obs} maxLength={LIM.obs} disabled={disabled} aria-describedby={describedBy} onChange={(e) => r.setValor({ ...d, obs: e.target.value })} />
            )}
          </Field>
          <Field label="Link da loja (opcional)" error={erros.urlLoja} hint="Só informativo: o SociMan não consulta a loja.">
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                type="url"
                inputMode="url"
                placeholder="https://"
                value={d.urlLoja}
                maxLength={LIM.urlLoja}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => r.setValor({ ...d, urlLoja: e.target.value })}
              />
            )}
          </Field>
          {!disabled && (
            <Button type="submit" variant="outline" disabled={busy || !r.sujo} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar dados
            </Button>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------------------------
// Histórico (T042): autor, antes e depois; "Reverter" só para o dono (o VersionHistory confere).

function HistoricoCard({ produto, onReload }: { produto: Produto; onReload: () => Promise<unknown> }) {
  const versoes = useProdutoVersoes(produto.id);
  return (
    <Card className="shadow-card" aria-labelledby="historico-produto">
      <CardHeader>
        <span id="historico-produto">
          <HistoryHeading>Histórico</HistoryHeading>
        </span>
        <CardDescription>Da versão mais recente para a mais antiga. Reverter (só o dono) cria uma versão nova e não gera imagens de novo.</CardDescription>
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
            labels={produtoFieldLabel}
            formatValue={formatProdutoValue}
            onRevert={
              produto.estado === "arquivado"
                ? undefined
                : async (toVersion) => {
                    await api.produtos.reverter(produto.id, produto.version, toVersion);
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
