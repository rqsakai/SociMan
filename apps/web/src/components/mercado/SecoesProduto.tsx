/*
 * Seções do detalhe do produto (spec 026, US5): Ficha (atributos, argumentos, variantes, selos e
 * "Ver versões anteriores" com o que mudou), Galeria (miniaturas pelo /img, lightbox simples),
 * Rankings (posição, melhor, dias no topo, variação em 7 d), Vídeos top (só @ público e
 * contadores; link externo com rel=noopener) e Avaliações (nota, data, texto, miniaturas; sem
 * autor). Tudo leitura; textos vêm da rede e entram como texto, nunca como HTML.
 */
import type { MercadoFicha, MercadoImagem, MercadoProdutoDetalhe } from "@sociman/contract";
import { ArrowDown, ArrowUp, ChevronDown, ExternalLink, Image as ImageIcon, Minus, Star } from "lucide-react";
import { useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { formatInteiro, rankingTipoLabel, useAvaliacoes, useFichas, useRankingsProduto, useVideos, type FiltroMercado } from "@/lib/mercado";
import { formatDateKey, formatDateTime } from "@/lib/tz";

const campoLabel: Record<string, string> = {
  titulo: "título",
  descricao: "descrição",
  atributos: "atributos",
  variantes: "variantes",
  argumentos: "argumentos",
  selos: "selos",
  categoria_id: "categoria",
  loja_id: "loja",
  imagens_sha: "imagens",
};

function FichaCorpo({ ficha }: { ficha: MercadoFicha }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="whitespace-pre-line">{ficha.descricao || <span className="text-muted-foreground">sem descrição</span>}</p>
      {ficha.selos.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {ficha.selos.map((s) => (
            <Badge key={s} variant="outline">
              {s}
            </Badge>
          ))}
        </div>
      )}
      {ficha.argumentos.length > 0 && (
        <ul className="list-disc pl-5">
          {ficha.argumentos.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      {ficha.atributos.length > 0 && (
        <table className="w-full text-sm">
          <caption className="sr-only">Atributos</caption>
          <tbody>
            {ficha.atributos.map((a, i) => (
              <tr key={i} className="border-t">
                <th scope="row" className="py-1 pr-3 text-left font-normal text-muted-foreground">
                  {String((a as Record<string, unknown>).nome ?? "")}
                </th>
                <td className="py-1">{String((a as Record<string, unknown>).valor ?? "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ficha.variantes.length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted-foreground">
            {ficha.variantes.length} variante{ficha.variantes.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-1 list-disc pl-5">
            {ficha.variantes.map((v, i) => {
              const r = v as Record<string, unknown>;
              return (
                <li key={i}>
                  {String(r.nome ?? r.redeVarianteId ?? "")}
                  {typeof r.precoCentavos === "number" ? ` · ${(r.precoCentavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}` : ""}
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </div>
  );
}

export function FichaSecao({ produto }: { produto: MercadoProdutoDetalhe }) {
  const [versoes, setVersoes] = useState(false);
  const fichas = useFichas(versoes ? produto.id : "");
  const f = produto.ficha;
  return (
    <HeaderCard
      title="Ficha"
      description={f ? `versão de ${formatDateKey(f.createdAt.slice(0, 10))} · ${produto.nFichas} versão${produto.nFichas === 1 ? "" : "ões"}` : "ainda sem ficha coletada"}
      actions={
        produto.nFichas > 1 ? (
          <Button type="button" size="sm" variant="ghost" aria-expanded={versoes} onClick={() => setVersoes((v) => !v)}>
            <ChevronDown aria-hidden="true" className={versoes ? "rotate-180" : ""} />
            Ver versões anteriores
          </Button>
        ) : null
      }
    >
      {f ? <FichaCorpo ficha={f} /> : <p className="text-sm text-muted-foreground">A primeira visita do coletor traz a ficha completa.</p>}
      {versoes && (
        <div className="mt-4 space-y-3 border-t pt-3" data-testid="ficha-versoes">
          {fichas.isPending && <Skeleton className="h-16 w-full" />}
          {fichas.isError && <ApiErrorAlert error={fichas.error} />}
          {fichas.data?.itens.slice(1).map((v) => (
            <details key={v.id} className="rounded-md border p-2">
              <summary className="cursor-pointer text-sm">
                Versão de {formatDateTime(v.createdAt)}: <span className="font-medium">{v.titulo}</span>
                {Array.isArray(v.diff?.campos) ? <span className="text-muted-foreground"> · a seguinte mudou {(v.diff.campos as string[]).map((c) => campoLabel[c] ?? c).join(", ")}</span> : null}
              </summary>
              <div className="mt-2">
                <FichaCorpo ficha={v} />
              </div>
            </details>
          ))}
          {Array.isArray(fichas.data?.itens[0]?.diff?.campos) && (
            <p className="text-xs text-muted-foreground">Na versão atual mudou: {(fichas.data.itens[0].diff.campos as string[]).map((c) => campoLabel[c] ?? c).join(", ")}.</p>
          )}
        </div>
      )}
    </HeaderCard>
  );
}

export function GaleriaSecao({ imagens }: { imagens: MercadoImagem[] }) {
  const [aberta, setAberta] = useState<MercadoImagem | null>(null);
  return (
    <HeaderCard title="Galeria" description={`${imagens.length} imagem${imagens.length === 1 ? "" : "ns"} original${imagens.length === 1 ? "" : "is"} da página`}>
      {imagens.length ? (
        <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4" aria-label="Imagens do produto">
          {imagens.map((img) => (
            <li key={img.id} className="overflow-hidden rounded-md bg-muted">
              <button type="button" className="block size-full" onClick={() => setAberta(img)} aria-label={`Ampliar imagem ${img.posicao + 1}`}>
                <img src={img.url} alt={`Imagem ${img.posicao + 1} do produto`} className="aspect-square size-full object-cover" loading="lazy" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Nenhuma imagem recebida ainda.</p>
      )}
      <Dialog open={aberta !== null} onOpenChange={(o) => !o && setAberta(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Imagem {aberta ? aberta.posicao + 1 : ""}</DialogTitle>
            <DialogDescription>
              {aberta ? `${aberta.width}×${aberta.height} · ${Math.round(aberta.bytes / 1024)} KB` : ""}
              {aberta && (
                <a href={aberta.original.url} target="_blank" rel="noopener noreferrer" className="ml-2 inline-flex items-center gap-1 underline">
                  <ExternalLink className="size-3" aria-hidden="true" />
                  original
                </a>
              )}
            </DialogDescription>
          </DialogHeader>
          {aberta && <img src={aberta.original.url} alt={`Imagem ${aberta.posicao + 1} do produto, ampliada`} className="max-h-[70vh] w-full object-contain" />}
        </DialogContent>
      </Dialog>
    </HeaderCard>
  );
}

export function RankingsSecao({ produtoId, filtro }: { produtoId: string; filtro: Pick<FiltroMercado, "de" | "ate"> }) {
  const q = useRankingsProduto(produtoId, filtro);
  const resumo = q.data?.resumo ?? [];
  return (
    <HeaderCard title="Rankings" description="Posição atual, melhor posição, dias no topo (≤ 10) e variação em 7 dias, por ranking do Affiliate Center.">
      {q.isPending && <Skeleton className="h-12 w-full" />}
      {q.isError && <ApiErrorAlert error={q.error} />}
      {q.data && resumo.length === 0 && <p className="text-sm text-muted-foreground">Fora dos rankings coletados no período.</p>}
      {resumo.length > 0 && (
        <table className="w-full text-sm" data-testid="rankings-produto">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1 font-normal">Ranking</th>
              <th className="py-1 text-right font-normal">Atual</th>
              <th className="py-1 text-right font-normal">Melhor</th>
              <th className="py-1 text-right font-normal">Dias no topo</th>
              <th className="py-1 text-right font-normal">7 dias</th>
            </tr>
          </thead>
          <tbody>
            {resumo.map((r, i) => (
              <tr key={i} className="border-t">
                <td className="py-1">
                  {rankingTipoLabel[r.tipo]} · {r.janela}
                  {r.categoria ? <span className="text-muted-foreground"> · {r.categoria.caminho}</span> : null}
                </td>
                <td className="py-1 text-right tabular-nums">{r.posicaoAtual ?? <span className="text-muted-foreground">saiu{r.saiuEm ? ` em ${formatDateKey(r.saiuEm)}` : ""}</span>}</td>
                <td className="py-1 text-right tabular-nums">{r.melhorPosicao ?? "—"}</td>
                <td className="py-1 text-right tabular-nums">{r.diasNoTopo}</td>
                <td className="py-1 text-right tabular-nums">
                  <Variacao delta={r.variacao7d ?? null} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </HeaderCard>
  );
}

export function Variacao({ delta, variacao }: { delta: number | null; variacao?: string }) {
  if (variacao === "novo") return <Badge variant="outline">novo</Badge>;
  if (delta === null || delta === undefined) return <span className="text-muted-foreground">—</span>;
  if (delta > 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-success">
        <ArrowUp className="size-3" aria-hidden="true" />
        <span className="sr-only">subiu </span>
        {delta}
      </span>
    );
  if (delta < 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-destructive">
        <ArrowDown className="size-3" aria-hidden="true" />
        <span className="sr-only">caiu </span>
        {Math.abs(delta)}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-0.5 text-muted-foreground">
      <Minus className="size-3" aria-hidden="true" />
      <span className="sr-only">igual</span>
    </span>
  );
}

export function VideosSecao({ produtoId, filtro }: { produtoId: string; filtro: Pick<FiltroMercado, "de" | "ate"> }) {
  const q = useVideos(produtoId, filtro);
  return (
    <HeaderCard title="Vídeos top" description="Os vídeos que mais venderam o produto: só o @ público do criador e os contadores.">
      {q.isPending && <Skeleton className="h-12 w-full" />}
      {q.isError && <ApiErrorAlert error={q.error} />}
      {q.data && q.data.itens.length === 0 && <p className="text-sm text-muted-foreground">Nenhum vídeo coletado no período.</p>}
      {q.data && q.data.itens.length > 0 && (
        <ul className="divide-y text-sm" aria-label="Vídeos top">
          {q.data.itens.map((v) => (
            <li key={`${v.redeVideoId}-${v.dataLocal}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className="w-6 text-muted-foreground tabular-nums">{v.posicao ?? ""}</span>
              <span className="font-medium">@{v.autorHandle}</span>
              <span className="text-muted-foreground tabular-nums">
                {formatInteiro(v.views)} views · {formatInteiro(v.likes)} likes · {formatInteiro(v.comentarios)} comentários
              </span>
              {v.legenda && <span className="line-clamp-1 flex-1 text-muted-foreground">{v.legenda}</span>}
              {v.url && (
                <a href={v.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline">
                  <ExternalLink className="size-3" aria-hidden="true" />
                  abrir
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </HeaderCard>
  );
}

export function AvaliacoesSecao({ produtoId }: { produtoId: string }) {
  const [nota, setNota] = useState("");
  const [comFotos, setComFotos] = useState("");
  const q = useAvaliacoes(produtoId, {
    ...(nota ? { nota: Number(nota) } : {}),
    ...(comFotos ? { comFotos: comFotos === "1" } : {}),
  });
  const r = q.data?.resumo;
  return (
    <HeaderCard
      title="Avaliações"
      description={r ? `${formatInteiro(r.total)} ${r.total === 1 ? "avaliação" : "avaliações"} · ${formatInteiro(r.comFotos)} com foto · nunca mostramos quem escreveu` : "Carregando…"}
      actions={
        <div className="flex gap-2">
          <Field label="Nota" className="w-24">
            {({ id }) => (
              <NativeSelect id={id} value={nota} onChange={(e) => setNota(e.target.value)}>
                <option value="">Todas</option>
                {[5, 4, 3, 2, 1].map((n) => (
                  <option key={n} value={n}>
                    {n} ★{r ? ` (${r.porNota[String(n)] ?? 0})` : ""}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Fotos" className="w-28">
            {({ id }) => (
              <NativeSelect id={id} value={comFotos} onChange={(e) => setComFotos(e.target.value)}>
                <option value="">Todas</option>
                <option value="1">Com foto</option>
                <option value="0">Sem foto</option>
              </NativeSelect>
            )}
          </Field>
        </div>
      }
    >
      {q.isPending && <Skeleton className="h-12 w-full" />}
      {q.isError && <ApiErrorAlert error={q.error} />}
      {q.data && q.data.itens.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma avaliação neste recorte.</p>}
      {q.data && q.data.itens.length > 0 && (
        <ul className="divide-y" aria-label="Avaliações">
          {q.data.itens.map((a) => (
            <li key={a.id} className="space-y-1 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {a.nota !== null && a.nota !== undefined && (
                  <span className="inline-flex items-center gap-0.5 text-foreground" aria-label={`${a.nota} de 5`}>
                    {Array.from({ length: a.nota }, (_, i) => (
                      <Star key={i} className="size-3 fill-current" aria-hidden="true" />
                    ))}
                  </span>
                )}
                {a.dataAvaliacao && <span>{formatDateKey(a.dataAvaliacao)}</span>}
                {a.variante && <span>· {a.variante}</span>}
                {a.curtidas ? <span>· {formatInteiro(a.curtidas)} curtidas</span> : null}
              </div>
              <p className="whitespace-pre-line">{a.texto || <span className="text-muted-foreground">sem texto</span>}</p>
              {a.imagens.length > 0 && (
                <ul className="flex flex-wrap gap-1" aria-label="Fotos da avaliação">
                  {a.imagens.map((img) => (
                    <li key={img.id}>
                      <a href={img.original.url} target="_blank" rel="noopener noreferrer">
                        <img src={img.url} alt="Foto enviada na avaliação" className="size-16 rounded object-cover" loading="lazy" />
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
      {!q.isPending && !q.isError && q.data && q.data.itens.length === 0 && r?.total === 0 && (
        <p className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
          <ImageIcon className="size-3" aria-hidden="true" />
          As avaliações chegam na primeira visita do coletor a um produto quente.
        </p>
      )}
    </HeaderCard>
  );
}
