// Importação da agência (spec 013): a API lê a pasta `shared/` e os clipes da agência (montagens só
// leitura), mostra a prévia (novo/igual/diverge/fora, nada gravado, uso único, 30 min) e grava o que
// o dono escolheu numa tarefa de fundo. Ler, confirmar e desfazer são só do dono humano (a API
// recusa o resto com 403); a lista, o detalhe e o estado são de todos.

import { ApiError, type AgenciaConfirmarRequest, type AgenciaEstado, type AgenciaImportacao, type AgenciaImportacaoResumo, type AgenciaPrevia } from "@sociman/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type Previa = AgenciaPrevia;
export type ItemPrevia = Previa["itens"][number];
export type Situacao = ItemPrevia["situacao"];
export type TipoItem = ItemPrevia["tipo"];
export type Direito = NonNullable<ItemPrevia["direitosAceitos"]>[number];
export type Estado = AgenciaEstado;
export type Importacao = AgenciaImportacao;
export type ImportacaoResumo = AgenciaImportacaoResumo;
export type ItemImportacao = Importacao["itens"][number];
export type EstadoImportacao = ImportacaoResumo["estado"];
export type Resultado = ItemImportacao["resultado"];
export type Progresso = ImportacaoResumo["progresso"];
export type EscolhaEnviada = NonNullable<AgenciaConfirmarRequest["escolhas"]>[number];
// Escolha do dono num item (o perfil da persona vai à parte, no topo do confirmar).
export type Escolha = Omit<EscolhaEnviada, "n">;

// ---------------------------------------------------------------------------------------------
// Rótulos

export const situacaoLabel: Record<Situacao, string> = {
  novo: "novo",
  igual: "igual",
  diverge: "diverge",
  fora: "fora",
  aguardando_cota: "aguardando cota",
  sugestao: "sugestão",
};

export const situacaoTone: Record<Situacao, string> = {
  novo: "bg-success text-success-foreground",
  igual: "bg-secondary text-secondary-foreground",
  diverge: "bg-warning text-warning-foreground",
  fora: "bg-muted text-muted-foreground",
  aguardando_cota: "bg-info text-info-foreground",
  sugestao: "bg-info text-info-foreground",
};

export const tipoLabel: Record<TipoItem, string> = {
  perfil: "Perfil",
  conta: "Conta",
  guia: "Guia de comunicação",
  anotacao: "Anotação",
  canal: "Canal-fonte",
  vinculo_canal: "Vínculo de canal",
  imagem_logo: "Logo",
  asset: "Asset",
  arquivo_asset: "Imagem de asset",
  clipe: "Clipe",
  sugestao_bordao: "Sugestão de bordão",
  arquivo: "Arquivo",
};

export const direitoLabel: Record<Direito, string> = {
  proprio: "Próprio",
  parceiro: "Parceiro",
  programa_de_cortes: "Programa de cortes",
  sem_acordo: "Sem acordo",
};

export const DIREITOS: Direito[] = ["proprio", "parceiro", "programa_de_cortes", "sem_acordo"];

export const estadoLabel: Record<EstadoImportacao, string> = {
  processando: "processando",
  concluida: "concluída",
  falhou: "falhou",
  desfeita: "desfeita",
};

export const resultadoLabel: Record<Resultado, string> = {
  criado: "criado",
  atualizado: "atualizado",
  mantido: "mantido",
  igual: "igual",
  fora: "fora",
  nao_gravado: "não gravado",
  sugestao: "sugestão",
};

export const etapaLabel: Record<NonNullable<Progresso["etapa"]>, string> = {
  conferindo: "Conferindo os arquivos e o espaço no HD",
  gravando: "Gravando",
  fim: "Fim",
};

// Motivos conhecidos (a API manda o texto pronto quando tem; o código fica de reserva).
const motivoLabel: Record<string, string> = {
  valor: "valor diferente",
  direito: "direito diferente",
  editado: "editado no SociMan",
  arquivado: "arquivado no SociMan",
  sem_canal_youtube: "sem canal do YouTube identificável",
  conteudo_proprio: "conteúdo próprio (use o envio avulso)",
  molde: "molde da agência",
  nao_usar_ainda: "marcado como “não usar ainda”",
  arquivo_operacional: "arquivo operacional da agência",
  fora_do_mapeamento: "fora do mapeamento",
  link_para_fora: "link para fora da pasta",
  escolha_o_perfil: "escolha o perfil",
  mudou_desde_a_leitura: "o arquivo mudou desde a leitura",
  editado_desde_a_leitura: "editado no SociMan desde a leitura",
  em_uso: "em uso",
  editado_depois: "editado depois",
  dono_inativo: "o dono foi desativado",
  interrompida: "interrompida",
};

export const textoMotivo = (codigo?: string | null, texto?: string | null) =>
  texto || (codigo ? (motivoLabel[codigo] ?? codigo.replaceAll("_", " ")) : "");

// "shared:perfis/x/fontes.md" → "perfis/x/fontes.md" (a raiz vai no título).
export const arquivoCurto = (arquivo: string) => arquivo.replace(/^(shared|clipes):/, "");
export const raizDoArquivo = (arquivo: string) => (arquivo.startsWith("clipes:") ? "clipes" : "shared");

export function formatMB(bytes: number | null | undefined): string {
  const b = bytes ?? 0;
  if (b > 0 && b < 1024 * 1024) return `${Math.max(1, Math.round(b / 1024)).toLocaleString("pt-BR")} KB`;
  const mb = b / (1024 * 1024);
  return `${mb.toLocaleString("pt-BR", { maximumFractionDigits: mb < 10 ? 1 : 0 })} MB`;
}

// Texto curto de um valor comparado (atual × proposto).
export function valorTexto(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.map(valorTexto).join(" · ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

const campoLabel: Record<string, string> = {
  name: "Nome",
  nome: "Nome",
  nicho: "Nicho",
  idioma: "Idioma",
  status: "Status",
  direito: "Direito",
  statusMarkdown: "Status no markdown",
  titulo: "Título",
  texto: "Texto",
  tom: "Tom",
  vocabulario: "Vocabulário",
  naoFaca: "Não faça",
  descricaoPrompt: "Descrição para prompts",
  tomDeVoz: "Tom de voz",
  regrasImagem: "Regras de imagem",
  plataforma: "Plataforma",
  handle: "@",
  bordao: "Bordão",
  canal: "Canal",
  perfil: "Perfil",
  perfis: "Perfis",
  papel: "Papel",
  rotulo: "Rótulo",
  look: "Look",
  uso: "Uso",
  prompt: "Prompt",
  erro: "Erro",
  faltou: "Faltou",
  arquivo: "Arquivo",
};
export const rotuloCampo = (campo: string) => campoLabel[campo] ?? campo;

// Escolha efetiva de um item: a do dono por cima do padrão da prévia.
export function escolhaEfetiva(item: ItemPrevia, escolhas: Record<number, Escolha>): Escolha {
  return { ...(item.escolhaPadrao ?? {}), ...(escolhas[item.n] ?? {}) };
}

// Só as escolhas que mudam o padrão vão no corpo do confirmar.
export function escolhasParaEnviar(itens: ItemPrevia[], escolhas: Record<number, Escolha>): EscolhaEnviada[] {
  const out: EscolhaEnviada[] = [];
  for (const item of itens) {
    const minha = escolhas[item.n];
    if (!minha) continue;
    const padrao = item.escolhaPadrao ?? {};
    const mudou = (Object.keys(minha) as (keyof Escolha)[]).some((k) => minha[k] !== undefined && minha[k] !== (padrao as Escolha)[k]);
    if (mudou) out.push({ n: item.n, ...padrao, ...minha });
  }
  return out;
}

// Itens da persona marcados sem perfil escolhido: a confirmação daria 422.
export function personaSemPerfil(previa: Previa, escolhas: Record<number, Escolha>, personaPerfil: string): boolean {
  if (!previa.persona?.exigePerfil || personaPerfil) return false;
  return previa.itens.some((i) => i.exigePerfil && i.situacao === "novo" && escolhaEfetiva(i, escolhas).marcado !== false);
}

// Resumo do que a confirmação vai fazer (AlertDialog).
export function resumoConfirmacao(itens: ItemPrevia[], escolhas: Record<number, Escolha>) {
  let criar = 0;
  let trocar = 0;
  let bytes = 0;
  for (const item of itens) {
    const e = escolhaEfetiva(item, escolhas);
    if (item.situacao === "novo" && e.marcado !== false) {
      criar += 1;
      bytes += item.bytes ?? 0;
    } else if (item.situacao === "diverge" && e.usar === "markdown") {
      trocar += 1;
    }
  }
  return { criar, trocar, bytes };
}

export const importacaoPath = (id: string) => `/app/configuracoes/importacao/${id}`;

// Onde abrir a entidade gravada (quando há tela).
export function entidadePath(e: { tipo: string; id: string }): string | null {
  switch (e.tipo) {
    case "perfil":
      return `/app/perfis/${e.id}`;
    case "conta":
      return `/app/contas/${e.id}/historico`;
    case "canal":
      return `/app/fontes/${e.id}`;
    case "asset":
      return `/app/assets/${e.id}`;
    case "conteudo":
      return `/app/conteudos/${e.id}`;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------------------------
// Queries e mutações. Sem retry em 404 (API sem a 013): nada fica em loop no console.

const agencia = api.agencia;

const semRetry404 = (falhas: number, err: unknown) => !(err instanceof ApiError && err.status === 404) && falhas < 1;

export const agenciaEstadoKey = ["agencia-estado"] as const;
export const agenciaImportacoesKey = ["agencia-importacoes"] as const;
export const agenciaImportacaoKey = (id: string) => ["agencia-importacao", id] as const;

export function useEstadoAgencia() {
  return useQuery({ queryKey: agenciaEstadoKey, queryFn: () => agencia.estado(), retry: semRetry404 });
}

export function useImportacoesAgencia() {
  return useQuery({ queryKey: agenciaImportacoesKey, queryFn: () => agencia.importacoes(), retry: semRetry404 });
}

// Enquanto `processando`, consulta a cada 2 s (andamento); depois, para.
export function useImportacaoAgencia(id: string | null | undefined) {
  return useQuery({
    queryKey: agenciaImportacaoKey(id ?? ""),
    queryFn: () => agencia.importacao(id!),
    enabled: Boolean(id),
    retry: semRetry404,
    refetchInterval: (q) => (q.state.data?.estado === "processando" ? 2000 : false),
  });
}

export function useAgenciaMutations() {
  const qc = useQueryClient();
  const depois = () =>
    Promise.all([qc.invalidateQueries({ queryKey: agenciaEstadoKey }), qc.invalidateQueries({ queryKey: agenciaImportacoesKey })]);
  return {
    previa: useMutation({ mutationFn: () => agencia.previa() }),
    confirmar: useMutation({
      mutationFn: (body: AgenciaConfirmarRequest) => agencia.confirmar(body),
      onSuccess: (imp) => {
        qc.setQueryData(agenciaImportacaoKey(imp.id), imp);
        return depois();
      },
    }),
    desfazer: useMutation({
      mutationFn: (imp: { id: string; version: number }) => agencia.desfazer(imp.id, imp.version),
      onSuccess: (imp) => {
        qc.setQueryData(agenciaImportacaoKey(imp.id), imp);
        return depois();
      },
    }),
  };
}

// Quando a importação de fundo termina, o estado e a lista mudam (a página chama num efeito).
export function useInvalidarAgencia() {
  const qc = useQueryClient();
  return () =>
    Promise.all([qc.invalidateQueries({ queryKey: agenciaEstadoKey }), qc.invalidateQueries({ queryKey: agenciaImportacoesKey })]);
}
