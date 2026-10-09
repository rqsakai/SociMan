import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import {
  DESCRICAO_MAX,
  escopoLabel,
  invalidarMcp,
  LIMITE_ESCRITAS,
  LIMITE_MINUTO,
  NOME_MAX,
  type McpCliente,
  type McpEscopo,
} from "@/lib/mcp";
import { fromLocal, localDateKey, parseDateKey, toIsoWithOffset } from "@/lib/tz";

interface Draft {
  nome: string;
  descricao: string;
  escopo: McpEscopo;
  limitePorMinuto: string;
  limiteEscritasDia: string;
  expiraEm: string; // "2026-12-31" (dia local; vale até 23:59)
}

function draftDe(c: McpCliente | null): Draft {
  return {
    nome: c?.nome ?? "",
    descricao: c?.descricao ?? "",
    escopo: c?.escopo ?? "leitura",
    limitePorMinuto: String(c?.limitePorMinuto ?? LIMITE_MINUTO.padrao),
    limiteEscritasDia: String(c?.limiteEscritasDia ?? LIMITE_ESCRITAS.padrao),
    expiraEm: c?.expiraEm ? localDateKey(c.expiraEm) : "",
  };
}

const inteiro = (s: string) => (/^\d+$/.test(s.trim()) ? Number(s.trim()) : NaN);

// Criar ou editar um cliente MCP (spec 009, US1/US5). Sem `cliente`: cria e devolve o token pelo
// `onCriado` (o diálogo do token é de quem chamou). Com `cliente`: edita nome, descrição, escopo,
// limites e vencimento, com a `version` (409 `version_conflict`).
export function NovoClienteDialog({
  open,
  onOpenChange,
  cliente = null,
  onCriado,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cliente?: McpCliente | null;
  onCriado?: (cliente: McpCliente, token: string) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => draftDe(cliente));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const editando = cliente !== null;

  function abrir(o: boolean) {
    if (o) {
      setDraft(draftDe(cliente));
      setErrors({});
      setError(null);
    }
    onOpenChange(o);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const nome = draft.nome.trim();
    if (!nome) errs.nome = "Informe o nome";
    else if (nome.length > NOME_MAX) errs.nome = `Até ${NOME_MAX} caracteres`;
    if (draft.descricao.length > DESCRICAO_MAX) errs.descricao = `Até ${DESCRICAO_MAX} caracteres`;
    const porMinuto = inteiro(draft.limitePorMinuto);
    if (!(porMinuto >= LIMITE_MINUTO.min && porMinuto <= LIMITE_MINUTO.max)) errs.limitePorMinuto = `De ${LIMITE_MINUTO.min} a ${LIMITE_MINUTO.max}`;
    const escritas = inteiro(draft.limiteEscritasDia);
    if (!(escritas >= LIMITE_ESCRITAS.min && escritas <= LIMITE_ESCRITAS.max)) errs.limiteEscritasDia = `De ${LIMITE_ESCRITAS.min} a ${LIMITE_ESCRITAS.max}`;
    let expiraEm: string | null = null;
    if (draft.expiraEm) {
      const { year, month, day } = parseDateKey(draft.expiraEm);
      const fim = fromLocal(year, month, day, 23, 59);
      if (fim.getTime() <= Date.now()) errs.expiraEm = "Escolha uma data no futuro";
      else expiraEm = toIsoWithOffset(fim);
    }
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;

    const campos = {
      nome,
      descricao: draft.descricao.trim(),
      escopo: draft.escopo,
      limitePorMinuto: porMinuto,
      limiteEscritasDia: escritas,
      expiraEm,
    };
    setBusy(true);
    setError(null);
    try {
      if (cliente) {
        await api.mcp.update(cliente.id, { version: cliente.version, ...campos });
        toast.success(`Cliente ${nome} salvo.`);
        await invalidarMcp(queryClient, cliente.id);
        onOpenChange(false);
      } else {
        const r = await api.mcp.create(campos);
        await invalidarMcp(queryClient);
        setDraft(draftDe(null));
        onOpenChange(false);
        onCriado?.(r.cliente, r.token);
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && abrir(o)}>
      <DialogContent>
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>{editando ? `Editar ${cliente.nome}` : "Novo cliente MCP"}</DialogTitle>
            <DialogDescription>
              {editando
                ? "Escopo e limites valem na próxima chamada do agente."
                : "Um cliente por agente. A credencial aparece uma vez, logo depois de criar."}
            </DialogDescription>
          </DialogHeader>
          <Field label="Nome" error={errors.nome} hint={`${draft.nome.length}/${NOME_MAX}`}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                value={draft.nome}
                maxLength={NOME_MAX}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setDraft({ ...draft, nome: e.target.value })}
              />
            )}
          </Field>
          <Field label="Descrição" error={errors.descricao}>
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={2}
                value={draft.descricao}
                maxLength={DESCRICAO_MAX}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setDraft({ ...draft, descricao: e.target.value })}
              />
            )}
          </Field>
          <Field
            label="Escopo"
            hint={draft.escopo === "propostas" ? "Lê tudo e grava anotações, propostas de texto, seleção de vídeo-fonte e textos de destino não aprovado." : "Só lê. Nenhuma escrita."}
          >
            {({ id, describedBy }) => (
              <NativeSelect id={id} aria-describedby={describedBy} value={draft.escopo} onChange={(e) => setDraft({ ...draft, escopo: e.target.value as McpEscopo })}>
                {(Object.keys(escopoLabel) as McpEscopo[]).map((e) => (
                  <option key={e} value={e}>
                    {escopoLabel[e]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Chamadas por minuto" error={errors.limitePorMinuto}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  type="number"
                  inputMode="numeric"
                  min={LIMITE_MINUTO.min}
                  max={LIMITE_MINUTO.max}
                  value={draft.limitePorMinuto}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  onChange={(e) => setDraft({ ...draft, limitePorMinuto: e.target.value })}
                />
              )}
            </Field>
            <Field label="Escritas por dia" error={errors.limiteEscritasDia} hint="0 = nenhuma escrita">
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  type="number"
                  inputMode="numeric"
                  min={LIMITE_ESCRITAS.min}
                  max={LIMITE_ESCRITAS.max}
                  value={draft.limiteEscritasDia}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  onChange={(e) => setDraft({ ...draft, limiteEscritasDia: e.target.value })}
                />
              )}
            </Field>
          </div>
          <Field label="Vence em" error={errors.expiraEm} hint="Opcional. Vencida, a credencial para de valer; a tela avisa 7 dias antes.">
            {({ id, describedBy, invalid }) => (
              <DateField
                id={id}
                value={draft.expiraEm}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(iso) => setDraft({ ...draft, expiraEm: iso })}
              />
            )}
          </Field>
          {error !== null && <ApiErrorAlert error={error} />}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => abrir(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={busy} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              {editando ? "Salvar" : "Criar cliente"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
