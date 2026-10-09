/*
 * "Montar com IA" (spec 017, US3): o dono descreve a conta em poucas palavras e a IA propõe tom,
 * regras, vocabulário, proibidas e emojis (sem fixas, máximo nem exemplos). "Usar no formulário" só
 * preenche o formulário; o guia muda ao salvar. "Outra versão" e o descarte seguem a 008.
 */
import type { GuiaCampos, IaChamada } from "@sociman/contract";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { emojisLabel } from "@/lib/guia";
import { descartarChamadas, iaErroRepetivel, iaErroTexto, INSTRUCAO_MAX, novoSessaoId } from "@/lib/ia";

export function MontarGuiaDialog({
  perfilId,
  contaId,
  guiaAtual,
  onUsar,
}: {
  perfilId: string;
  contaId?: string;
  guiaAtual: GuiaCampos;
  onUsar: (proposta: GuiaCampos, chamadaId: string) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const [sessaoId, setSessaoId] = useState(novoSessaoId);
  const [descricao, setDescricao] = useState("");
  const [chamadas, setChamadas] = useState<IaChamada[]>([]);
  const [atual, setAtual] = useState<string | null>(null);
  const [gerando, setGerando] = useState(false);
  const [erro, setErro] = useState<unknown>(null);

  const chamada = chamadas.find((c) => c.id === atual) ?? null;
  const proposta = chamada?.proposta?.guia ?? null;

  function reiniciar(descartar: boolean) {
    if (descartar) descartarChamadas(chamadas.map((c) => c.id));
    setSessaoId(novoSessaoId());
    setChamadas([]);
    setAtual(null);
    setErro(null);
  }

  async function gerar(outra: boolean) {
    setErro(null);
    setGerando(true);
    try {
      const { chamada: nova } = await api.ia.guiaMontar({
        perfilId,
        ...(contaId ? { contaId } : {}),
        descricao: descricao.trim(),
        guiaAtual,
        sessaoId,
        anteriores: outra ? chamadas.slice(-5).map((c) => c.id) : [],
      });
      setChamadas((cur) => [...cur, nova]);
      setAtual(nova.id);
    } catch (err) {
      setErro(err);
    } finally {
      setGerando(false);
    }
  }

  function usar() {
    if (!chamada || !proposta) return;
    descartarChamadas(chamadas.filter((c) => c.id !== chamada.id).map((c) => c.id));
    onUsar(proposta, chamada.id);
    reiniciar(false);
    setAberto(false);
  }

  return (
    <Dialog
      open={aberto}
      onOpenChange={(open) => {
        if (!open) reiniciar(true);
        setAberto(open);
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          <Sparkles aria-hidden="true" />
          Montar com IA
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Montar o guia com IA</DialogTitle>
          <DialogDescription>
            Descreva {contaId ? "o que esta conta tem de diferente do perfil" : "a conta"} em poucas palavras. A proposta preenche o
            formulário; nada muda até você salvar.
          </DialogDescription>
        </DialogHeader>
        <Field
          label="Descrição curta"
          hint={
            <span aria-live="polite">
              {descricao.length.toLocaleString("pt-BR")}/{INSTRUCAO_MAX.toLocaleString("pt-BR")}
            </span>
          }
        >
          {({ id, describedBy }) => (
            <Textarea
              id={id}
              rows={3}
              maxLength={INSTRUCAO_MAX}
              value={descricao}
              aria-describedby={describedBy}
              placeholder="Ex.: perfil de achadinhos de cozinha, fala como amiga"
              onChange={(e) => setDescricao(e.target.value)}
            />
          )}
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" disabled={gerando || !descricao.trim()} aria-busy={gerando} onClick={() => void gerar(false)}>
            {gerando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
            {gerando ? "Gerando…" : "Gerar proposta"}
          </Button>
          {chamada && (
            <Button type="button" size="sm" variant="outline" disabled={gerando || !descricao.trim()} onClick={() => void gerar(true)}>
              <RefreshCw aria-hidden="true" />
              Outra versão
            </Button>
          )}
        </div>

        {erro !== null && (
          <Alert variant="destructive">
            <AlertTitle>Não foi possível gerar</AlertTitle>
            <AlertDescription>
              <p>{iaErroTexto(erro)}</p>
              {iaErroRepetivel(erro) && <p>Tente de novo.</p>}
            </AlertDescription>
          </Alert>
        )}

        {chamadas.length > 1 && (
          <div role="group" aria-label="Versões desta sessão" className="flex flex-wrap gap-1">
            {chamadas.map((c, i) => (
              <Button
                key={c.id}
                type="button"
                size="sm"
                variant={c.id === atual ? "secondary" : "ghost"}
                aria-pressed={c.id === atual}
                onClick={() => setAtual(c.id)}
              >
                Versão {i + 1}
              </Button>
            ))}
          </div>
        )}

        {chamada && proposta && (
          <section aria-label="Proposta de guia" className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
            <dl className="space-y-2">
              <Item titulo="Tom de voz">{proposta.tom}</Item>
              <Item titulo="Faça">{proposta.faca}</Item>
              <Item titulo="Não faça">{proposta.naoFaca}</Item>
              <Item titulo="Vocabulário da casa">{proposta.vocabulario}</Item>
              <Item titulo="Palavras proibidas">{proposta.proibidas}</Item>
              <Item titulo="Emojis">
                {[proposta.emojis ? emojisLabel[proposta.emojis] : "", (proposta.emojisPreferidos ?? []).join(" ")].filter(Boolean).join(" · ")}
              </Item>
            </dl>
            {chamada.explicacao && <p>{chamada.explicacao}</p>}
            {chamada.avisos.length > 0 && (
              <ul aria-label="Avisos da IA" className="list-disc space-y-0.5 pl-5 text-warning-foreground">
                {chamada.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
          </section>
        )}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => {
              reiniciar(true);
              setAberto(false);
            }}>
            Descartar
          </Button>
          <Button type="button" disabled={!proposta || gerando} onClick={usar}>
            Usar no formulário
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Item({ titulo, children }: { titulo: string; children: string | string[] | undefined }) {
  const texto = Array.isArray(children) ? children : children ? [children] : [];
  if (texto.length === 0) return null;
  return (
    <div>
      <dt className="text-xs font-semibold text-muted-foreground uppercase">{titulo}</dt>
      <dd>
        {texto.length === 1 ? (
          texto[0]
        ) : (
          <ul className="list-disc pl-5">
            {texto.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        )}
      </dd>
    </div>
  );
}
