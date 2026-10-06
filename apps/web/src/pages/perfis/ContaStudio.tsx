import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { usePageMeta } from "@/components/shell";
import { CoberturaBarras } from "@/components/studio/CoberturaBarras";
import { EnvioArquivos } from "@/components/studio/EnvioArquivos";
import { ListaImportacoes } from "@/components/studio/ListaImportacoes";
import { PreviaStudio } from "@/components/studio/PreviaStudio";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/authStore";
import { useGuiaConta } from "@/lib/guia";
import { perfilKey } from "@/lib/perfis";
import { useCoberturaStudio, useImportacoesStudio, useStudioMutations, type ImportacaoStudio, type Previa } from "@/lib/studio";

// /app/contas/:id/studio (spec 020, R12): o histórico importado do TikTok Studio da conta.
// 1. Cobertura (todos); 2. Importar → prévia → confirmar (só dono); 3. Importações, com "Desfazer"
// (só dono). Fica fora da rota lazy do analytics: escreve e não usa ECharts. Não há leitura da conta
// sozinha: o perfil vem do guia da conta e o @, do detalhe do perfil (como no ContaGuia).
export default function ContaStudio() {
  const { id = "" } = useParams();
  const ehDono = useAuth((s) => s.user?.role === "dono");
  const guia = useGuiaConta(id);
  const perfilId = guia.data?.guia.perfilId ?? "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: Boolean(perfilId) });
  const conta = perfil.data?.contas.find((c) => c.id === id);
  const cobertura = useCoberturaStudio(id);
  const lista = useImportacoesStudio(id);
  const mut = useStudioMutations(id);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [envio, setEnvio] = useState(0);
  const [desfazendo, setDesfazendo] = useState<string | null>(null);

  const title = conta ? `Histórico do Studio de @${conta.handle}` : "Histórico do Studio";
  usePageMeta({
    title,
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(perfil.data ? [{ label: perfil.data.perfil.name, to: `/app/perfis/${perfilId}?aba=contas` }] : []),
    ],
  });

  function fecharPrevia() {
    setPrevia(null);
    mut.confirmar.reset();
    mut.previa.reset();
    setEnvio((n) => n + 1); // limpa o input de arquivos
  }

  async function desfazer(imp: ImportacaoStudio) {
    setDesfazendo(imp.id);
    try {
      await mut.desfazer.mutateAsync({ id: imp.id, version: imp.version });
      toast.success("Importação desfeita. Os dias saíram do analytics.");
    } catch {
      // o erro aparece acima da lista (mut.desfazer.error)
    } finally {
      setDesfazendo(null);
    }
  }

  return (
    <div className="space-y-6">
      {perfilId && (
        <Link to={`/app/perfis/${perfilId}?aba=contas`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" aria-hidden="true" />
          Contas do perfil
        </Link>
      )}
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">{title}</h1>
        <p className="text-sm text-muted-foreground">
          Os números diários que o TikTok Studio guarda (cerca de 1 ano) completam os dias antes da coleta pela API. O analytics usa o Studio só nos dias que a coleta
          não cobre inteiros e diz quando usou.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[3fr_2fr]">
        <div className="min-w-0 space-y-6">
          {ehDono && (
            <Card className="shadow-card" role="region" aria-labelledby="studio-importar">
              <CardHeader>
                <CardTitle>
                  <h2 id="studio-importar">Importar</h2>
                </CardTitle>
                <CardDescription>Primeiro você vê o que seria gravado; nada entra antes de confirmar.</CardDescription>
              </CardHeader>
              <CardContent>
                {previa ? (
                  <PreviaStudio
                    previa={previa}
                    confirmando={mut.confirmar.isPending}
                    erro={mut.confirmar.error}
                    onCancelar={fecharPrevia}
                    onConfirmar={async (confirmoConta) => {
                      try {
                        const imp = await mut.confirmar.mutateAsync({ previaId: previa.previaId, confirmoConta });
                        toast.success(imp.gravados > 0 ? `Importação confirmada: ${imp.gravados} dias gravados.` : "Nada novo: estes dias já estavam importados.");
                        fecharPrevia();
                      } catch {
                        // a prévia expirada, já usada ou desatualizada aparece no erro; "Cancelar" volta ao envio
                      }
                    }}
                  />
                ) : (
                  <EnvioArquivos
                    key={envio}
                    lendo={mut.previa.isPending}
                    erro={mut.previa.error}
                    onLer={(arquivos) =>
                      mut.previa.mutate(arquivos, {
                        onSuccess: (p) => {
                          mut.confirmar.reset();
                          setPrevia(p);
                        },
                      })
                    }
                  />
                )}
              </CardContent>
            </Card>
          )}

          <Card className="shadow-card" role="region" aria-labelledby="studio-importacoes">
            <CardHeader>
              <CardTitle>
                <h2 id="studio-importacoes">Importações</h2>
              </CardTitle>
              <CardDescription>Desfazer tira os dias do analytics e da exportação; eles continuam guardados.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {mut.desfazer.error ? <ApiErrorAlert error={mut.desfazer.error} onReload={() => void lista.refetch()} /> : null}
              {lista.isError ? (
                <ApiErrorAlert error={lista.error} />
              ) : lista.isPending ? (
                <Skeleton className="h-24 w-full" />
              ) : (
                <ListaImportacoes importacoes={lista.data.items} podeDesfazer={ehDono} desfazendo={desfazendo} onDesfazer={desfazer} />
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="h-fit min-w-0 shadow-card" role="region" aria-labelledby="studio-cobertura">
          <CardHeader>
            <CardTitle>
              <h2 id="studio-cobertura">Cobertura</h2>
            </CardTitle>
            <CardDescription>De que dia a que dia há dado importado, desde quando há coleta e onde faltam dias.</CardDescription>
          </CardHeader>
          <CardContent>
            {cobertura.isError ? (
              <ApiErrorAlert error={cobertura.error} />
            ) : cobertura.isPending ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <CoberturaBarras cobertura={cobertura.data} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
