/*
 * Cor fixa por conta no analytics (spec 019, FR-006/FR-013; R11).
 *
 * A cor segue a conta, nunca a posição: todas as contas da casa (de todos os perfis, inclusive as
 * arquivadas) entram numa ordem estável (criação, depois id) e a n-ésima recebe `--chart-n`. Um
 * filtro que tira contas da tela não repinta as que ficam; uma conta nova pega o próximo slot.
 * Da 9ª conta em diante, e nas contas anônimas (sem id), a série vira "Outros", em cinza.
 *
 * A ordem vem de UMA rota (`/api/analytics/ordem-contas`), com chave própria e cache longo: um GET
 * por perfil estourava o limite de requisições do edge. Quando só há o rótulo ("@handle"),
 * `slotDoRotulo` resolve por ele.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "@/lib/api";
import type { TemaGraficos } from "./tema";

export const MAX_CORES = 8;
export const ROTULO_OUTROS = "Outros";

export interface OrdemContas {
  /** false enquanto as contas carregam (sem a ordem, a cor ainda não é a definitiva) */
  pronto: boolean;
  /** 0..7 (o slot `--chart-(n+1)`) ou null: "Outros" */
  slot: (contaId: string | null | undefined) => number | null;
  slotDoRotulo: (rotulo: string | null | undefined) => number | null;
}

export function useOrdemContas(): OrdemContas {
  const ordem = useQuery({ queryKey: ["analytics", "ordem-contas"], queryFn: () => api.analytics.ordemContas(), staleTime: 10 * 60_000 });
  const contas = ordem.data?.contas;
  // com erro, segue com o que tiver (tudo "Outros") em vez de travar os cards no esqueleto
  const pronto = ordem.isSuccess || ordem.isError;

  return useMemo(() => {
    const porId = new Map<string, number>();
    const porRotulo = new Map<string, number>();
    (contas ?? []).slice(0, MAX_CORES).forEach((c, i) => {
      porId.set(c.contaId, i);
      if (!porRotulo.has(c.rotulo)) porRotulo.set(c.rotulo, i);
    });
    return {
      pronto,
      slot: (id) => (id ? (porId.get(id) ?? null) : null),
      slotDoRotulo: (r) => (r ? (porRotulo.get(r) ?? null) : null),
    };
  }, [contas, pronto]);
}

/** Cor da série: o slot da conta, ou o cinza de "Outros". */
export function corDoSlot(tema: TemaGraficos, slot: number | null): string {
  return slot === null ? tema.textoFraco : tema.categorica[slot]!;
}
