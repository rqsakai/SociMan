/*
 * O chat do vídeo guiado no detalhe do roteiro (spec 031, US2, T029; FR-008..013, R5): as até 5
 * perguntas fechadas que a IA gerou de uma vez, uma por vez, com as respostas gravadas no roteiro
 * (fechar e reabrir retoma de onde parou). Respondida a conversa, "Montar o vídeo" pede o plano
 * (`planejar`), e a IA monta narração, cenas, quadros e a divisão do tempo na grade. Com o plano
 * montado, o resumo mostra cada cena com a sua duração e a soma, que fecha na duração escolhida.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Chat } from "@/components/video-guiado/Chat";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { Roteiro } from "@/lib/roteiros";
import { conversaKey, duracaoPosicao, duracaoTexto, invalidarConversa, somaPlano, useConversa } from "@/lib/videoGuiado";
import type { RodarRoteiro } from "../etapas/comum";

const PLANEJAVEL = new Set(["rascunho", "aguardando_texto"]);

export function Conversa({ roteiro: r, rodar, travado }: { roteiro: Roteiro; rodar: RodarRoteiro; travado: boolean }) {
  const queryClient = useQueryClient();
  const conv = useConversa(r.id);
  const [enviando, setEnviando] = useState(false);
  const [montando, setMontando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const c = conv.data;
  const planejado = r.posicoes.length > 0;
  const planejando = r.status === "planejando" || r.geracoesAbertas.some((g) => g.passo === "roteiro.plano");
  const podeMontar = !travado && c?.estado === "respondida" && !planejando && (PLANEJAVEL.has(r.status) || (r.status === "falhou" && r.etapaFalhou === "plano"));
  const version = Math.max(r.version, c?.version ?? 0);

  async function chamar(fn: () => Promise<unknown>) {
    setError(null);
    try {
      const novo = await fn();
      if (novo && typeof novo === "object" && "mensagens" in novo) queryClient.setQueryData(conversaKey(r.id), novo);
      await invalidarConversa(queryClient, r.id);
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  }

  return (
    <Card className="shadow-card" aria-labelledby="conversa-titulo" data-testid="conversa">
      <CardHeader>
        <h2 id="conversa-titulo" className="text-base font-semibold">
          Conversa com a IA
        </h2>
        <CardDescription>Responda às perguntas sobre o produto e o que você espera do vídeo. Dá para responder só com cliques.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {conv.isError && <ApiErrorAlert error={conv.error} />}
        {c && (
          <Chat
            mensagens={c.mensagens}
            pergunta={travado ? null : c.perguntaAtual}
            progresso={{ respondidas: c.respondidas, total: c.total }}
            pensando={c.geracaoAberta !== null || (c.estado === "sem_perguntas" && c.erro === null)}
            erro={c.erro?.message ?? null}
            enviando={enviando}
            desabilitado={travado}
            onResponder={async (opcoes, texto) => {
              const p = c.perguntaAtual;
              if (!p) return;
              setEnviando(true);
              await chamar(() => api.roteiros.responder(r.id, { perguntaId: p.id, opcoes, texto: texto || null, version }));
              setEnviando(false);
            }}
            onTentarDeNovo={async () => {
              setEnviando(true);
              await chamar(() => api.roteiros.refazerPerguntas(r.id, version));
              setEnviando(false);
            }}
          />
        )}
        {error !== null && <ApiErrorAlert error={error} onReload={() => void invalidarConversa(queryClient, r.id).then(() => setError(null))} />}

        {c?.estado === "respondida" && !planejado && !planejando && (
          <p className="text-sm text-muted-foreground" role="status">
            Tudo respondido. A IA monta a narração, as cenas, os quadros e a divisão do tempo.
          </p>
        )}
        {planejando && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status" data-testid="ia-montando">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />A IA está montando o vídeo…
          </p>
        )}
        {podeMontar && (
          <div className="flex flex-wrap gap-2">
            <Button
                type="button"
                disabled={montando}
                aria-busy={montando}
                onClick={async () => {
                  setMontando(true);
                  await rodar(() => api.roteiros.planejar(r.id, version), "A IA está montando o vídeo.");
                  setMontando(false);
                }}
              >
                {montando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
                {planejado ? "Montar de novo" : "Montar o vídeo"}
              </Button>
            <Button
              type="button"
              variant="outline"
              disabled={enviando || montando}
              onClick={async () => {
                setEnviando(true);
                if (await chamar(() => api.roteiros.refazerPerguntas(r.id, version))) toast.success("A IA vai fazer outras perguntas.");
                setEnviando(false);
              }}
            >
              <RotateCcw aria-hidden="true" />
              Outras perguntas
            </Button>
          </div>
        )}

        {planejado && <ResumoPlano r={r} />}
      </CardContent>
    </Card>
  );
}

// O plano montado: uma linha por cena (nova ou reaproveitada), a duração e a soma (FR-013, SC-001).
function ResumoPlano({ r }: { r: Roteiro }) {
  const soma = somaPlano(r);
  const alvo = r.duracaoAlvoS;
  return (
    <section className="flex flex-col gap-2 rounded-lg border p-3" aria-labelledby="plano-titulo" data-testid="plano-resumo">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="plano-titulo" className="text-sm font-medium">
          Plano montado
        </h3>
        <p className="text-sm tabular-nums" data-testid="plano-soma">
          Total: {duracaoTexto(soma)}
          {alvo != null && ` de ${duracaoTexto(alvo)}`}
        </p>
      </div>
      <ol className="flex flex-col gap-1.5">
        {r.posicoes.map((p) => (
          <li key={p.ordem} className="flex flex-wrap items-center gap-2 text-sm" data-testid={`plano-cena-${p.ordem + 1}`}>
            <span className="text-muted-foreground tabular-nums">{p.ordem + 1}.</span>
            <span className="min-w-0 flex-1 truncate">{p.cena.nome}</span>
            <Badge variant="outline">{p.reuso === "total" ? "reaproveitada" : p.reuso === "plano" ? "plano reaproveitado" : p.reaproveitada ? "reaproveitada" : "nova"}</Badge>
            <span className="tabular-nums" data-testid="plano-cena-duracao">
              {duracaoTexto(duracaoPosicao(r, p))}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
