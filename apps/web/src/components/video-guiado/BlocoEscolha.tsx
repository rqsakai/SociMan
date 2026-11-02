import { Check, ImageOff, Mic } from "lucide-react";
import { useId, useRef, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Audio } from "../../lib/geracoes";
import { PlayerAudio } from "../geracao/PlayerAudio";

export interface ItemEscolha {
  id: string;
  titulo: string;
  subtitulo?: string;
  thumbUrl?: string | null;
  desabilitado?: boolean;
  // Por que o item está desabilitado (lido junto do título).
  motivo?: string;
  // Só na variante "voz": o áudio de teste (sem ele, o cartão mostra só o nome).
  audio?: Audio | null;
}

export interface BlocoEscolhaProps {
  rotulo: string;
  itens: ItemEscolha[];
  valor: string | null;
  onChange: (id: string) => void;
  // "texto": cartões só com o título (perfil, tipo de vídeo, duração).
  variante?: "imagem" | "voz" | "texto";
  descricao?: string;
  carregando?: boolean;
  // Estado vazio: o texto e o link para o cadastro.
  vazio?: { titulo: string; descricao?: string; acao: string; href: string };
  // Os itens que ficaram de fora da lista (ex.: "3 fora (sem kit completo)").
  fora?: { quantidade: number; motivo: string };
  // A variante "voz" pede um link novo do áudio quando o navegador não consegue tocar.
  onRenovarAudio?: (id: string) => void;
}

const PROXIMO: Partial<Record<string, number>> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

// Um bloco de escolha do vídeo guiado (spec 031, T020, R10): cartões com imagem num `radiogroup`
// (padrão do `ProfileImagePicker`, sem o radio-group do shadcn), com o foco itinerante (só o
// marcado, ou o 1º habilitado, entra no Tab; as setas andam e escolhem, pulando os desabilitados,
// e Home/End vão às pontas). A variante "voz" põe o player do áudio de teste FORA do botão
// (controle dentro de botão é HTML inválido).
export function BlocoEscolha({
  rotulo,
  itens,
  valor,
  onChange,
  variante = "imagem",
  descricao,
  carregando = false,
  vazio,
  fora,
  onRenovarAudio,
}: BlocoEscolhaProps) {
  const rotuloId = useId();
  const descricaoId = useId();
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const habilitados = itens.filter((i) => !i.desabilitado);
  const focavel = habilitados.some((i) => i.id === valor) ? valor : (habilitados[0]?.id ?? null);

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, id: string) {
    const pos = habilitados.findIndex((i) => i.id === id);
    const passo = PROXIMO[e.key];
    let alvo: ItemEscolha | undefined;
    if (passo !== undefined) alvo = habilitados[(pos + passo + habilitados.length) % habilitados.length];
    else if (e.key === "Home") alvo = habilitados[0];
    else if (e.key === "End") alvo = habilitados.at(-1);
    if (!alvo) return;
    e.preventDefault();
    refs.current.get(alvo.id)?.focus();
    if (alvo.id !== valor) onChange(alvo.id);
  }

  return (
    <section className="flex min-w-0 flex-col gap-3" aria-busy={carregando}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={rotuloId} className="text-sm font-medium">
          {rotulo}
        </h3>
        {fora && fora.quantidade > 0 && (
          <p className="text-xs text-muted-foreground" data-testid="bloco-fora">
            {fora.quantidade} fora ({fora.motivo})
          </p>
        )}
      </div>
      {descricao && (
        <p id={descricaoId} className="-mt-2 text-xs text-muted-foreground">
          {descricao}
        </p>
      )}
      {itens.length === 0 ? (
        carregando ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : (
          vazio && (
            <EmptyState
              titulo={vazio.titulo}
              descricao={vazio.descricao}
              className="items-start rounded-lg border border-dashed px-4 py-4 text-left"
              acao={
                <Button asChild size="sm" variant="outline">
                  <Link to={vazio.href}>{vazio.acao}</Link>
                </Button>
              }
            />
          )
        )
      ) : (
        <div
          role="radiogroup"
          aria-labelledby={rotuloId}
          aria-describedby={descricao ? descricaoId : undefined}
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
        >
          {itens.map((item) => {
            const marcado = item.id === valor;
            const radio = (
              <button
                ref={(el) => {
                  if (el) refs.current.set(item.id, el);
                  else refs.current.delete(item.id);
                }}
                type="button"
                role="radio"
                aria-checked={marcado}
                aria-disabled={item.desabilitado || undefined}
                aria-label={[item.titulo, item.subtitulo, item.desabilitado && item.motivo].filter(Boolean).join(". ")}
                tabIndex={item.id === focavel ? 0 : -1}
                disabled={item.desabilitado}
                onClick={() => onChange(item.id)}
                onKeyDown={(e) => onKeyDown(e, item.id)}
                className={cn(
                  "group relative flex w-full min-w-0 flex-col text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed",
                  variante === "imagem" && "overflow-hidden rounded-lg border bg-card",
                  variante === "imagem" && marcado && "border-primary ring-2 ring-primary",
                  variante === "texto" && "rounded-lg border bg-card p-3",
                  variante === "texto" && marcado && "border-primary ring-2 ring-primary",
                  item.desabilitado && "opacity-60",
                )}
              >
                {variante === "imagem" && (
                  <span className="flex aspect-[3/4] w-full items-center justify-center bg-muted">
                    {item.thumbUrl ? (
                      <img src={item.thumbUrl} alt="" loading="lazy" className="size-full object-cover" />
                    ) : (
                      <ImageOff className="size-6 text-muted-foreground" aria-hidden="true" />
                    )}
                  </span>
                )}
                <span className={cn("flex min-w-0 items-start gap-2", variante === "imagem" && "p-2")}>
                  {variante === "voz" && <Mic className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-sm font-medium">{item.titulo}</span>
                    {item.subtitulo && <span className="truncate text-xs text-muted-foreground">{item.subtitulo}</span>}
                    {item.desabilitado && item.motivo && <span className="text-xs text-muted-foreground">{item.motivo}</span>}
                  </span>
                  {marcado && <Check className="size-4 shrink-0 text-primary" aria-hidden="true" />}
                </span>
              </button>
            );
            if (variante !== "voz") return <div key={item.id}>{radio}</div>;
            return (
              <div
                key={item.id}
                className={cn(
                  "flex min-w-0 flex-col gap-2 rounded-lg border bg-card p-3",
                  marcado && "border-primary ring-2 ring-primary",
                )}
              >
                {radio}
                {item.audio && (
                  <PlayerAudio audio={item.audio} rotulo={`Teste da voz ${item.titulo}`} onRenovar={() => onRenovarAudio?.(item.id)} />
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
