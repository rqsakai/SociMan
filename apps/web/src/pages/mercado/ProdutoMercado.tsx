/*
 * /app/mercado/produtos/:id (spec 026, US1/US5): o detalhe de um produto de mercado. Cabeçalho com
 * o cartão mínimo, a série (ECharts), e as seções Ficha, Galeria, Rankings, Vídeos e Avaliações
 * (preenchidas na US5). "Acompanhar neste perfil" (US4) e "Adotar no catálogo" (US6) chegam
 * desabilitados até as histórias delas.
 */
import { ExternalLink, Star } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { AcompanharDialog } from "@/components/mercado/AcompanharDialog";
import { AdotarDialog } from "@/components/mercado/AdotarDialog";
import { CartaoProduto } from "@/components/mercado/CartaoProduto";
import { AvaliacoesSecao, FichaSecao, GaleriaSecao, RankingsSecao, VideosSecao } from "@/components/mercado/SecoesProduto";
import { SerieProduto } from "@/components/mercado/SerieProduto";
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useFiltroMercado, useMercadoProduto, useMercadoSerie } from "@/lib/mercado";
import { formatDateKey } from "@/lib/tz";

export default function ProdutoMercado() {
  const { id = "" } = useParams();
  const { filtro } = useFiltroMercado();
  const [acompanhar, setAcompanhar] = useState(false);
  const [adotar, setAdotar] = useState(false);
  const produto = useMercadoProduto(id, filtro);
  const serie = useMercadoSerie(id, filtro);
  const p = produto.data;
  usePageMeta({ title: p?.titulo ?? "Produto", breadcrumbs: [{ label: "Mercado de produtos", to: "/app/mercado" }] });

  if (produto.isPending) return <Skeleton className="h-96 w-full" />;
  if (produto.isError) return <ApiErrorAlert error={produto.error} />;
  if (!p) return null;

  return (
    <Page>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeading
          title={p.titulo ?? p.redeProdutoId}
          description={
            <>
              {p.loja ? `${p.loja.nome}${p.loja.oficial ? " · Loja oficial" : ""}` : "Loja desconhecida"}
              {p.categoria ? ` · ${p.categoria.caminho}` : ""}
              {" · visto pela 1ª vez em "}
              {formatDateKey(p.primeiraVezEm.slice(0, 10))}
            </>
          }
        />
        <div className="flex flex-wrap gap-2">
          <Button asChild type="button" variant="outline" size="sm">
            <a href={p.urlCanonica} target="_blank" rel="noopener noreferrer">
              <ExternalLink aria-hidden="true" />
              Abrir na rede
            </a>
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setAcompanhar(true)} disabled={p.interessesDoUsuario.every((x) => x.interesseId)}>
            <Star aria-hidden="true" />
            Acompanhar neste perfil
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setAdotar(true)} disabled={p.interessesDoUsuario.length === 0}>
            Adotar no catálogo
          </Button>
        </div>
      </div>

      {p.interessesDoUsuario.some((x) => x.interesseId) && (
        <p className="text-sm text-muted-foreground" data-testid="acompanhado-por">
          Acompanhado por: {p.interessesDoUsuario.filter((x) => x.interesseId).map((x) => x.perfilNome).join(", ")}
        </p>
      )}
      <CartaoProduto produto={p} />
      {acompanhar && <AcompanharDialog produto={p} open={acompanhar} onOpenChange={setAcompanhar} />}
      {adotar && <AdotarDialog produto={p} open={adotar} onOpenChange={setAdotar} />}

      <SerieProduto serie={serie.data} carregando={serie.isPending} erro={serie.error} />

      <div className="grid gap-6 lg:grid-cols-2">
        <FichaSecao produto={p} />
        <GaleriaSecao imagens={p.galeria} />
        <RankingsSecao produtoId={p.id} filtro={filtro} />
        <VideosSecao produtoId={p.id} filtro={filtro} />
      </div>
      <AvaliacoesSecao produtoId={p.id} />
    </Page>
  );
}
