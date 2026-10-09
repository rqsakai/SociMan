import { useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquarePlus, MessagesSquare } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { criarAnotacao, invalidarAnotacoes, TEXTO_MAX, useAnotacoesDisponiveis, useAnotacoesDoItem, type AlvoTipo, type Anotacao } from "@/lib/anotacoes";
import { PropostaCard } from "./PropostaCard";

// Anotações e propostas presas a um item (spec 009, US4; T050): destino, conteúdo, corte,
// canal-fonte e vídeo-fonte. As abertas vêm primeiro, cada uma com o selo do autor. O humano também
// anota ("Anotar"); as propostas de texto só têm "Aplicar" onde há formulário (`onAplicar`).
export function AnotacoesDoItem({
  alvoTipo,
  alvoId,
  onAplicar,
  aplicarBloqueado,
  titulo = "Anotações e propostas",
  arquivado = false,
}: {
  alvoTipo: AlvoTipo;
  alvoId: string;
  onAplicar?: (a: Anotacao) => void;
  aplicarBloqueado?: string | null;
  titulo?: string;
  arquivado?: boolean;
}) {
  const queryClient = useQueryClient();
  const disponivel = useAnotacoesDisponiveis();
  const anotacoes = useAnotacoesDoItem(alvoTipo, alvoId);
  const [novaOpen, setNovaOpen] = useState(false);
  const [texto, setTexto] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const itens = anotacoes.data ?? [];
  const abertas = itens.filter((a) => a.situacao === "aberta").length;

  async function anotar() {
    const t = texto.trim();
    if (!t) return;
    setBusy(true);
    setError(null);
    try {
      await criarAnotacao({ alvoTipo, alvoId, tipo: "observacao", texto: t });
      toast.success("Anotação gravada.");
      setTexto("");
      setNovaOpen(false);
      await invalidarAnotacoes(queryClient);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  // API sem as rotas de anotações (spec 009 ainda não aplicada): a seção não aparece.
  if (!disponivel) return null;

  return (
    <section className="space-y-3" aria-label={titulo}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <MessagesSquare className="size-4 text-muted-foreground" aria-hidden="true" />
          {titulo}
          {abertas > 0 && <Badge className="bg-info text-info-foreground">{abertas} aberta(s)</Badge>}
        </h3>
        {!arquivado && !novaOpen && (
          <Button type="button" size="sm" variant="ghost" onClick={() => setNovaOpen(true)}>
            <MessageSquarePlus aria-hidden="true" />
            Anotar
          </Button>
        )}
      </div>
      {novaOpen && (
        <div className="space-y-2 rounded-lg border p-3">
          <Field label="Nova anotação" hint={`${texto.length}/${TEXTO_MAX}`}>
            {({ id, describedBy }) => (
              <Textarea id={id} rows={3} value={texto} maxLength={TEXTO_MAX} aria-describedby={describedBy} onChange={(e) => setTexto(e.target.value)} />
            )}
          </Field>
          <div className="flex gap-2">
            <Button type="button" size="sm" disabled={busy || !texto.trim()} aria-busy={busy} onClick={() => void anotar()}>
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              Gravar anotação
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setNovaOpen(false)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
      {error !== null && <ApiErrorAlert error={error} />}
      {anotacoes.isError && <ApiErrorAlert error={anotacoes.error} />}
      {anotacoes.isPending ? (
        <p className="text-sm text-muted-foreground">Carregando…</p>
      ) : itens.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhuma anotação.</p>
      ) : (
        <ul className="space-y-2">
          {itens.map((a) => (
            <li key={a.id}>
              <PropostaCard anotacao={a} onAplicar={onAplicar} aplicarBloqueado={aplicarBloqueado} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// A seção num cartão, para as páginas de detalhe; sem as rotas de anotações na API, nem o cartão aparece.
export function AnotacoesCard(props: Parameters<typeof AnotacoesDoItem>[0]) {
  const disponivel = useAnotacoesDisponiveis();
  if (!disponivel) return null;
  return (
    <Card className="shadow-card">
      <CardContent>
        <AnotacoesDoItem {...props} />
      </CardContent>
    </Card>
  );
}
