// Histórico do TikTok Studio (spec 020): os ZIPs (ou CSVs) que o dono baixa no Studio viram dias
// importados da série da 016. Prévia (nada gravado, uso único, 30 min), confirmar, desfazer e a
// cobertura. Escrever é só do dono humano (a API recusa o resto com 403); ler é de todos.

import type { StudioCobertura, StudioImportacao, StudioPrevia } from "@sociman/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type Previa = StudioPrevia;
export type PreviaSecao = Previa["secoes"][number];
export type ImportacaoStudio = StudioImportacao;
export type CoberturaStudio = StudioCobertura;
export type SecaoStudio = PreviaSecao["secao"];
export type AnoOrigem = Previa["periodo"]["anoOrigem"];
export type SituacaoDia = PreviaSecao["amostra"][number]["situacao"];
export interface Faixa {
  de: string;
  ate: string;
}

// ---------------------------------------------------------------------------------------------
// Queries e mutações. Confirmar e desfazer mudam a lista, a cobertura e o analytics (os dias do
// Studio entram nos totais diários da 019).

export const studioImportacoesKey = (contaId: string) => ["studio-importacoes", contaId] as const;
export const studioCoberturaKey = (contaId: string) => ["studio-cobertura", contaId] as const;

export function useImportacoesStudio(contaId: string) {
  return useQuery({ queryKey: studioImportacoesKey(contaId), queryFn: () => api.studio.importacoes(contaId) });
}

export function useCoberturaStudio(contaId: string | undefined) {
  return useQuery({ queryKey: studioCoberturaKey(contaId ?? ""), queryFn: () => api.studio.cobertura(contaId!), enabled: Boolean(contaId) });
}

export function useStudioMutations(contaId: string) {
  const qc = useQueryClient();
  const depois = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: studioImportacoesKey(contaId) }),
      qc.invalidateQueries({ queryKey: studioCoberturaKey(contaId) }),
      qc.invalidateQueries({ queryKey: ["analytics"] }),
    ]);
  return {
    previa: useMutation({ mutationFn: (arquivos: File[]) => api.studio.previa(contaId, arquivos) }),
    confirmar: useMutation({
      mutationFn: (body: { previaId: string; confirmoConta: boolean }) => api.studio.confirmar(contaId, body),
      onSuccess: depois,
    }),
    desfazer: useMutation({
      mutationFn: (imp: { id: string; version: number }) => api.studio.desfazer(imp.id, imp.version),
      onSuccess: depois,
    }),
  };
}

// ---------------------------------------------------------------------------------------------
// Rótulos

export const secaoLabel: Record<SecaoStudio, string> = { visao_geral: "Visão geral", seguidores: "Seguidores" };

export const anoOrigemLabel: Record<AnoOrigem, string> = {
  nome_zip: "ano pelo nome do ZIP",
  deduzido: "ano deduzido",
  misto: "ano pelo nome do ZIP e deduzido",
};

export const situacaoLabel: Record<SituacaoDia, string> = {
  novo: "novo",
  igual: "igual ao já importado",
  divergente: "diferente do já importado (vale o anterior)",
  coletado: "coletado (vale a API)",
  ignorado: "hoje (ignorado)",
};

// Os totais da prévia, na ordem da tela.
export const totaisLabel: Record<SecaoStudio, [string, string][]> = {
  visao_geral: [
    ["views", "Views"],
    ["visitasPerfil", "Visitas ao perfil"],
    ["likes", "Curtidas"],
    ["comments", "Comentários"],
    ["shares", "Compartilhamentos"],
  ],
  seguidores: [
    ["seguidoresInicio", "Seguidores no início"],
    ["seguidoresFim", "Seguidores no fim"],
    ["ganhos", "Ganhos"],
  ],
};

export const colunasAmostra: Record<SecaoStudio, [string, string][]> = {
  visao_geral: [
    ["views", "Views"],
    ["visitasPerfil", "Visitas"],
    ["likes", "Curtidas"],
    ["comments", "Coment."],
    ["shares", "Compart."],
  ],
  seguidores: [
    ["seguidores", "Seguidores"],
    ["seguidoresDif", "Diferença"],
  ],
};

export const dataBr = (dia: string) => dia.split("-").reverse().join("/");
export const periodoBr = (f: Faixa) => (f.de === f.ate ? dataBr(f.de) : `${dataBr(f.de)} a ${dataBr(f.ate)}`);

// Onde fica a tela da conta.
export const studioContaPath = (contaId: string) => `/app/contas/${contaId}/studio`;
