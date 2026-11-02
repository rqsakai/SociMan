import { Bot, Check, Loader2, RotateCcw, Send, TriangleAlert, User } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { AVISO_DADOS_PESSOAIS, EXEMPLOS_PADRAO, LIM_RESPOSTA, rotulosDaResposta, type RoteiroMensagem, type RoteiroPergunta } from "../../lib/videoGuiado";

export interface ChatProps {
  mensagens: RoteiroMensagem[];
  pergunta: RoteiroPergunta | null;
  // "1 de 3" acima da pergunta.
  progresso?: { respondidas: number; total: number };
  pensando: boolean;
  erro: string | null;
  enviando: boolean;
  desabilitado?: boolean;
  onResponder: (opcoes: string[], texto: string) => void;
  onTentarDeNovo: () => void;
}

// O chat do vídeo guiado (spec 031, US2, T029; FR-008..012): o histórico (perguntas da IA, as
// respostas do operador e os avisos), a pergunta atual com as opções clicáveis (única ou
// múltipla, `aria-pressed`), os exemplos de pedidos prontos (preenchem a resposta curta), a
// resposta curta opcional (≤ 500, com o aviso de dados pessoais), "A IA está pensando…" e o
// "Tentar de novo" quando a IA não respondeu. Responder só com cliques sempre é possível.
export function Chat({ mensagens, pergunta, progresso, pensando, erro, enviando, desabilitado = false, onResponder, onTentarDeNovo }: ChatProps) {
  const [opcoes, setOpcoes] = useState<string[]>([]);
  const [texto, setTexto] = useState("");
  const textoId = useId();
  const avisoId = useId();
  const perguntaId = pergunta ? `${pergunta.rodada}:${pergunta.id}` : null;

  // Uma pergunta nova começa limpa.
  useEffect(() => {
    setOpcoes([]);
    setTexto("");
  }, [perguntaId]);

  function alternar(id: string) {
    if (!pergunta) return;
    if (pergunta.multipla) setOpcoes((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]));
    else setOpcoes((o) => (o[0] === id ? [] : [id]));
  }

  const exemplos = pergunta ? [...new Set([...pergunta.exemplos, ...EXEMPLOS_PADRAO])].slice(0, 6) : [];
  const podeResponder = !desabilitado && !enviando && (opcoes.length > 0 || texto.trim() !== "");

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="chat">
      <ol role="log" aria-label="Conversa com a IA" aria-live="polite" className="flex flex-col gap-2" data-testid="chat-mensagens">
        {mensagens.filter((m) => m.tipo !== "pergunta" || respondida(m, mensagens)).map((m) => (
          <Mensagem key={m.id} m={m} mensagens={mensagens} />
        ))}
      </ol>

      {pensando && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status" data-testid="ia-pensando">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />A IA está pensando…
        </p>
      )}

      {erro && !pensando && (
        <Alert variant="destructive" data-testid="chat-erro">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>A IA não respondeu</AlertTitle>
          <AlertDescription>
            <p>{erro} As escolhas e as respostas já dadas continuam guardadas.</p>
            <Button type="button" variant="outline" size="sm" className="mt-1" disabled={desabilitado || enviando} onClick={onTentarDeNovo}>
              <RotateCcw aria-hidden="true" />
              Tentar de novo
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {pergunta && !pensando && (
        <form
          className="flex flex-col gap-3 rounded-lg border bg-card p-3 sm:p-4"
          data-testid="pergunta-atual"
          onSubmit={(e) => {
            e.preventDefault();
            if (podeResponder) onResponder(opcoes, texto.trim());
          }}
        >
          <fieldset className="flex min-w-0 flex-col gap-3">
            <legend className="mb-1 text-sm font-medium">
              {progresso && progresso.total > 0 && (
                <span className="mr-2 text-xs font-normal text-muted-foreground">
                  Pergunta {Math.min(progresso.respondidas + 1, progresso.total)} de {progresso.total}
                </span>
              )}
              {pergunta.texto}
            </legend>
            <p className="-mt-2 text-xs text-muted-foreground">{pergunta.multipla ? "Marque uma ou mais opções." : "Marque uma opção."}</p>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Opções">
              {pergunta.opcoes.map((o) => {
                const marcada = opcoes.includes(o.id);
                return (
                  <Button key={o.id} type="button" size="sm" variant={marcada ? "default" : "outline"} aria-pressed={marcada} disabled={desabilitado} onClick={() => alternar(o.id)}>
                    {marcada && <Check aria-hidden="true" />}
                    {o.rotulo}
                  </Button>
                );
              })}
            </div>
          </fieldset>

          {exemplos.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-xs text-muted-foreground">Pedidos prontos (preenchem a resposta curta):</p>
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Pedidos prontos">
                {exemplos.map((ex) => (
                  <Button key={ex} type="button" size="sm" variant="secondary" className="h-7 rounded-full text-xs" disabled={desabilitado} onClick={() => setTexto(ex)}>
                    {ex}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor={textoId} className="text-sm font-medium">
              Resposta curta (opcional)
            </label>
            <Textarea
              id={textoId}
              rows={2}
              value={texto}
              maxLength={LIM_RESPOSTA}
              aria-describedby={avisoId}
              disabled={desabilitado}
              onChange={(e) => setTexto(e.target.value)}
            />
            <p id={avisoId} className="text-xs text-muted-foreground">
              {AVISO_DADOS_PESSOAIS} {texto.length}/{LIM_RESPOSTA}
            </p>
          </div>

          <Button type="submit" className="self-end" disabled={!podeResponder} aria-busy={enviando}>
            {enviando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            Responder
          </Button>
        </form>
      )}
    </div>
  );
}

// As perguntas chegam todas de uma vez: no histórico, só as já respondidas (a atual fica no formulário).
const rodadaDe = (m: RoteiroMensagem) => Number(m.conteudo.rodada ?? 0);
const respondida = (p: RoteiroMensagem, mensagens: RoteiroMensagem[]) =>
  mensagens.some((m) => m.tipo === "resposta" && m.perguntaId === p.perguntaId && rodadaDe(m) === rodadaDe(p));

function Mensagem({ m, mensagens }: { m: RoteiroMensagem; mensagens: RoteiroMensagem[] }) {
  const daIa = m.autor.tipo !== "user";
  if (m.tipo === "aviso") {
    return (
      <li className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm" data-testid="chat-aviso">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
        <span>{String(m.conteudo.texto ?? "Aviso")}</span>
      </li>
    );
  }
  let corpo: string;
  if (m.tipo === "resposta") {
    const partes = rotulosDaResposta(m, mensagens);
    const t = typeof m.conteudo.texto === "string" ? m.conteudo.texto : "";
    corpo = [partes.join(", "), t].filter(Boolean).join(" · ");
  } else {
    corpo = String(m.conteudo.texto ?? m.conteudo.resumo ?? "");
  }
  return (
    <li className={cn("flex max-w-[85%] items-start gap-2", daIa ? "self-start" : "flex-row-reverse self-end")} data-testid={`chat-${m.tipo}`}>
      <span className="mt-1 flex size-6 shrink-0 items-center justify-center rounded-full bg-muted" aria-hidden="true">
        {daIa ? <Bot className="size-3.5" /> : <User className="size-3.5" />}
      </span>
      <span className={cn("min-w-0 rounded-lg px-3 py-2 text-sm break-words", daIa ? "bg-muted" : "bg-primary text-primary-foreground")}>
        <span className="sr-only">{daIa ? "IA: " : `${m.autor.nome ?? "Você"}: `}</span>
        {corpo}
      </span>
    </li>
  );
}
