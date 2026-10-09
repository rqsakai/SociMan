import { Loader2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import type { Asset } from "@/lib/assets";
import { perfilNomeDe, TETO_TEXTO, usePerfisTodos } from "@/lib/estudio";
import { useVozesAprovadas } from "@/lib/vozes";

// "Voz padrão" do avatar (spec 025, US2, T028): uma voz aprovada do mesmo perfil. Trocar salva na hora
// (`PATCH` com `vozId`; vazio limpa). Voz arquivada ou revogada continua aparecendo, com o aviso.
export function VozPadraoCard({ asset, onSalvo }: { asset: Asset; onSalvo: () => Promise<void> }) {
  const vozes = useVozesAprovadas(asset.perfilId);
  const perfis = usePerfisTodos();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const atual = asset.vozPadrao ?? null;
  const opcoes = (vozes.itens ?? []).map((v) => ({ id: v.id, nome: `${v.name} · ${perfilNomeDe(v, perfis.data)}` }));
  if (atual && !opcoes.some((o) => o.id === atual.id)) {
    opcoes.unshift({ id: atual.id, nome: `${atual.name}${atual.revogada ? " (revogada)" : atual.arquivada ? " (arquivada)" : ""}` });
  }
  const travado = asset.archived || asset.revogado;

  async function trocar(vozId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.assets.update(asset.id, { version: asset.version, vozId: vozId || null });
      await onSalvo();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="shadow-card" aria-labelledby="voz-padrao-titulo">
      <CardHeader>
        <CardTitle>
          <h2 id="voz-padrao-titulo">Voz padrão</h2>
        </CardTitle>
        <CardDescription>A voz que narra os vídeos deste avatar. Só vozes aprovadas, de qualquer perfil base.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Field label="Voz padrão" hint={vozes.truncado ? TETO_TEXTO : vozes.itens && vozes.itens.length === 0 ? "Nenhuma voz aprovada na agência: cadastre em AI Studio › Vozes." : undefined}>
          {({ id, describedBy }) => (
            <div className="flex items-center gap-2">
              <NativeSelect
                id={id}
                value={atual?.id ?? ""}
                disabled={busy || travado}
                aria-describedby={describedBy}
                onChange={(e) => void trocar(e.target.value)}
              >
                <option value="">Nenhuma</option>
                {opcoes.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.nome}
                  </option>
                ))}
              </NativeSelect>
              {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            </div>
          )}
        </Field>
        {atual && (atual.arquivada || atual.revogada) && (
          <p role="status" className="text-sm text-warning-foreground" data-testid="voz-padrao-aviso">
            {atual.revogada ? "Voz padrão revogada: escolha outra." : "Voz padrão arquivada: escolha outra."}
          </p>
        )}
        {atual && (
          <Link to={`/app/vozes/${atual.id}`} className="text-sm underline-offset-2 hover:underline">
            Abrir a voz {atual.name}
          </Link>
        )}
        {error !== null && <ApiErrorAlert error={error} />}
      </CardContent>
    </Card>
  );
}
