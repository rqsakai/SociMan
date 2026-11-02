/*
 * O "Não aprovo" do wizard (spec 031, US3, T037; FR-016, R6): o chat aberto naquele item. O
 * operador marca opções de troca prontas (por tipo de item) e/ou escreve um texto curto; a IA
 * transforma o pedido em ajuste e refaz só o item e o que depende dele. Quando ela não entende,
 * devolve um esclarecimento com opções, que aparecem aqui como botões. Nada mostra prompt nem fala.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Loader2, Send, TriangleAlert, User, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { Roteiro } from "@/lib/roteiros";
import { cn } from "@/lib/utils";
import {
  AVISO_DADOS_PESSOAIS,
  LIM_OPCOES_TROCA,
  LIM_RESPOSTA,
  OPCOES_TROCA,
  ajusteAberto,
  esclarecimentoPendente,
  invalidarConversa,
  mensagensDoAlvo,
  useConversa,
  type RoteiroAlvoRecusa,
  type RoteiroMensagem,
  type RoteiroPergunta,
} from "@/lib/videoGuiado";

export interface NaoAprovoProps {
  roteiro: Roteiro;
  alvo: RoteiroAlvoRecusa;
  // "a narração", "o quadro Fim da cena 2"…
  rotulo: string;
  // opções somadas às prontas do tipo (ex.: o "texto mais curto" do aviso de fala)
  inicial?: string[];
  onFechar: () => void;
}

export function NaoAprovo({ roteiro: r, alvo, rotulo, inicial = [], onFechar }: NaoAprovoProps) {
  const queryClient = useQueryClient();
  const conv = useConversa(r.id);
  const [marcadas, setMarcadas] = useState<string[]>(inicial);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const tituloId = useId();
  const textoId = useId();
  const avisoId = useId();

  const doAlvo = mensagensDoAlvo(conv.data?.mensagens ?? [], alvo);
  const pendente = esclarecimentoPendente(doAlvo);
  const pensando = ajusteAberto(r) || (conv.data?.geracaoAberta ?? null) !== null;
  const pergunta = pendente ? (pendente.conteudo as unknown as Partial<RoteiroPergunta>) : null;
  const opcoes: { id: string; rotulo: string }[] = pergunta
    ? (pergunta.opcoes ?? []).map((o) => ({ id: o.id, rotulo: o.rotulo }))
    : [...new Set([...inicial, ...OPCOES_TROCA[alvo.tipo]])].map((o) => ({ id: o, rotulo: o }));
  const multipla = pergunta ? pergunta.multipla !== false : true;
  // Um esclarecimento novo começa limpo (as opções dele são outras).
  const pendenteId = pendente?.id ?? null;
  useEffect(() => {
    if (pendenteId) setMarcadas([]);
  }, [pendenteId]);
  const podeEnviar = !enviando && !pensando && (marcadas.length > 0 || texto.trim() !== "");

  function alternar(id: string) {
    if (!multipla) return setMarcadas((m) => (m[0] === id ? [] : [id]));
    setMarcadas((m) => (m.includes(id) ? m.filter((x) => x !== id) : m.length < LIM_OPCOES_TROCA ? [...m, id] : m));
  }

  async function enviar() {
    setError(null);
    setEnviando(true);
    try {
      await api.roteiros.recusar(r.id, { alvo, opcoes: marcadas, texto: texto.trim() || null, version: r.version });
      setMarcadas([]);
      setTexto("");
      await invalidarConversa(queryClient, r.id);
    } catch (err) {
      setError(err);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-primary/40 bg-card p-3" aria-labelledby={tituloId} data-testid="nao-aprovo">
      <div className="flex items-start gap-2">
        <h4 id={tituloId} className="min-w-0 flex-1 text-sm font-semibold">
          Não aprovo {rotulo}
        </h4>
        <Button type="button" variant="ghost" size="icon" className="-mt-1 -mr-1 size-7" aria-label="Fechar o pedido de troca" onClick={onFechar}>
          <X aria-hidden="true" />
        </Button>
      </div>

      {doAlvo.length > 0 && (
        <ol role="log" aria-label={`Pedidos de troca: ${rotulo}`} aria-live="polite" className="flex flex-col gap-2" data-testid="nao-aprovo-mensagens">
          {doAlvo.map((m) => (
            <Mensagem key={m.id} m={m} />
          ))}
        </ol>
      )}

      {pensando && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status" data-testid="ia-ajustando">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />A IA está ajustando…
        </p>
      )}
      {!pensando && !pendente && doAlvo.some((m) => m.tipo === "pedido_troca") && (
        <p className="text-sm text-muted-foreground" role="status" data-testid="ajuste-feito">
          Pedido aplicado. O item é refeito e volta para você aprovar.
        </p>
      )}

      {!pensando && (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (podeEnviar) void enviar();
          }}
        >
          <fieldset className="flex min-w-0 flex-col gap-2">
            <legend className="mb-1 text-sm">{pergunta?.texto ?? "O que trocar? Marque uma ou mais opções."}</legend>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={pergunta ? "Opções da IA" : "Trocas prontas"} data-testid={pergunta ? "opcoes-esclarecimento" : "trocas-prontas"}>
              {opcoes.map((o) => {
                const on = marcadas.includes(o.id);
                return (
                  <Button key={o.id} type="button" size="sm" variant={on ? "default" : "outline"} className="h-8 rounded-full" aria-pressed={on} onClick={() => alternar(o.id)}>
                    {on && <Check aria-hidden="true" />}
                    {o.rotulo}
                  </Button>
                );
              })}
            </div>
          </fieldset>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={textoId} className="text-sm font-medium">
              Ou diga com suas palavras (opcional)
            </label>
            <Textarea id={textoId} rows={2} value={texto} maxLength={LIM_RESPOSTA} aria-describedby={avisoId} onChange={(e) => setTexto(e.target.value)} />
            <p id={avisoId} className="text-xs text-muted-foreground">
              {AVISO_DADOS_PESSOAIS} {texto.length}/{LIM_RESPOSTA}
            </p>
          </div>
          {error !== null && <ApiErrorAlert error={error} />}
          <Button type="submit" size="sm" className="self-end" disabled={!podeEnviar} aria-busy={enviando}>
            {enviando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            {pergunta ? "Responder" : "Pedir a troca"}
          </Button>
        </form>
      )}
    </section>
  );
}

function Mensagem({ m }: { m: RoteiroMensagem }) {
  if (m.tipo === "aviso") {
    return (
      <li className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm" data-testid="nao-aprovo-aviso">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
        <span>{String(m.conteudo.texto ?? "Aviso")}</span>
      </li>
    );
  }
  const daIa = m.tipo === "esclarecimento";
  const corpo = daIa
    ? String(m.conteudo.texto ?? "")
    : [((m.conteudo.opcoes as string[] | undefined) ?? []).join(", "), typeof m.conteudo.texto === "string" ? m.conteudo.texto : ""].filter(Boolean).join(" · ");
  return (
    <li className={cn("flex max-w-[90%] items-start gap-2", daIa ? "self-start" : "flex-row-reverse self-end")} data-testid={`nao-aprovo-${m.tipo}`}>
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
