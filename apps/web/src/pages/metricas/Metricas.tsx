/*
 * /app/metricas (spec 016, US4 e US5): o desempenho dos vídeos e das contas TikTok.
 *
 * - Aba "Ranking": vídeos da conta ou do perfil, ordenáveis por views em 24 h e 7 dias,
 *   engajamento e velocidade, filtráveis por período de publicação, perfil, conta e origem.
 * - Aba "Contas": evolução de seguidores e curtidas de uma conta, com os vídeos marcados e o
 *   estado da coleta.
 * - "Exportar" (só dono): o dataset em CSV ou JSON Lines, num ZIP.
 * A aba e os filtros moram na URL. Tudo é leitura: nada aqui publica ou altera posts.
 */
import { Download } from "lucide-react";
import { useState } from "react";
import { useFiltroUrl } from "@/components/conteudos/FiltrosConteudos";
import { ContaMetricas } from "@/components/metricas/ContaMetricas";
import { ExportarDialog } from "@/components/metricas/ExportarDialog";
import { RankingTable } from "@/components/metricas/RankingTable";
import { PageHeading } from "@/components/PageHeading";
import { usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useEhDono } from "@/lib/conteudos";

export default function Metricas() {
  usePageMeta({ title: "Métricas" });
  const dono = useEhDono();
  const [params, set] = useFiltroUrl();
  const aba = params.get("aba") === "contas" ? "contas" : "ranking";
  const [exportar, setExportar] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeading
          title="Métricas"
          description="Visualizações, curtidas, comentários e compartilhamentos dos vídeos públicos e a evolução das contas TikTok, coletados pelo SociMan."
        />
        {dono && (
          <Button type="button" variant="outline" onClick={() => setExportar(true)}>
            <Download aria-hidden="true" />
            Exportar
          </Button>
        )}
      </div>

      <Tabs value={aba} onValueChange={(v) => set({ aba: v === "ranking" ? null : v })} className="gap-4">
        <TabsList aria-label="Métricas">
          <TabsTrigger value="ranking">Ranking</TabsTrigger>
          <TabsTrigger value="contas">Contas</TabsTrigger>
        </TabsList>
        <TabsContent value="ranking">
          <RankingTable />
        </TabsContent>
        <TabsContent value="contas">
          <ContaMetricas />
        </TabsContent>
      </Tabs>

      <p className="text-xs text-muted-foreground">
        A TikTok só informa vídeos públicos e números acumulados; vídeos privados ou "só amigos" não são coletados. Horários em São Paulo.
      </p>

      {dono && exportar && <ExportarDialog open onOpenChange={setExportar} perfilId={params.get("perfil") ?? ""} contaId={params.get("conta") ?? ""} />}
    </div>
  );
}
