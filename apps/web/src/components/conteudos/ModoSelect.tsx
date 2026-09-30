/*
 * Escolha do modo de agendamento (spec 014, US3; R4): <select> nativo "Modo" com os quatro modos na
 * ordem da spec (os e2e usam selectOption); os que a conta não oferece ficam desabilitados, e a
 * lista abaixo mostra o que cada modo faz ou o motivo em pt-BR de estar indisponível.
 * Na 014 só o lembrete fica disponível. Na 015 (US2) os modos automáticos aparecem quando a conta
 * está conectada, com o `aviso` do modo; o membro os vê desabilitados ("Só donos agendam envio
 * automático") e `bloqueados` desabilita um modo com o motivo dado pela tela.
 */
import type { Modo } from "@sociman/contract";
import { Loader2 } from "lucide-react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Field, NativeSelect } from "@/components/ui/field";
import { MODOS, modoDescricao, modoLabel, useModos } from "@/lib/postagem";
import { ehAutomatico } from "@/lib/publicacao";
import { cn } from "@/lib/utils";

export function ModoSelect({
  contaId,
  value,
  onChange,
  dono = true,
  bloqueados = {},
}: {
  contaId: string | null;
  value: Modo;
  onChange: (m: Modo) => void;
  dono?: boolean;
  bloqueados?: Partial<Record<Modo, string>>;
}) {
  const modos = useModos(contaId);
  const bloqueio = (m: Modo) => bloqueados[m] ?? (!dono && ehAutomatico(m) ? "Só donos agendam envio automático." : null);
  const info = (m: Modo) => {
    const i = modos.data?.modos.find((x) => x.modo === m);
    const b = bloqueio(m);
    return i && i.disponivel && b ? { ...i, disponivel: false, motivo: b, aviso: null } : i;
  };

  return (
    <div className="space-y-2">
      <Field label="Modo">
        {({ id }) => (
          <NativeSelect id={id} value={value} disabled={!contaId || !modos.data} onChange={(e) => onChange(e.target.value as Modo)}>
            {MODOS.map((m) => (
              <option key={m} value={m} disabled={!info(m)?.disponivel}>
                {modoLabel[m]}
                {info(m) && !info(m)!.disponivel ? " (indisponível)" : ""}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      {!contaId && <p className="text-sm text-muted-foreground">Escolha a conta para ver os modos.</p>}
      {contaId && modos.isPending && <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Carregando os modos" />}
      {modos.isError && <ApiErrorAlert error={modos.error} />}
      {contaId && modos.data && (
        <ul aria-label="Modos desta conta" className="space-y-1 text-xs">
          {MODOS.map((m) => {
            const i = info(m);
            const disponivel = Boolean(i?.disponivel);
            return (
              <li key={m} className={cn("flex flex-wrap gap-x-1", !disponivel && "text-muted-foreground")}>
                <span className="font-medium">{modoLabel[m]}:</span>
                <span>{disponivel ? modoDescricao[m] : (i?.motivo ?? "Indisponível para esta conta.")}</span>
                {disponivel && i?.aviso && <span className="text-warning-foreground">({i.aviso})</span>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
