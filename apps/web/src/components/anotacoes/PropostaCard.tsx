import { useQueryClient } from "@tanstack/react-query";
import { Archive, ClipboardPaste, Loader2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { AgenteSelo } from "@/components/mcp/AgenteSelo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import {
  aceitarCenaHref,
  alvoTipoLabel,
  arquivarAnotacao,
  camposCena,
  camposTexto,
  descartarAnotacao,
  invalidarAnotacoes,
  MOTIVO_DESCARTE_MAX,
  situacaoAnotacaoLabel,
  situacaoAnotacaoTone,
  tipoAnotacaoLabel,
  type Anotacao,
} from "@/lib/anotacoes";
import { useAuth } from "@/lib/authStore";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";

// Uma anotação ou proposta (spec 009, US4), com o selo do autor. Ações só para abertas:
// - "Aplicar" (proposta de texto, quando o item tem formulário): `onAplicar` preenche o formulário,
//   sem salvar; quem grava é o "Salvar" humano, com o `propostaId`;
// - "Descartar" (humano), com motivo opcional;
// - "Arquivar": o autor humano ou um dono.
// `mostrarAlvo` põe o link do item (caixa "Propostas dos agentes").
export function PropostaCard({
  anotacao: a,
  onAplicar,
  aplicarBloqueado,
  mostrarAlvo = false,
}: {
  anotacao: Anotacao;
  onAplicar?: (a: Anotacao) => void;
  aplicarBloqueado?: string | null;
  mostrarAlvo?: boolean;
}) {
  const queryClient = useQueryClient();
  const user = useAuth((s) => s.user);
  const [busy, setBusy] = useState<"descartar" | "arquivar" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [descartarOpen, setDescartarOpen] = useState(false);
  const [motivo, setMotivo] = useState("");
  const aberta = a.situacao === "aberta";
  const podeArquivar = aberta && (user?.role === "dono" || (a.autor.tipo === "usuario" && a.autor.id === user?.id));
  const campos = camposTexto(a);
  // spec 010: proposta de cena; "Aceitar" abre o formulário da cena preenchido (nada salvo).
  const cena = camposCena(a);
  const aceitarCena = cena ? aceitarCenaHref(a) : null;

  async function run(kind: NonNullable<typeof busy>, fn: () => Promise<unknown>, msg: string) {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      toast.success(msg);
      await invalidarAnotacoes(queryClient);
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className={cn("space-y-2 rounded-lg border p-3", aberta ? "bg-card" : "bg-muted/30")} aria-label={`${tipoAnotacaoLabel[a.tipo]} de ${a.autor.nome ?? "—"}`}>
      <header className="flex flex-wrap items-center gap-2 text-sm">
        {a.autor.tipo === "mcp_client" ? <AgenteSelo nome={a.autor.nome ?? "—"} /> : <span className="font-medium">{a.autor.nome ?? "—"}</span>}
        <span className="text-muted-foreground">{tipoAnotacaoLabel[a.tipo]}</span>
        <Badge className={situacaoAnotacaoTone[a.situacao]}>{situacaoAnotacaoLabel[a.situacao]}</Badge>
        <time dateTime={a.createdAt} className="ml-auto text-xs text-muted-foreground">
          {formatDateTime(a.createdAt)}
        </time>
      </header>
      {mostrarAlvo && (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">{alvoTipoLabel[a.alvo.tipo]}:</span>
          {a.alvo.link ? (
            <Link to={a.alvo.link} className="font-medium underline-offset-2 hover:underline">
              {a.alvo.titulo || "abrir item"}
            </Link>
          ) : (
            <span className="font-medium">{a.alvo.titulo || "—"}</span>
          )}
          {a.alvo.arquivado && <Badge variant="outline">item arquivado</Badge>}
        </p>
      )}
      <p className="text-sm break-words whitespace-pre-wrap">{a.texto}</p>
      {campos && (
        <dl className="grid gap-x-3 gap-y-1 rounded-md bg-muted/40 p-2 text-sm sm:grid-cols-[auto_1fr]">
          {campos.titulo != null && (
            <>
              <dt className="text-muted-foreground">Título</dt>
              <dd className="break-words">{campos.titulo || "—"}</dd>
            </>
          )}
          {campos.descricao != null && (
            <>
              <dt className="text-muted-foreground">Descrição</dt>
              <dd className="break-words whitespace-pre-wrap">{campos.descricao || "—"}</dd>
            </>
          )}
          {campos.hashtags != null && (
            <>
              <dt className="text-muted-foreground">Hashtags</dt>
              <dd className="break-words">{campos.hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ") || "—"}</dd>
            </>
          )}
        </dl>
      )}
      {cena && (
        <dl className="grid gap-x-3 gap-y-1 rounded-md bg-muted/40 p-2 text-sm sm:grid-cols-[auto_1fr]">
          {(
            [
              ["Nome", cena.nome],
              ["Ação", cena.acao],
              ["Fala", cena.fala],
              ["Câmera", cena.camera],
              ["Iluminação e estilo", cena.estilo],
              ["Áudio", cena.audio],
              ["Produto", cena.produtoNome],
              ["Duração", cena.duracaoS != null ? `${cena.duracaoS} s` : null],
            ] as const
          )
            .filter(([, v]) => v != null && v !== "")
            .map(([rotulo, v]) => (
              <div key={rotulo} className="contents">
                <dt className="text-muted-foreground">{rotulo}</dt>
                <dd className="break-words whitespace-pre-wrap">{v}</dd>
              </div>
            ))}
        </dl>
      )}
      {!aberta && (a.resolvidaPor || a.motivoDescarte) && (
        <p className="text-xs text-muted-foreground">
          {a.resolvidaPor && `${situacaoAnotacaoLabel[a.situacao]} por ${a.resolvidaPor.name}${a.resolvidaEm ? ` em ${formatDateTime(a.resolvidaEm)}` : ""}.`}
          {a.motivoDescarte && ` Motivo: ${a.motivoDescarte}`}
        </p>
      )}
      {aberta && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Ações da anotação">
          {aceitarCena && (
            <Button type="button" size="sm" asChild>
              <Link to={aceitarCena}>
                <ClipboardPaste aria-hidden="true" />
                Aceitar
              </Link>
            </Button>
          )}
          {onAplicar && campos && (
            <Button type="button" size="sm" disabled={Boolean(aplicarBloqueado)} title={aplicarBloqueado ?? undefined} onClick={() => onAplicar(a)}>
              <ClipboardPaste aria-hidden="true" />
              Aplicar
            </Button>
          )}
          <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => setDescartarOpen(true)}>
            <X aria-hidden="true" />
            Descartar
          </Button>
          {podeArquivar && (
            <ConfirmButton
              label="Arquivar"
              icon={Archive}
              size="sm"
              variant="ghost"
              busy={busy === "arquivar"}
              disabled={busy !== null}
              title="Arquivar esta anotação?"
              description="Ela sai das abertas e fica no histórico."
              onConfirm={() => void run("arquivar", () => arquivarAnotacao(a), "Anotação arquivada.")}
            />
          )}
        </div>
      )}
      {onAplicar && campos && aberta && aplicarBloqueado && <p className="text-xs text-muted-foreground">{aplicarBloqueado}</p>}
      {error !== null && <ApiErrorAlert error={error} onReload={() => void invalidarAnotacoes(queryClient)} />}

      <Dialog open={descartarOpen} onOpenChange={(o) => busy === null && setDescartarOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Descartar a {tipoAnotacaoLabel[a.tipo].toLowerCase()}?</DialogTitle>
            <DialogDescription>Ela sai das abertas. O agente vê o motivo, se você escrever um.</DialogDescription>
          </DialogHeader>
          <Field label="Motivo (opcional)" hint={`${motivo.length}/${MOTIVO_DESCARTE_MAX}`}>
            {({ id, describedBy }) => (
              <Textarea id={id} rows={3} value={motivo} maxLength={MOTIVO_DESCARTE_MAX} aria-describedby={describedBy} onChange={(e) => setMotivo(e.target.value)} />
            )}
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy !== null} onClick={() => setDescartarOpen(false)}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={busy !== null}
              aria-busy={busy === "descartar"}
              onClick={() =>
                void run("descartar", () => descartarAnotacao(a, motivo), "Proposta descartada.").then((ok) => {
                  if (ok) {
                    setDescartarOpen(false);
                    setMotivo("");
                  }
                })
              }
            >
              {busy === "descartar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <X aria-hidden="true" />}
              Descartar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </article>
  );
}
