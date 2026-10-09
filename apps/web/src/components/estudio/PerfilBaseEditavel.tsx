import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PerfilBaseField } from "./PerfilBaseField";

// O perfil base no cabeçalho do detalhe (spec 029, T025; FR-007): trocar salva na hora, como uma
// edição versionada do item (`PATCH` com `perfilId`; "Nenhum" = null). Dono e membro mudam; reverter
// é do dono, pelo histórico.
export function PerfilBaseEditavel({
  valor,
  disabled,
  onSalvar,
}: {
  valor: string | null;
  disabled?: boolean;
  onSalvar: (perfilId: string | null) => Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function trocar(perfilId: string | null) {
    if (perfilId === valor) return;
    setBusy(true);
    setError(null);
    try {
      await onSalvar(perfilId);
      toast.success(perfilId ? "Perfil base trocado." : "Item sem perfil base.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2" data-testid="perfil-base-editavel">
      <div className="flex items-end gap-2">
        <PerfilBaseField value={valor} onChange={(v) => void trocar(v)} disabled={disabled || busy} className="w-full sm:w-64" />
        {busy && <Loader2 className="mb-2.5 size-4 animate-spin" aria-hidden="true" />}
      </div>
      {error !== null && <ApiErrorAlert error={error} />}
    </div>
  );
}
