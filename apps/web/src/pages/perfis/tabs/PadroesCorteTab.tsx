import { ApiError, type Conta, type Perfil } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfigCampos, configFrom, type ConfigValues } from "../../../components/envios/ConfigCampos";
import { HistoryHeading, VersionHistory } from "../../../components/VersionHistory";
import { api } from "../../../lib/api";
import {
  formatPadroesValue,
  padroesApiField,
  padroesFieldLabel,
  padroesKey,
  padroesVersionsKey,
  validatePadroes,
} from "../../../lib/envios";
import { contaPlatformText } from "../../../lib/perfis";

// Aba "Padrões de corte" do perfil (spec 006, US3; T053): duração mínima e máxima, quantidade,
// layout, formato, legenda (do kit, do OpenShorts ou nenhuma), marca automática e a conta padrão da
// postagem. Preenchem todo envio do perfil e podem ser ajustados envio a envio. Nunca salvo =
// padrão (versão 0). Histórico com "Reverter" só para o dono.
export function PadroesCorteTab({ perfil, contas }: { perfil: Perfil; contas: Conta[] }) {
  const queryClient = useQueryClient();
  const padroes = useQuery({ queryKey: padroesKey(perfil.id), queryFn: () => api.padroesCorte.get(perfil.id) });
  const versions = useQuery({ queryKey: padroesVersionsKey(perfil.id), queryFn: () => api.padroesCorte.versions(perfil.id) });
  const p = padroes.data?.padroes;
  const [config, setConfig] = useState<ConfigValues | null>(null);
  const [contaId, setContaId] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (p) {
      setConfig(configFrom(p));
      setContaId(p.contaPadraoId ?? "");
    }
  }, [p]);

  async function refresh() {
    setError(null);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: padroesKey(perfil.id) }),
      queryClient.invalidateQueries({ queryKey: padroesVersionsKey(perfil.id) }),
    ]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!config || !p) return;
    setError(null);
    const errs = validatePadroes(config);
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    setSaving(true);
    try {
      await api.padroesCorte.put(perfil.id, { version: p.version, ...config, contaPadraoId: contaId || null });
      toast.success("Padrões de corte salvos.");
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_padroes" && err.field) {
        setErrors({ [padroesApiField[err.field] ?? err.field]: err.message });
      } else setError(err);
    } finally {
      setSaving(false);
    }
  }

  const contasAtivas = contas.filter((c) => !c.archived);

  return (
    <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle>
            <h2>Padrões de corte</h2>
          </CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            Preenchem todo envio deste perfil ao OpenShorts; dá para ajustar envio a envio.
            {p && (p.version === 0 ? <Badge variant="secondary">Padrão (ainda não salvo)</Badge> : <Badge variant="secondary">Versão {p.version}</Badge>)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {padroes.isError && <ApiErrorAlert error={padroes.error} />}
          {!config ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
              <ConfigCampos value={config} onChange={setConfig} errors={errors} disabled={saving || perfil.archived} />
              <Field label="Conta padrão da postagem" error={errors.contaPadraoId} hint="A conta que já vem escolhida ao preparar a postagem do corte.">
                {({ id, describedBy, invalid }) => (
                  <NativeSelect id={id} value={contaId} aria-invalid={invalid} aria-describedby={describedBy} disabled={saving || perfil.archived} onChange={(e) => setContaId(e.target.value)}>
                    <option value="">Nenhuma</option>
                    {contasAtivas.map((c) => (
                      <option key={c.id} value={c.id}>
                        {contaPlatformText(c)} @{c.handle}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <p className="text-xs text-muted-foreground">O gancho automático do OpenShorts fica sempre desligado: o gancho vem do kit.</p>
              {error !== null && <ApiErrorAlert error={error} onReload={() => void refresh()} />}
              <Button type="submit" disabled={saving || perfil.archived} aria-busy={saving}>
                {saving ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                Salvar padrões
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
      <Card className="shadow-card">
        <CardHeader>
          <HistoryHeading>Histórico dos padrões</HistoryHeading>
        </CardHeader>
        <CardContent>
          {versions.isError && <ApiErrorAlert error={versions.error} />}
          {versions.data && (
            <VersionHistory
              versions={versions.data.items}
              labels={padroesFieldLabel}
              formatValue={(field, value) =>
                field === "conta_padrao_id" && typeof value === "string"
                  ? (() => {
                      const c = contas.find((x) => x.id === value);
                      return c ? `${contaPlatformText(c)} @${c.handle}` : value.slice(0, 8);
                    })()
                  : formatPadroesValue(field, value)
              }
              onRevert={async (toVersion) => {
                await api.padroesCorte.revert(perfil.id, p?.version ?? 0, toVersion);
                await refresh();
              }}
              onReload={refresh}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
