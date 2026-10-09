import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { cn } from "@/lib/utils";
import { resolveColor, withAlpha, type KitTokens, type PosicaoMarca } from "../../lib/marca";
import { fontStack } from "./useKitFonts";

// Prévia do kit em CSS sobre um quadro 9:16 (R7, FR-008). As contas seguem os geradores:
// - legenda: o cálculo do OpenShorts (px = tamanho × 0,85 / 288 × altura; margem 43/288);
// - gancho: a geometria do renderizador Pillow (R2) numa base de 1080 px de largura;
// - marca d'água e card final: as mesmas regras do compose (escala e margem em % da largura).
// É aproximada: o resultado final sai do processamento.

export type PreviewMoment = "inicio" | "fim";

export interface KitPreviewProps {
  tokens: KitTokens;
  fontsReady: Set<string>;
  hookText?: string;
  captionText?: string;
  logoUrl?: string | null;
  watermarkImageUrl?: string | null;
  handle?: string | null;
  backgroundUrl?: string | null;
  // Imagem de fundo do gancho e do card final (FR-005a), só com o tipo de fundo "imagem".
  hookImageUrl?: string | null;
  endCardImageUrl?: string | null;
  moment: PreviewMoment;
  className?: string;
}

const HOOK_SIZE = { P: 0.8, M: 1, G: 1.3 } as const;

function useFrameSize() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 270, h: 480 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return { ref, ...size };
}

// Contorno por fora do texto: o traço é centrado na borda, então o dobro com `paint-order`.
function stroke(width: number, color: string): CSSProperties {
  if (width <= 0) return {};
  return { WebkitTextStroke: `${width * 2}px ${color}`, paintOrder: "stroke fill" };
}

// Fundo de uma área: a imagem em cover com a camada da cor × opacidade por cima (como o compose);
// sem imagem, só a cor.
function areaBackground(rgba: string, imageUrl: string | null | undefined): CSSProperties {
  if (!imageUrl) return { backgroundColor: rgba };
  return {
    backgroundImage: `linear-gradient(${rgba}, ${rgba}), url(${JSON.stringify(imageUrl)})`,
    backgroundSize: "cover",
    backgroundPosition: "center",
  };
}

function watermarkPlacement(pos: PosicaoMarca, marginPx: number): CSSProperties {
  const style: CSSProperties = { position: "absolute" };
  if (pos.startsWith("sup") || pos === "centro_sup") style.top = marginPx;
  else style.bottom = marginPx;
  if (pos.endsWith("esq")) style.left = marginPx;
  else if (pos.endsWith("dir")) style.right = marginPx;
  else {
    style.left = "50%";
    style.transform = "translateX(-50%)";
  }
  return style;
}

export function KitPreview({
  tokens,
  fontsReady,
  hookText = "3 achadinhos que salvaram minha cozinha",
  captionText = "Olha esse achadinho",
  logoUrl,
  watermarkImageUrl,
  handle,
  backgroundUrl,
  hookImageUrl,
  endCardImageUrl,
  moment,
  className,
}: KitPreviewProps) {
  const { ref, w, h } = useFrameSize();
  const { palette, caption, hook, watermark, endCard } = tokens;
  const color = (ref: string) => resolveColor(ref, palette);
  const unit = w / 1080; // base de 1080 px de largura (vídeo vertical padrão)

  // Legenda (OpenShorts): fonte e margem proporcionais à altura. O Fontsize do ASS (libass) é a
  // altura da linha (ascendente + descendente), não o em do CSS; ~1,3 em nas fontes padrão.
  // Valores fora da faixa (ainda sendo digitados) entram presos à faixa, como no gerador.
  const clamp = (v: number, min: number, max: number) => (Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : min);
  const capPx = (clamp(caption.tamanho, 10, 200) * 0.85 * h) / 288 / 1.3;
  const capMargin = (43 * h) / 288;
  const capOutline = (clamp(caption.espessura_contorno, 0, 10) * h) / 288;
  const words = (caption.maiusculas ? captionText.toUpperCase() : captionText).split(" ");
  const highlight = caption.estilo === "karaoke" ? Math.min(1, words.length - 1) : -1;
  const capPosition: CSSProperties =
    caption.posicao === "base"
      ? { bottom: capMargin }
      : caption.posicao === "topo"
        ? { top: capMargin }
        : { top: "50%", transform: "translateY(-50%)" };

  // Gancho (render.py): caixa de 27% a 90% da largura, fonte = 5% da caixa máxima × P/M/G,
  // padding 30/25, entrelinha 20, raio 20 (base 1080).
  const hookPx = 0.05 * 0.9 * w * HOOK_SIZE[hook.tamanho];
  const hookPosition: CSSProperties =
    hook.posicao === "topo"
      ? { top: h * 0.12 }
      : hook.posicao === "base"
        ? { top: h * 0.7 }
        : { top: "50%", transform: "translateY(-50%)" }; // o X vem da classe (propriedade `translate`)

  // Marca d'água: largura = escala% da largura; margem em % da largura.
  const wmWidth = (clamp(watermark.escala_pct, 5, 40) / 100) * w;
  const wmMargin = (clamp(watermark.margem_pct, 0, 10) / 100) * w;
  const handleText = handle ? `@${handle.replace(/^@/, "")}` : "@perfil";
  // Texto: a fonte é ajustada para o @ ocupar a largura da escala (medido no canvas).
  const wmFamily = fontStack(watermark.fonte, fontsReady);
  const wmTextPx = useMemo(() => {
    const ctx = document.createElement("canvas").getContext("2d");
    if (!ctx) return wmWidth / Math.max(4, handleText.length * 0.55);
    ctx.font = `100px ${wmFamily}`;
    const at100 = ctx.measureText(handleText).width;
    return at100 > 0 ? (wmWidth * 100) / at100 : wmWidth / Math.max(4, handleText.length * 0.55);
  }, [wmFamily, handleText, wmWidth]);

  const showCard = moment === "fim" && endCard.ligado;

  return (
    <div className={cn("space-y-2", className)}>
      <div
        ref={ref}
        role="img"
        aria-label={moment === "fim" ? "Prévia do fim do vídeo" : "Prévia do início do vídeo"}
        className="relative mx-auto aspect-[9/16] w-full max-w-[20rem] overflow-hidden rounded-xl bg-gradient-to-b from-slate-500 via-slate-700 to-slate-900 shadow-card select-none"
        style={
          backgroundUrl
            ? { backgroundImage: `url(${JSON.stringify(backgroundUrl)})`, backgroundSize: "cover", backgroundPosition: "center" }
            : undefined
        }
      >
        {/* Legenda */}
        <p
          data-preview="legenda"
          className="absolute inset-x-[3%] text-center leading-tight break-normal [overflow-wrap:normal]" /* como a legenda real: quebra só entre palavras */
          style={{
            ...capPosition,
            fontFamily: fontStack(caption.fonte, fontsReady),
            fontSize: capPx,
            color: color(caption.cor_texto),
            ...stroke(capOutline, color(caption.cor_contorno)),
          }}
        >
          <span
            className="box-decoration-clone px-[0.2em]"
            style={
              caption.opacidade_fundo > 0
                ? { backgroundColor: withAlpha(color(caption.cor_fundo), caption.opacidade_fundo), borderRadius: "0.15em" }
                : undefined
            }
          >
            {words.map((word, i) => {
              const active = i === highlight;
              const effect: CSSProperties = active
                ? caption.efeito === "pop"
                  ? { display: "inline-block", transform: "scale(1.15)" }
                  : caption.efeito === "brilho"
                    ? { textShadow: `0 0 ${capPx * 0.4}px ${color(caption.cor_destaque)}` }
                    : caption.efeito === "caixa"
                      ? { backgroundColor: color(caption.cor_destaque), color: color(caption.cor_texto), borderRadius: "0.1em", padding: "0 0.1em" }
                      : {}
                : {};
              return (
                <span key={i}>
                  <span
                    style={{
                      ...(active && caption.efeito !== "caixa" ? { color: color(caption.cor_destaque) } : {}),
                      ...effect,
                    }}
                  >
                    {word}
                  </span>
                  {i < words.length - 1 ? " " : ""}
                </span>
              );
            })}
          </span>
        </p>

        {/* Gancho */}
        {moment === "inicio" && hook.ligado && (
          <div
            data-preview="gancho"
            data-fundo={hookImageUrl ? "imagem" : "cor"}
            className="absolute left-1/2 line-clamp-3 w-max max-w-[90%] min-w-[27%] -translate-x-1/2 text-center break-words whitespace-pre-line"
            style={{
              ...hookPosition,
              lineHeight: `${hookPx + 20 * unit}px`,
              padding: `${25 * unit}px ${30 * unit}px`,
              borderRadius: 20 * unit,
              ...areaBackground(withAlpha(color(hook.cor_fundo), hook.opacidade_fundo), hookImageUrl),
              fontFamily: fontStack(hook.fonte, fontsReady),
              fontSize: hookPx,
              color: color(hook.cor_texto),
              ...stroke(clamp(hook.espessura_contorno, 0, 10) * unit, color(hook.cor_contorno)),
            }}
          >
            {hookText}
          </div>
        )}

        {/* Marca d'água */}
        {watermark.ligado && (
          <div data-preview="marca" style={{ ...watermarkPlacement(watermark.posicao, wmMargin), opacity: watermark.opacidade_pct / 100 }}>
            {watermark.tipo === "texto" ? (
              <span
                className="whitespace-nowrap"
                style={{ fontFamily: fontStack(watermark.fonte, fontsReady), fontSize: wmTextPx, color: color(watermark.cor_texto) }}
              >
                {handleText}
              </span>
            ) : (watermark.tipo === "logo" ? logoUrl : watermarkImageUrl) ? (
              <img
                src={(watermark.tipo === "logo" ? logoUrl : watermarkImageUrl) ?? undefined}
                alt=""
                style={{ width: wmWidth }}
                className="h-auto"
              />
            ) : (
              <span
                className="flex aspect-square items-center justify-center rounded border border-dashed border-white/70 text-[10px] text-white"
                style={{ width: wmWidth }}
              >
                {watermark.tipo === "logo" ? "sem logo" : "sem imagem"}
              </span>
            )}
          </div>
        )}

        {/* Card final: por cima de tudo nos últimos segundos */}
        {showCard && (
          <div
            data-preview="card"
            data-fundo={endCardImageUrl ? "imagem" : "cor"}
            className="absolute inset-0 flex flex-col items-center justify-center text-center"
            style={{
              ...areaBackground(
                endCardImageUrl ? withAlpha(color(endCard.cor_fundo), endCard.opacidade_fundo) : color(endCard.cor_fundo),
                endCardImageUrl,
              ),
              gap: h * 0.04,
            }}
          >
            {/* render.py: logo com 35% da largura (altura máx. 25%), 4% da altura de espaço, CTA com
                fonte de 8% da largura, até 85% da largura e 4 linhas */}
            {endCard.mostrar_logo && logoUrl && (
              <img src={logoUrl} alt="" className="object-contain" style={{ width: w * 0.35, maxHeight: h * 0.25 }} />
            )}
            <p
              className="line-clamp-4 max-w-[85%] leading-tight break-words"
              style={{ fontFamily: fontStack(endCard.fonte, fontsReady), fontSize: w * 0.08, color: color(endCard.cor_texto) }}
            >
              {endCard.cta}
            </p>
          </div>
        )}
        {moment === "fim" && !endCard.ligado && (
          <p className="absolute inset-x-0 top-3 text-center text-xs text-white/80">Card final desligado</p>
        )}
      </div>
      <p className="text-center text-xs text-muted-foreground">Prévia aproximada; o resultado final sai do processamento.</p>
    </div>
  );
}
