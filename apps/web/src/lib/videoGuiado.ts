import type {
  CenaResumo,
  ProdutoResumo,
  Roteiro,
  RoteiroAlvoRecusa,
  RoteiroConversa,
  RoteiroMensagem,
  RoteiroPergunta,
  RoteiroPosicaoReuso,
  RoteiroQuadroPapel,
  RoteiroTipoVideo,
} from "@sociman/contract";
import { useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { buscarTodas, ordenarPorPerfil } from "./estudio";
import { roteiroKey } from "./roteiros";

export type { RoteiroConversa, RoteiroGrade, RoteiroMensagem, RoteiroPergunta, RoteiroTipoVideo } from "@sociman/contract";

// Vídeo guiado (spec 031, US1/US2): os 6 blocos do "Novo vídeo" e o chat de perguntas fechadas.
// A grade de duração vem da API (`roteiros_grade`); as perguntas, as respostas e o estado do chat
// ficam no roteiro (`roteiros_conversa`), e a tela só lê e responde.

// Os tipos de vídeo do bloco 1 (FR-002): só "Avatar & POV" existe; os outros aparecem "em breve".
export const TIPOS_VIDEO: { id: RoteiroTipoVideo | string; titulo: string; subtitulo: string; emBreve?: boolean }[] = [
  { id: "avatar_pov", titulo: "Avatar & POV", subtitulo: "Um avatar mostra o produto, com voice over" },
  { id: "so_produto", titulo: "Só produto", subtitulo: "Close do produto, sem avatar", emBreve: true },
  { id: "antes_depois", titulo: "Antes e depois", subtitulo: "Comparação em duas partes", emBreve: true },
];

export const BLOCOS = ["Tipo de vídeo", "Perfil", "Avatar e voz", "Cenário", "Produto", "Duração"] as const;
export const LIM_RESPOSTA = 500;
export const AVISO_DADOS_PESSOAIS = "Não escreva dados pessoais (nome completo, telefone, endereço, documento).";

// Exemplos de pedidos prontos (FR-010), somados aos que a IA manda em cada pergunta.
export const EXEMPLOS_PADRAO = ["mostrar o caimento", "foco no preço", "estilo antes/depois", "chamada para o link"];

export const duracaoTexto = (s: number) => (s < 60 ? `${s} s` : `${Math.floor(s / 60)} min${s % 60 ? ` ${s % 60} s` : ""}`);

export const gradeKey = ["roteiros", "grade"] as const;
export const conversaKey = (id: string) => ["roteiro-conversa", id] as const;

export function useGrade() {
  return useQuery({ queryKey: gradeKey, queryFn: () => api.roteiros.grade(), staleTime: 5 * 60_000 });
}

// Os produtos não arquivados da agência numa leitura só: os aprovados entram no bloco, os outros
// só no contador "N fora (não aprovados)" (FR-004).
export function useProdutosBloco(perfilBase: string | null | undefined) {
  const q = useQuery({
    queryKey: ["produtos", "agencia", "opcoes", "ativos"],
    queryFn: () =>
      buscarTodas(
        (cursor) => api.produtos.listarAgencia({ arquivados: "false", limit: 100, cursor }),
        (p) => p.itens,
        (p) => p.proximoCursor,
      ),
    staleTime: 30_000,
  });
  const todos: ProdutoResumo[] | undefined = q.data?.itens;
  const aprovados = todos ? ordenarPorPerfil(todos.filter((p) => p.status === "aprovado"), perfilBase, (p) => p.nomeComercial ?? p.name) : undefined;
  return { ...q, aprovados, fora: todos ? todos.length - (aprovados?.length ?? 0) : 0, truncado: q.data?.truncado ?? false };
}

// O chat anda sozinho enquanto a IA pensa (as perguntas ainda não chegaram ou uma geração está
// aberta), com polling de 2 s; com erro, para e espera o "tentar de novo".
export function conversaMudando(c: RoteiroConversa): boolean {
  return c.geracaoAberta !== null || (c.estado === "sem_perguntas" && c.erro === null);
}

export function useConversa(roteiroId: string, ligado = true) {
  return useQuery({
    queryKey: conversaKey(roteiroId),
    queryFn: () => api.roteiros.conversa(roteiroId),
    enabled: roteiroId !== "" && ligado,
    refetchInterval: (q) => (q.state.data && conversaMudando(q.state.data) ? 2000 : false),
  });
}

export async function invalidarConversa(qc: QueryClient, roteiroId: string) {
  await Promise.all([qc.invalidateQueries({ queryKey: conversaKey(roteiroId) }), qc.invalidateQueries({ queryKey: roteiroKey(roteiroId) })]);
}

// Os rótulos das opções escolhidas numa resposta (a pergunta da mesma rodada).
export function rotulosDaResposta(resposta: RoteiroMensagem, mensagens: RoteiroMensagem[]): string[] {
  const rodada = Number(resposta.conteudo.rodada ?? 0);
  const pergunta = mensagens.find((m) => m.tipo === "pergunta" && m.perguntaId === resposta.perguntaId && Number(m.conteudo.rodada ?? 0) === rodada);
  const opcoes = (pergunta?.conteudo.opcoes as RoteiroPergunta["opcoes"] | undefined) ?? [];
  const escolhidas = (resposta.conteudo.opcoes as string[] | undefined) ?? [];
  return escolhidas.map((id) => opcoes.find((o) => o.id === id)?.rotulo ?? id);
}

// A duração de cada posição do plano: os trechos × o trecho-base (guiado) ou a duração medida.
export const duracaoPosicao = (r: Roteiro, p: Roteiro["posicoes"][number]) =>
  p.trechos != null && r.trechoBaseS != null ? p.trechos * r.trechoBaseS : (p.duracaoS ?? 0);

export const somaPlano = (r: Roteiro) => r.posicoes.reduce((s, p) => s + duracaoPosicao(r, p), 0);

// ---------------------------------------------------------------------------------------------
// Wizard (spec 031, US3/US5/US6; FR-014..016, R6, R9): aprovar ou "Não aprovo" cada item. A tela
// nunca mostra texto de prompt nem de fala (FR-015): só o áudio, as imagens e os vídeos.

export type { RoteiroAlvoRecusa, RoteiroQuadro, RoteiroQuadroPapel, RoteiroTomadaTrecho } from "@sociman/contract";

export type TipoAlvo = RoteiroAlvoRecusa["tipo"];

export const papelLabel: Record<RoteiroQuadroPapel, string> = { inicio: "Início", meio1: "Meio 1", meio2: "Meio 2", fim: "Fim" };

// As opções prontas de troca por tipo de item (FR-016); a IA recebe os rótulos.
export const OPCOES_TROCA: Record<TipoAlvo, string[]> = {
  narracao: ["mais animada", "mais calma", "mais devagar", "mais rápida", "texto mais curto"],
  quadros: ["mais de lado", "mostrar a manga", "manter o rosto", "mais perto do produto"],
  trecho: ["movimento mais suave", "sem mexer a boca", "não mudar o fundo", "mais devagar"],
  final: ["ritmo mais rápido", "ritmo mais calmo", "outra ordem das cenas"],
  posicao: ["outra cena", "cena mais curta", "cena mais longa"],
};
export const OPCAO_TEXTO_CURTO = "texto mais curto";
export const LIM_OPCOES_TROCA = 6;

// O alvo sem os campos vazios (é como a API grava no chat), para comparar.
export function alvoChave(a: Partial<RoteiroAlvoRecusa> | Record<string, unknown> | null | undefined): string {
  if (!a) return "";
  const x = a as Record<string, unknown>;
  return ["tipo", "ordem", "quadro", "trecho"].map((k) => (x[k] == null ? "" : String(x[k]))).join("|");
}

// As mensagens do chat de um alvo ("Não aprovo"): os pedidos, os esclarecimentos e os avisos.
export function mensagensDoAlvo(mensagens: RoteiroMensagem[], alvo: RoteiroAlvoRecusa): RoteiroMensagem[] {
  const chave = alvoChave(alvo);
  return mensagens.filter(
    (m) => (m.tipo === "pedido_troca" || m.tipo === "esclarecimento" || m.tipo === "aviso") && alvoChave((m.alvo ?? m.conteudo.alvo) as Record<string, unknown> | null) === chave,
  );
}

// O esclarecimento ainda sem resposta (o último da cadeia do alvo, sem pedido depois dele).
export function esclarecimentoPendente(doAlvo: RoteiroMensagem[]): RoteiroMensagem | null {
  const ultimo = [...doAlvo].reverse().find((m) => m.tipo === "pedido_troca" || m.tipo === "esclarecimento");
  return ultimo?.tipo === "esclarecimento" ? ultimo : null;
}

// Um "Não aprovo" ainda com a IA (um `roteiro.ajuste` aberto): a API aceita um por vez.
export const ajusteAberto = (r: Roteiro): boolean => r.geracoesAbertas.some((g) => g.passo === "roteiro.ajuste");

// A próxima duração da grade, maior que a atual (o "duração maior" do aviso `fala_nao_cabe`).
export function proximaDuracao(opcoes: number[] | undefined, atual: number | null | undefined): number | null {
  if (!opcoes || atual == null) return null;
  return [...opcoes].sort((a, b) => a - b).find((o) => o > atual) ?? null;
}

// ---------------------------------------------------------------------------------------------
// Modal de cenas (spec 031, US4, T042; FR-019..024, R7): por posição, a cena proposta e o nível.

export type { RoteiroPosicaoReuso } from "@sociman/contract";

export const reusoLabel: Record<RoteiroPosicaoReuso, string> = { total: "Sem custo", plano: "Refaz as imagens", nova: "Criar nova" };
export const reusoDescricao: Record<RoteiroPosicaoReuso, string> = {
  total: "Usa os quadros e os clipes aprovados da cena, sem gerar nada.",
  plano: "Usa a ação, a câmera e o movimento da cena; os quadros e os clipes saem de novo.",
  nova: "A IA cria uma cena nova, que vai para a biblioteca.",
};
export const reusoTone: Record<RoteiroPosicaoReuso, string> = {
  total: "bg-success text-success-foreground",
  plano: "bg-info text-info-foreground",
  nova: "bg-secondary text-secondary-foreground",
};

// O que a tela consegue adiantar de uma cena da biblioteca para o vídeo (a API confere de novo e
// responde 422 `reuso_invalido`): outro produto só entra pelo plano, com aviso (FR-024); com o
// mesmo avatar, cenário e produto e a cena pronta, o reuso total pode valer.
export interface NivelPossivel {
  outroProduto: boolean;
  podeTotal: boolean;
  diferencas: string[];
}

export function nivelPossivel(r: Roteiro, c: CenaResumo): NivelPossivel {
  const produtoId = r.produtos[0]?.produtoId ?? null;
  const outroProduto = c.produtoId != null && c.produtoId !== produtoId;
  const diferencas: string[] = [];
  if ((c.avatar?.id ?? null) !== (r.avatar?.id ?? null)) diferencas.push("outro avatar");
  if ((c.cenario?.id ?? null) !== (r.cenarioId ?? null)) diferencas.push("outro cenário");
  if (outroProduto) diferencas.push("outro produto");
  else if (c.produtoId == null) diferencas.push("sem o produto");
  if (c.status !== "pronta" && c.status !== "usada") diferencas.push("ainda em rascunho");
  return { outroProduto, podeTotal: diferencas.length === 0, diferencas };
}

// O modo da tela do roteiro (FR-014, R9): conveniência de quem vê, no navegador.
export type ModoTela = "wizard" | "avancado";
const modoChave = (id: string) => `sociman:roteiro:modo:${id}`;

export function lerModo(id: string): ModoTela | null {
  try {
    const v = window.localStorage.getItem(modoChave(id));
    return v === "wizard" || v === "avancado" ? v : null;
  } catch {
    return null;
  }
}

export function gravarModo(id: string, modo: ModoTela): void {
  try {
    window.localStorage.setItem(modoChave(id), modo);
  } catch {
    // sem armazenamento (janela privada): o modo vale só nesta visita
  }
}

// FR-035: no wizard, todos os portões ligados e o modo revisar.
export const PORTOES_TODOS = { texto: true, narracao: true, keyframes: true, clipes: true, final: true } as const;
export const portoesTodosLigados = (r: Pick<Roteiro, "modo" | "portoes">): boolean =>
  r.modo === "revisar" && Object.values(r.portoes).every(Boolean);
