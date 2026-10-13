import { CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { AndamentoGeracao } from "@/components/geracao/AndamentoGeracao";
import { Button } from "@/components/ui/button";
import type { GeracaoStatus } from "@sociman/contract";
import { api } from "@/lib/api";
import { portaoParado, type Roteiro, type RoteiroGeracaoAberta, type RoteiroPortao } from "@/lib/roteiros";

// Roda uma ação do roteiro (que devolve o roteiro novo) e cuida do toast, do erro e do recarregamento.
export type RodarRoteiro = (acao: () => Promise<Roteiro | unknown>, ok: string) => Promise<boolean>;

export interface EtapaProps {
  roteiro: Roteiro;
  rodar: RodarRoteiro;
  // arquivado: tudo só leitura
  travado: boolean;
}

const rotuloAprovar: Record<RoteiroPortao, string> = {
  texto: "Aprovar texto",
  narracao: "Aprovar narração",
  keyframes: "Aprovar keyframes",
  clipes: "Aprovar clipes",
  final: "Aprovar o final",
};

// "Aprovar <etapa>" (spec 011): só aparece com o roteiro parado neste portão; o histórico guarda quem
// aprovou. A API recusa fora de hora (409 `portao_fora_de_hora`) e com pendência (ex.: keyframes).
export function BotaoAprovar({ roteiro, portao, rodar, travado, motivo }: EtapaProps & { portao: RoteiroPortao; motivo?: string | null }) {
  const [busy, setBusy] = useState(false);
  if (travado || portaoParado(roteiro.status) !== portao) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/60 bg-warning/5 p-3" data-testid={`aprovar-${portao}`}>
      <p className="min-w-0 flex-1 text-sm">{motivo ?? "O roteiro está parado aqui, esperando a sua revisão."}</p>
      <Button
        type="button"
        disabled={busy}
        aria-busy={busy}
        onClick={async () => {
          setBusy(true);
          await rodar(() => api.roteiros.aprovar(roteiro.id, roteiro.version, portao), "Etapa aprovada. O roteiro segue.");
          setBusy(false);
        }}
      >
        {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
        {rotuloAprovar[portao]}
      </Button>
    </div>
  );
}

const passoLabel: Record<string, string> = {
  "roteiro.plano": "Plano (frases e cenas)",
  "roteiro.narracao": "Narração",
  "roteiro.montagem": "Prévia",
  "roteiro.acabamento": "Acabamento HD",
  "cena.keyframe": "Keyframe",
  "cena.clipe": "Clipe",
};
export const rotuloPasso = (passo: string) => passoLabel[passo] ?? passo;

// O andamento das gerações abertas (021): a barra com a mensagem ("Aguardando a GPU ficar livre").
export function Andamentos({ geracoes, filtro }: { geracoes: RoteiroGeracaoAberta[]; filtro?: (g: RoteiroGeracaoAberta) => boolean }) {
  const lista = filtro ? geracoes.filter(filtro) : geracoes;
  if (lista.length === 0) return null;
  return (
    <ul className="space-y-3" aria-label="Gerações em andamento">
      {lista.map((g) => (
        <li key={g.id} className="space-y-1" data-testid={`andamento-${g.passo}`}>
          <p className="text-xs font-medium text-muted-foreground">{rotuloPasso(g.passo)}</p>
          <AndamentoGeracao geracao={{ status: g.status as GeracaoStatus, progress: g.progress, etapaMensagem: g.etapaMensagem }} />
        </li>
      ))}
    </ul>
  );
}
