import type { Asset, AssetFile, AssetOrigem, GeracaoStatus, KitPasso, KitSlotId, KitStatus } from "@sociman/contract";

export type {
  AssetOrigem,
  AvisoDerivados,
  ConsentimentoPessoa,
  IdentidadeKit,
  KitPadrao,
  KitPasso,
  KitSlot,
  KitSlotId,
  KitStatus,
  PreviaRevogacao,
  VozPadrao,
} from "@sociman/contract";

// Cadastro padronizado (spec 025): rótulos pt-BR dos slots, dos passos e da situação do kit, a
// configuração de cada pedido (número de opções e campos) e o polling do asset. A ordem e as regras
// (o que abre cada passo) vêm da API (`asset.kit`); aqui só a apresentação.

export const slotLabel: Record<KitSlotId, string> = {
  rosto_origem: "Rosto de origem",
  rosto_frontal: "Rosto frontal",
  rosto_34_esq: "Rosto 3/4 (esquerda)",
  rosto_34_dir: "Rosto 3/4 (direita)",
  corpo_base: "Corpo-base",
  cena: "Cena",
};

export const passoLabel: Record<string, string> = {
  "avatar.rosto_origem": "Rosto de origem",
  "avatar.rosto_frontal": "Rosto frontal",
  "avatar.rostos_34": "Rostos 3/4",
  "avatar.corpo_base": "Corpo-base",
  "avatar.identidade": "Checagem de identidade",
  "avatar.look": "Look",
  "avatar.pose": "Pose",
  "cenario.cena": "Cena",
  "cenario.variacao": "Variação",
  "voz.gravacao": "Candidatos da gravação",
  "voz.design": "Candidatos da voz sintética",
  "voz.teste": "Teste da voz",
};

// O passo que preenche cada slot (o par 3/4 sai de um passo só).
export const passoDoSlot: Record<KitSlotId, string> = {
  rosto_origem: "avatar.rosto_origem",
  rosto_frontal: "avatar.rosto_frontal",
  rosto_34_esq: "avatar.rostos_34",
  rosto_34_dir: "avatar.rostos_34",
  corpo_base: "avatar.corpo_base",
  cena: "cenario.cena",
};

// Os passos de imagem do kit do avatar, na ordem da tela, com o que o pedido leva.
export interface PassoConfig {
  passo: string;
  slots: KitSlotId[];
  n: number;
  instrucao: { label: string; hint: string; obrigatoria: boolean } | null;
}

export const PASSOS_KIT: PassoConfig[] = [
  {
    passo: "avatar.rosto_origem",
    slots: ["rosto_origem"],
    n: 4,
    instrucao: {
      label: "Descrição da pessoa (inglês)",
      hint: "Uma pessoa adulta e fictícia: idade aproximada, traços, cabelo, expressão. Ex.: brazilian woman in her early 30s, wavy shoulder-length brown hair, warm smile.",
      obrigatoria: true,
    },
  },
  {
    passo: "avatar.rosto_frontal",
    slots: ["rosto_frontal"],
    n: 2,
    instrucao: { label: "Ajuste (opcional, inglês)", hint: "Vazio: o retrato de estúdio padrão, de frente, fundo cinza.", obrigatoria: false },
  },
  { passo: "avatar.rostos_34", slots: ["rosto_34_esq", "rosto_34_dir"], n: 2, instrucao: null },
  { passo: "avatar.corpo_base", slots: ["corpo_base"], n: 2, instrucao: null },
];

export const kitStatusLabel: Record<KitStatus, string> = { incompleto: "Incompleto", completo: "Completo", atencao: "Atenção" };
export const kitStatusTone: Record<KitStatus, string> = {
  incompleto: "bg-secondary text-secondary-foreground",
  completo: "bg-success text-success-foreground",
  atencao: "bg-warning text-warning-foreground",
};
export const kitStatusTexto = (s: KitStatus | null | undefined) => (s ? kitStatusLabel[s] : "Sem kit padrão");

export const origemLabel: Record<AssetOrigem, string> = { upload: "Upload", sintetico: "Sintético", pessoa_real: "Pessoa real" };

export const NOTA_MINIMA = 7;
export const ROTULO_MAX = 60;
export const QUANDO_USAR_MAX = 300;
export const INSTRUCAO_MAX = 2000;

// ---------------------------------------------------------------------------------------------
// Leitura do asset

export const arquivoDoSlot = (asset: Asset, fileId: string | null): AssetFile | undefined =>
  fileId ? asset.files.find((f) => f.id === fileId) : undefined;

export const passoDoKit = (asset: Asset, passo: string): KitPasso | undefined => asset.kit?.passos.find((p) => p.passo === passo);

const ANDANDO: ReadonlySet<GeracaoStatus> = new Set(["na_fila", "rodando"]);
export const POLL_MS = 2000;

// O asset muda sozinho enquanto um passo do kit roda (a checagem de identidade, pedida pelo
// servidor, grava as notas e a descrição sem escolha humana).
export const assetMudando = (asset: Asset | undefined) =>
  Boolean(asset?.kit?.passos.some((p) => p.geracaoAberta && ANDANDO.has(p.geracaoAberta.status)));

// "Derivados desatualizados" da resposta do envio num slot: os itens feitos a partir da imagem antiga.
export function derivadosTexto(itens: Record<string, unknown>[]): string {
  return itens
    .map((i) => {
      const slot = typeof i.slot === "string" ? (slotLabel[i.slot as KitSlotId] ?? i.slot) : null;
      const look = typeof i.look === "string" ? `look ${i.look}` : null;
      const label = typeof i.label === "string" ? `pose ${i.label}` : null;
      return slot ?? look ?? label ?? "arquivo";
    })
    .join(", ");
}
