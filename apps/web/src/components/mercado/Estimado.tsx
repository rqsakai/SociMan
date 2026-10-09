/*
 * Um número derivado do mercado (spec 026, FR-042): o valor formatado com o selo "estimado" e, no
 * título (tooltip nativo, texto puro), os motivos por extenso. Sem valor, mostra o motivo
 * principal ("coletando", "sem dado de afiliado"…) em vez de um número.
 */
import type { MercadoNumero } from "@sociman/contract";
import { motivoLabel } from "@/lib/mercado";
import { cn } from "@/lib/utils";

export interface EstimadoProps {
  numero: MercadoNumero | null | undefined;
  formatar: (v: number | null | undefined) => string;
  className?: string;
  /** rótulo curto quando não há valor (padrão: o 1º motivo) */
  vazio?: string;
}

export function motivosTexto(n: MercadoNumero): string {
  const partes = (n.motivos ?? []).map((m) => motivoLabel[m] ?? m);
  if (n.amostraPequena) partes.push("amostra pequena: menos de 7 dias de fotos");
  if (n.nFotos) partes.push(`${n.nFotos} foto${n.nFotos === 1 ? "" : "s"}`);
  return partes.join("; ");
}

const vazioLabel: Record<string, string> = {
  coletando: "coletando",
  sem_dado_afiliado: "sem dado de afiliado",
  base_pequena: "base pequena",
  sem_vendas: "sem vendas",
};

export function Estimado({ numero, formatar, className, vazio }: EstimadoProps) {
  if (!numero || numero.valor === null || numero.valor === undefined) {
    const motivo = numero?.motivos?.[0] ?? "coletando";
    return (
      <span className={cn("text-sm text-muted-foreground", className)} title={numero ? motivosTexto(numero) : undefined} data-estimado="vazio">
        {vazio ?? vazioLabel[motivo] ?? motivo}
      </span>
    );
  }
  const faixa = numero.min !== null && numero.min !== undefined && numero.max !== null && numero.max !== undefined && numero.min !== numero.max;
  return (
    <span className={cn("tabular-nums", className)} title={motivosTexto(numero)} data-estimado={numero.estimado ? "sim" : "nao"}>
      {formatar(numero.valor)}
      {numero.estimado && (
        <abbr className="ml-0.5 text-muted-foreground no-underline" title="estimado">
          *
        </abbr>
      )}
      {faixa && (
        <span className="ml-1 text-xs text-muted-foreground">
          ({formatar(numero.min)}–{formatar(numero.max)})
        </span>
      )}
      {numero.amostraPequena && <span className="sr-only"> (amostra pequena)</span>}
    </span>
  );
}
