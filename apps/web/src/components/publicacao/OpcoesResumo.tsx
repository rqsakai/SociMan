import type { OpcoesTikTok } from "@sociman/contract";
import { comercialLabel, privacidadeLabel } from "@/lib/publicacao";
import { formatDateTime } from "@/lib/tz";

// O que o dono confirmou na tela obrigatória da TikTok (spec 015, US3): é o que a trilha publica.
export function OpcoesResumo({ opcoes }: { opcoes: OpcoesTikTok }) {
  const sim = (v: boolean) => (v ? "sim" : "não");
  return (
    <dl aria-label="Opções confirmadas para a publicação" className="grid gap-x-3 gap-y-0.5 text-xs sm:grid-cols-[auto_1fr]">
      <dt className="text-muted-foreground">Quem pode ver</dt>
      <dd>{privacidadeLabel[opcoes.privacidade]}</dd>
      <dt className="text-muted-foreground">Comentários · dueto · costura</dt>
      <dd>
        {sim(opcoes.permitirComentario)} · {sim(opcoes.permitirDueto)} · {sim(opcoes.permitirCostura)}
      </dd>
      <dt className="text-muted-foreground">Conteúdo comercial</dt>
      <dd>{comercialLabel[opcoes.comercial ?? "nenhum"]}</dd>
      <dt className="text-muted-foreground">Gerado por IA</dt>
      <dd>{sim(opcoes.conteudoIa ?? false)}</dd>
      <dt className="text-muted-foreground">Consentimento</dt>
      <dd>
        {opcoes.consentimento.texto} (em {formatDateTime(opcoes.consentimento.aceitoEm)})
      </dd>
    </dl>
  );
}
