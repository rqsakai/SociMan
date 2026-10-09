/*
 * Gráfico de linhas em SVG próprio (spec 016, R14): sem biblioteca e sem mudar a CSP.
 *
 * <LinhaChart titulo series pontos formatX formatY marcadores? altura? />
 *   series: 1 a 4 { label, cor } ("primary" | "success" | "warning" | "info", tokens do tema)
 *   pontos: { x, y: (number | null)[] } na ordem de x; y[i] é o valor da série i (null = sem dado)
 *   marcadores: linhas verticais (vídeos publicados na conta; 1 h/24 h/7 d/30 d no vídeo)
 *
 * Mouse: o ponto mais próximo mostra a dica. Teclado: foco no gráfico e setas (Home/End), Esc
 * fecha. Leitor de tela: role="img" com o `titulo` e uma tabela escondida com todos os pontos.
 */
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { cn } from "@/lib/utils";

export type SerieCor = "primary" | "success" | "warning" | "info";

export interface Serie {
  label: string;
  cor: SerieCor;
}

export interface Ponto {
  x: number;
  y: (number | null)[];
}

export interface Marcador {
  x: number;
  label: string;
}

const traco: Record<SerieCor, string> = {
  primary: "stroke-primary",
  success: "stroke-success",
  warning: "stroke-warning",
  info: "stroke-info",
};
const preenchimento: Record<SerieCor, string> = {
  primary: "fill-primary",
  success: "fill-success",
  warning: "fill-warning",
  info: "fill-info",
};
const fundo: Record<SerieCor, string> = {
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  info: "bg-info",
};

// Ticks "bonitos" (1, 2, 2,5, 5 × 10^n) cobrindo [min, max].
export function ticksBonitos(min: number, max: number, alvo = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0];
  if (min === max) max = min + 1;
  const bruto = (max - min) / Math.max(1, alvo);
  const mag = 10 ** Math.floor(Math.log10(bruto));
  const passo = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= bruto) ?? 10) * mag;
  const ini = Math.floor(min / passo) * passo;
  const out: number[] = [];
  for (let v = ini; v <= max + passo * 0.5; v += passo) out.push(Math.round(v / passo) * passo);
  return out;
}

const PAD = { top: 16, right: 12, bottom: 28, left: 52 };

export function LinhaChart({
  titulo,
  series,
  pontos,
  formatX,
  formatY,
  marcadores = [],
  altura = 240,
  className,
}: {
  titulo: string;
  series: Serie[];
  pontos: Ponto[];
  formatX: (x: number) => string;
  formatY: (y: number) => string;
  marcadores?: Marcador[];
  altura?: number;
  className?: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [largura, setLargura] = useState(640);
  const [ativo, setAtivo] = useState<number | null>(null);
  const dicaId = useId();

  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => {
      const w = Math.round(e?.contentRect.width ?? 0);
      if (w > 0) setLargura(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const escala = useMemo(() => {
    const xs = [...pontos.map((p) => p.x), ...marcadores.map((m) => m.x)];
    let xMin = Math.min(...xs);
    let xMax = Math.max(...xs);
    if (!Number.isFinite(xMin)) [xMin, xMax] = [0, 1];
    if (xMin === xMax) [xMin, xMax] = [xMin - 1, xMax + 1];
    const ys = pontos.flatMap((p) => p.y.filter((v): v is number => v !== null));
    const yTicks = ticksBonitos(Math.min(0, ...ys), ys.length ? Math.max(...ys) : 1);
    const yMin = yTicks[0] ?? 0;
    const yMax = yTicks[yTicks.length - 1] ?? 1;
    const w = Math.max(160, largura) - PAD.left - PAD.right;
    const h = altura - PAD.top - PAD.bottom;
    const sx = (x: number) => PAD.left + ((x - xMin) / (xMax - xMin)) * w;
    const sy = (y: number) => PAD.top + h - ((y - yMin) / (yMax - yMin || 1)) * h;
    const nx = Math.max(2, Math.min(6, Math.floor(w / 110)));
    const xTicks = Array.from({ length: nx }, (_, i) => xMin + ((xMax - xMin) * i) / (nx - 1));
    return { sx, sy, xTicks, yTicks, w, h };
  }, [pontos, marcadores, largura, altura]);

  const caminhos = series.map((_, si) => {
    let d = "";
    let aberto = false;
    for (const p of pontos) {
      const v = p.y[si];
      if (v === null || v === undefined) {
        aberto = false;
        continue;
      }
      d += `${aberto ? "L" : "M"}${escala.sx(p.x).toFixed(1)},${escala.sy(v).toFixed(1)}`;
      aberto = true;
    }
    return d;
  });

  function maisProximo(clientX: number) {
    const el = wrapRef.current;
    if (!el || pontos.length === 0) return null;
    const x = clientX - el.getBoundingClientRect().left;
    let melhor = 0;
    for (let i = 1; i < pontos.length; i++) {
      if (Math.abs(escala.sx(pontos[i]!.x) - x) < Math.abs(escala.sx(pontos[melhor]!.x) - x)) melhor = i;
    }
    return melhor;
  }

  function onKey(e: KeyboardEvent) {
    if (pontos.length === 0) return;
    const ult = pontos.length - 1;
    const mapa: Record<string, number> = {
      ArrowRight: Math.min(ult, (ativo ?? -1) + 1),
      ArrowLeft: Math.max(0, (ativo ?? ult + 1) - 1),
      Home: 0,
      End: ult,
    };
    if (e.key in mapa) {
      e.preventDefault();
      setAtivo(mapa[e.key]!);
    } else if (e.key === "Escape") {
      setAtivo(null);
    }
  }

  const ponto = ativo !== null ? pontos[ativo] : undefined;
  const dicaEsquerda = ponto ? escala.sx(ponto.x) : 0;
  const poucosMarcadores = marcadores.length <= 6;

  return (
    <div className={cn("space-y-2", className)}>
      {series.length > 1 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-hidden="true">
          {series.map((s) => (
            <li key={s.label} className="flex items-center gap-1.5">
              <span className={cn("size-2.5 rounded-full", fundo[s.cor])} />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <div ref={wrapRef} className="relative w-full">
        <svg
          role="img"
          aria-label={`${titulo}. Use as setas para percorrer os pontos.`}
          aria-describedby={dicaId}
          tabIndex={0}
          width="100%"
          height={altura}
          className="block rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          onKeyDown={onKey}
          onBlur={() => setAtivo(null)}
          onPointerMove={(e: PointerEvent) => setAtivo(maisProximo(e.clientX))}
          onPointerLeave={() => setAtivo(null)}
        >
          {/* grade e eixo Y */}
          {escala.yTicks.map((t) => (
            <g key={`y${t}`}>
              <line x1={PAD.left} x2={PAD.left + escala.w} y1={escala.sy(t)} y2={escala.sy(t)} className="stroke-border" strokeWidth={1} />
              <text x={PAD.left - 6} y={escala.sy(t)} textAnchor="end" dominantBaseline="middle" className="fill-muted-foreground text-[10px]">
                {formatY(t)}
              </text>
            </g>
          ))}
          {/* eixo X */}
          {escala.xTicks.map((t, i) => (
            <text
              key={`x${i}`}
              x={escala.sx(t)}
              y={altura - 8}
              textAnchor={i === 0 ? "start" : i === escala.xTicks.length - 1 ? "end" : "middle"}
              className="fill-muted-foreground text-[10px]"
            >
              {formatX(t)}
            </text>
          ))}
          {/* marcadores verticais */}
          {marcadores.map((m, i) => (
            <g key={`m${i}`}>
              <line
                x1={escala.sx(m.x)}
                x2={escala.sx(m.x)}
                y1={PAD.top}
                y2={PAD.top + escala.h}
                className="stroke-muted-foreground/50"
                strokeWidth={1}
                strokeDasharray="3 3"
              >
                <title>{m.label}</title>
              </line>
              {poucosMarcadores ? (
                <text x={escala.sx(m.x) + 3} y={PAD.top - 4} className="fill-muted-foreground text-[10px]">
                  {m.label}
                </text>
              ) : (
                <circle cx={escala.sx(m.x)} cy={PAD.top + escala.h} r={3} className="fill-muted-foreground">
                  <title>{m.label}</title>
                </circle>
              )}
            </g>
          ))}
          {/* séries */}
          {series.map((s, si) => (
            <path key={s.label} d={caminhos[si]} fill="none" className={traco[s.cor]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {pontos.length === 1 &&
            series.map((s, si) => {
              const v = pontos[0]!.y[si];
              return v === null || v === undefined ? null : <circle key={s.label} cx={escala.sx(pontos[0]!.x)} cy={escala.sy(v)} r={3} className={preenchimento[s.cor]} />;
            })}
          {/* ponto ativo */}
          {ponto && (
            <g>
              <line x1={escala.sx(ponto.x)} x2={escala.sx(ponto.x)} y1={PAD.top} y2={PAD.top + escala.h} className="stroke-foreground/30" strokeWidth={1} />
              {series.map((s, si) => {
                const v = ponto.y[si];
                return v === null || v === undefined ? null : (
                  <circle key={s.label} cx={escala.sx(ponto.x)} cy={escala.sy(v)} r={4} className={cn(preenchimento[s.cor], "stroke-card")} strokeWidth={2} />
                );
              })}
            </g>
          )}
        </svg>
        {ponto && (
          <div
            className="pointer-events-none absolute top-2 z-10 min-w-36 rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md"
            style={dicaEsquerda > largura / 2 ? { right: largura - dicaEsquerda + 8 } : { left: dicaEsquerda + 8 }}
          >
            <p className="font-medium">{formatX(ponto.x)}</p>
            {series.map((s, si) => (
              <p key={s.label} className="flex items-center gap-1.5 tabular-nums">
                <span className={cn("size-2 rounded-full", fundo[s.cor])} aria-hidden="true" />
                {s.label}: {ponto.y[si] === null || ponto.y[si] === undefined ? "—" : formatY(ponto.y[si]!)}
              </p>
            ))}
          </div>
        )}
        <p id={dicaId} className="sr-only" aria-live="polite">
          {ponto ? `${formatX(ponto.x)}: ${series.map((s, si) => `${s.label} ${ponto.y[si] === null || ponto.y[si] === undefined ? "sem dado" : formatY(ponto.y[si]!)}`).join(", ")}` : ""}
        </p>
      </div>
      <table className="sr-only">
        <caption>{titulo}</caption>
        <thead>
          <tr>
            <th scope="col">Momento</th>
            {series.map((s) => (
              <th key={s.label} scope="col">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pontos.map((p, i) => (
            <tr key={i}>
              <th scope="row">{formatX(p.x)}</th>
              {series.map((s, si) => (
                <td key={s.label}>{p.y[si] === null || p.y[si] === undefined ? "—" : formatY(p.y[si]!)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
