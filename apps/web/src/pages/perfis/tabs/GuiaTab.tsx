import type { Conta, Perfil } from "@sociman/contract";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { HistoryHeading, VersionHistory } from "../../../components/VersionHistory";
import { GuiaForm } from "../../../components/guia/GuiaForm";
import {
  formatGuiaValue,
  guiaContaPath,
  guiaFieldLabel,
  useGuiaMutations,
  useGuiaPerfil,
  useGuiaPerfilVersions,
} from "../../../lib/guia";
import { contaPlatformText } from "../../../lib/perfis";

// Aba "Guia" do perfil (spec 017, US1): o guia de comunicação que vale para todas as contas do
// perfil, com o histórico (reverter só para o dono). Cada conta complementa na página dela.
export function GuiaTab({ perfil, contas }: { perfil: Perfil; contas: Conta[] }) {
  const guia = useGuiaPerfil(perfil.id);
  const versions = useGuiaPerfilVersions(perfil.id);
  const { reverterPerfil, aposPerfil } = useGuiaMutations();
  const ativas = contas.filter((c) => !c.archived);

  return (
    <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle>
            <h2>Guia de comunicação</h2>
          </CardTitle>
          <CardDescription>
            Como o perfil fala. Entra em todo pedido do assistente de IA das contas dele; o guia de cada conta complementa e vence em
            conflito.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {guia.isPending && <Skeleton className="h-96 w-full" />}
          {guia.isError && <ApiErrorAlert error={guia.error} />}
          {guia.data && (
            <GuiaForm
              key={guia.data.guia.version}
              nivel="perfil"
              perfilId={perfil.id}
              guia={guia.data.guia}
              contas={contas}
              arquivado={perfil.archived}
            />
          )}
        </CardContent>
      </Card>
      <div className="space-y-6">
        <Card className="shadow-card">
          <CardHeader>
            <CardTitle>
              <h2>Guia de cada conta</h2>
            </CardTitle>
            <CardDescription>O que muda por rede: tom, exemplos, hashtags fixas e o máximo delas.</CardDescription>
          </CardHeader>
          <CardContent>
            {ativas.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhuma conta ativa.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {ativas.map((c) => (
                  <li key={c.id}>
                    <Link to={guiaContaPath(c.id)} className="text-primary underline-offset-4 hover:underline">
                      @{c.handle} · {contaPlatformText(c)}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="shadow-card">
          <CardHeader>
            <HistoryHeading>Histórico do guia</HistoryHeading>
            <CardDescription>Reverter cria uma versão nova; nada é apagado.</CardDescription>
          </CardHeader>
          <CardContent>
            {versions.isPending && (
              <p aria-live="polite" className="text-sm text-muted-foreground">
                Carregando…
              </p>
            )}
            {versions.isError && <ApiErrorAlert error={versions.error} />}
            {versions.data && (
              <VersionHistory
                versions={versions.data.items}
                labels={guiaFieldLabel}
                formatValue={formatGuiaValue}
                onRevert={async (toVersion) => {
                  await reverterPerfil(perfil.id, guia.data?.guia.version ?? 0, toVersion);
                }}
                onReload={async () => {
                  await aposPerfil(perfil.id);
                }}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
