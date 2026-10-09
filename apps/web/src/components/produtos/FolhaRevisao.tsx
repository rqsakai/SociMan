import { ImageOff, Loader2 } from "lucide-react";
import type { CSSProperties } from "react";
import { passoAberto, ultimoPasso, variantesAtivas, type Produto, type ProdutoImagem, type ProdutoVariante } from "@/lib/produtos";

type Linha = "original" | "recorte" | "flat";
const linhaLabel: Record<Linha, string> = { original: "Original", recorte: "Recorte", flat: "Flat lay" };

// Folha de revisão (spec 012, US3, T033; FR-017): as fotos originais, os recortes e os flats, numerados
// por variante ativa. Na tela larga, uma coluna por variante com as três linhas alinhadas; no celular
// (SC-007), as colunas empilham (original, recorte e flat de cada variante), sem rolar na horizontal.
export function FolhaRevisao({ produto }: { produto: Produto }) {
  const ativas = variantesAtivas(produto);
  const comFlat = Boolean(produto.ficha?.precisaFlat) || ativas.some((v) => v.flat);
  const linhas: Linha[] = comFlat ? ["original", "recorte", "flat"] : ["original", "recorte"];
  if (ativas.length === 0) return <p className="text-sm text-muted-foreground">Nenhuma variante ativa. Envie uma foto em "Variantes".</p>;

  return (
    <ol
      aria-label="Folha de revisão"
      data-testid="folha-revisao"
      className="grid gap-4 sm:grid-cols-[repeat(var(--colunas),minmax(0,1fr))]"
      style={{ "--colunas": Math.min(ativas.length, 6) } as CSSProperties}
    >
      {ativas.map((v, i) => (
        <li key={v.id} aria-label={`Variante ${i + 1}`} className="min-w-0 space-y-2" data-testid={`folha-variante-${i + 1}`}>
          <p className="truncate text-sm font-semibold">
            {i + 1}. {v.corPt ?? "Sem cor"}
          </p>
          {linhas.map((linha) => (
            <Celula key={linha} produto={produto} variante={v} linha={linha} numero={i + 1} />
          ))}
        </li>
      ))}
    </ol>
  );
}

function Celula({ produto, variante, linha, numero }: { produto: Produto; variante: ProdutoVariante; linha: Linha; numero: number }) {
  const imagem: ProdutoImagem | null = variante[linha];
  const rotulo = `${linhaLabel[linha]} ${numero}`;
  const passo = linha === "original" ? undefined : ultimoPasso(produto, `produto.${linha}`, variante.id);
  const gerando = passo && passoAberto(passo.status);
  const vazio =
    linha === "flat" && !produto.ficha?.precisaFlat
      ? "Não usa flat"
      : gerando
        ? "Gerando…"
        : passo?.status === "revisao"
          ? "Escolha uma opção"
          : passo?.status === "falhou"
            ? "Falhou"
            : linha === "recorte"
              ? "Sem recorte"
              : "Sem flat";

  return (
    <figure className="space-y-1" data-testid={`folha-${linha}-${numero}`}>
      {imagem ? (
        <a href={imagem.url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg border bg-white">
          <img src={imagem.thumbUrl} alt={rotulo} width={imagem.largura} height={imagem.altura} loading="lazy" className="aspect-square h-auto w-full object-contain" />
        </a>
      ) : (
        <div className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-lg border border-dashed bg-muted/40 text-xs text-muted-foreground">
          {gerando ? <Loader2 className="size-5 animate-spin" aria-hidden="true" /> : <ImageOff className="size-5" aria-hidden="true" />}
          <span>{vazio}</span>
        </div>
      )}
      <figcaption className="text-xs text-muted-foreground">
        {rotulo}
        {linha === "flat" && imagem && !produto.ficha?.precisaFlat && " (guardado, fora do render)"}
      </figcaption>
    </figure>
  );
}
