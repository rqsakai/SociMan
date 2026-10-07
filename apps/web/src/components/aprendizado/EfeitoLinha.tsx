/*
 * Uma linha de efeito do "por que deu certo" (spec 023, US2; FR-020 a FR-028): o efeito encolhido
 * em palavras ("≈ 2,4× o típico da conta" ou "+35 p.p. de chance de sair do zero"), o intervalo
 * plausível, o n de posts e de dias distintos, a confiança em palavras e os avisos. Abaixo da amostra
 * mínima, só os números brutos e "faltam N posts". Tudo vem calculado da API; aqui só se formata.
 */
import { TriangleAlert, TrendingDown, TrendingUp } from "lucide-react";
import { confiancaLabel, confiancaTom, formatEfeito, formatIntervalo, fraseEfeito, rotuloFator, type AprendizadoEfeito } from "@/lib/aprendizado";
import { formatNumero } from "@/lib/metricas";
import { cn } from "@/lib/utils";

type Aviso = AprendizadoEfeito["avisos"][number];

export function textoAviso(a: Aviso, parte: AprendizadoEfeito["parte"]): string {
  switch (a.tipo) {
    case "puxado_por_1":
      return `puxado por 1 post${a.semMaior !== null && a.semMaior !== undefined ? ` (sem o maior post: ${formatEfeito(parte, a.semMaior)})` : ""}`;
    case "nao_separavel":
      return `não separável do tema ${a.temaNome ?? "principal"}`;
    case "quase_so_com":
      return `quase só com ${a.fator ? rotuloFator(a.fator).toLowerCase() : "outro fator"}${a.valor ? ` = ${a.valor}` : ""}: não separável`;
    case "travada":
      return "conta com distribuição travada: só indício";
    case "em_alta":
      return "em alta nos últimos 30 dias";
    case "em_queda":
      return "em queda nos últimos 30 dias";
    default:
      return String(a.tipo);
  }
}

export function ChipConfianca({ confianca }: { confianca: AprendizadoEfeito["confianca"] }) {
  return (
    <span data-confianca={confianca} className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs whitespace-nowrap ring-1", confiancaTom[confianca])}>
      {confianca === "amostra_pequena" ? confiancaLabel[confianca] : `confiança ${confiancaLabel[confianca]}`}
    </span>
  );
}

export function EfeitoLinha({ efeito: e, mostrarFator = false }: { efeito: AprendizadoEfeito; mostrarFator?: boolean }) {
  const pequena = e.confianca === "amostra_pequena";
  const naoSeparavel = e.avisos.some((a) => a.tipo === "nao_separavel" || a.tipo === "quase_so_com");
  return (
    <li className="flex flex-col gap-1 py-2.5" data-efeito={`${e.fator}:${e.rotulo}`} aria-label={`${rotuloFator(e.fator)} ${e.rotulo}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="min-w-0 text-sm break-words">
          {mostrarFator && <span className="text-muted-foreground">{rotuloFator(e.fator)}: </span>}
          <span className="font-medium">{e.rotulo}</span>
          {!pequena && !naoSeparavel && <span>: {fraseEfeito(e)}</span>}
        </p>
        <ChipConfianca confianca={e.confianca} />
      </div>
      <p className="text-xs text-muted-foreground tabular-nums">
        {formatNumero(e.nPosts)} {e.nPosts === 1 ? "post distinto" : "posts distintos"} em {formatNumero(e.nDias)} {e.nDias === 1 ? "dia" : "dias"}
        {pequena
          ? `${e.medianaBruta !== null && e.medianaBruta !== undefined ? ` · mediana bruta ${formatNumero(Math.round(e.medianaBruta))} views` : ""}${e.faltam ? ` · faltam ${formatNumero(e.faltam)} posts` : ""}`
          : !naoSeparavel && e.intervalo
            ? ` · intervalo plausível ${formatIntervalo(e)}`
            : ""}
      </p>
      {e.avisos.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Avisos">
          {e.avisos.map((a, i) => (
            <li key={i} data-aviso={a.tipo} className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-xs ring-1 ring-warning/40">
              {a.tipo === "em_alta" ? (
                <TrendingUp className="size-3" aria-hidden="true" />
              ) : a.tipo === "em_queda" ? (
                <TrendingDown className="size-3" aria-hidden="true" />
              ) : (
                <TriangleAlert className="size-3 text-warning" aria-hidden="true" />
              )}
              {textoAviso(a, e.parte)}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
