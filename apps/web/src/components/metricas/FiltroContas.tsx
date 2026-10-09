/*
 * Seletores de perfil e conta TikTok de /app/metricas (spec 016). Os valores moram na URL
 * (`perfil`, `conta`) e valem para as duas abas; trocar o perfil limpa a conta.
 */
import { useQuery } from "@tanstack/react-query";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { perfilKey } from "@/lib/perfis";
import { usePerfisAtivos } from "@/lib/usePerfis";

export function useContasTikTok(perfilId: string) {
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: Boolean(perfilId) });
  return (perfil.data?.contas ?? []).filter((c) => c.platform === "tiktok");
}

export function FiltroContas({
  perfilId,
  contaId,
  set,
  todasAsContas = true,
}: {
  perfilId: string;
  contaId: string;
  set: (patch: Record<string, string | null>) => void;
  todasAsContas?: boolean;
}) {
  const perfis = usePerfisAtivos();
  const contas = useContasTikTok(perfilId);
  return (
    <>
      <Field label="Perfil" className="w-full sm:w-52">
        {({ id }) => (
          <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value, conta: null })}>
            <option value="">{todasAsContas ? "Todos os perfis" : "Escolha um perfil"}</option>
            {perfis.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label="Conta TikTok" className="w-full sm:w-52">
        {({ id }) => (
          <NativeSelect id={id} value={contaId} disabled={!perfilId} onChange={(e) => set({ conta: e.target.value })}>
            <option value="">{!perfilId ? "Escolha um perfil" : todasAsContas ? "Todas as contas" : contas.length ? "Escolha a conta" : "Sem conta TikTok"}</option>
            {contas.map((c) => (
              <option key={c.id} value={c.id}>
                @{c.handle}
                {c.archived ? " (arquivada)" : ""}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
    </>
  );
}
