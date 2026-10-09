/*
 * Aba "Diagnóstico" (spec 023, US5; FR-048 a FR-050). Por conta: "distribuição travada" quando mais
 * de 60% dos posts medidos ficaram estagnados, os sinais encontrados (com o número que os sustenta) e
 * o checklist do que conferir no app da rede. Cada post com sinal tem o link para o detalhe, onde o
 * dono marca o que conferiu. Só leitura, mais as conferências do dono.
 */
import { ClipboardCheck } from "lucide-react";
import { ChecklistApp, SinaisDistribuicao } from "@/components/aprendizado/SinaisDistribuicao";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { EmptyState, HeaderCard, Page } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useDiagnostico } from "@/lib/aprendizado";
import { formatNumero } from "@/lib/metricas";
import type { AbaProps } from "../Aprendizado";

export function Diagnostico({ perfil, estado }: AbaProps) {
  const diag = useDiagnostico(perfil.id, estado.filtro);

  if (diag.isError) return <ApiErrorAlert error={diag.error} />;
  if (diag.isPending) return <Skeleton className="h-96 w-full" />;
  const d = diag.data;

  return (
    <Page>
      {d.contas.length === 0 && (
        <EmptyState titulo="Nenhuma conta com posts medidos neste recorte." />
      )}
      {d.contas.map((c) => {
        const daConta = c.sinais.filter((s) => s.alvo === "conta");
        const dosPosts = c.sinais.filter((s) => s.alvo === "post");
        return (
          <HeaderCard
            key={c.conta.id}
            title={c.conta.rotulo}
            tone={c.travada ? "warning" : "primary"}
            description={`${formatNumero(c.estagnados)} de ${formatNumero(c.medidos)} posts medidos estagnados (0 a 1 view)`}
            actions={c.travada ? <Badge variant="secondary">distribuição travada</Badge> : undefined}
          >
            <div className="flex flex-col gap-4 pb-2" data-conta={c.conta.rotulo}>
              {c.travada && (
                <p className="text-sm">
                  A maioria dos posts desta conta não foi entregue pela rede. Antes de concluir algo sobre assunto ou hashtag, confira os sinais abaixo e o app.
                </p>
              )}
              <section aria-label={`Sinais da conta ${c.conta.rotulo}`} className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Sinais da conta</h3>
                <SinaisDistribuicao sinais={daConta} />
              </section>
              {dosPosts.length > 0 && (
                <section aria-label={`Sinais dos posts de ${c.conta.rotulo}`} className="flex flex-col gap-2">
                  <h3 className="text-sm font-semibold">Sinais dos posts</h3>
                  <SinaisDistribuicao sinais={dosPosts} comLinkPost />
                </section>
              )}
            </div>
          </HeaderCard>
        );
      })}

      <HeaderCard title="O que conferir no app" description="A rede não informa estes motivos pela API. Abra o post no app e marque o que conferiu no detalhe do vídeo.">
        <div className="flex items-start gap-3 pb-2">
          <ClipboardCheck className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <ChecklistApp checklist={d.checklist} />
        </div>
      </HeaderCard>
    </Page>
  );
}
