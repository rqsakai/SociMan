/*
 * /app/metricas (spec 019): o analytics de decisão, carregado sob demanda (React.lazy em App.tsx;
 * o ECharts vem no chunk `graficos`, fora do precache do PWA).
 *
 * - Filtros globais (período, perfil, conta, rede, medida do post) e a aba moram na URL
 *   (`?aba=visao-geral|quando-postar|publico|o-que-funciona|curvas|contas|funil|mercado|alertas`).
 *   A aba Público (spec 022) mostra os dados importados do TikTok Studio.
 * - Cabeçalho: o estado da coleta da conta filtrada e "Exportar" (só dono), herdados da 016.
 * - Visão geral leva o ranking da 016; Contas, a evolução da conta. O detalhe do vídeo
 *   (/app/metricas/videos/:id) não muda.
 * Tudo é leitura: nada aqui publica, aprova, agenda ou altera dado (FR-009).
 */
import { Download } from "lucide-react";
import { useState } from "react";
import { FiltrosGlobais, TrilhaConta } from "@/components/analytics/FiltrosGlobais";
import { ColetaStatus } from "@/components/metricas/ColetaStatus";
import { ExportarDialog } from "@/components/metricas/ExportarDialog";
import { PageHeading } from "@/components/PageHeading";
import { usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ABAS_ANALYTICS, abaLabel, useFiltroAnalytics, type AbaAnalytics } from "@/lib/analytics";
import { useEhDono } from "@/lib/conteudos";
import { useMetricasConta } from "@/lib/metricas";
import { Alertas, ContadorAlertas } from "./abas/Alertas";
import { Contas } from "./abas/Contas";
import { Curvas } from "./abas/Curvas";
import { Funil } from "./abas/Funil";
import { Mercado } from "./abas/Mercado";
import { OQueFunciona } from "./abas/OQueFunciona";
import { Publico } from "./abas/Publico";
import { QuandoPostar } from "./abas/QuandoPostar";
import { VisaoGeral } from "./abas/VisaoGeral";

const CONTEUDO: Record<AbaAnalytics, typeof VisaoGeral> = {
  "visao-geral": VisaoGeral,
  "quando-postar": QuandoPostar,
  publico: Publico,
  "o-que-funciona": OQueFunciona,
  curvas: Curvas,
  contas: Contas,
  funil: Funil,
  mercado: Mercado,
  alertas: Alertas,
};

// Estado da coleta da conta filtrada (a aba Contas já mostra o dela dentro da evolução).
function ColetaDaConta({ contaId }: { contaId: string }) {
  const dados = useMetricasConta(contaId, {});
  return <ColetaStatus coleta={dados.data?.coleta} />;
}

export default function Analytics() {
  usePageMeta({ title: "Métricas" });
  const dono = useEhDono();
  const estado = useFiltroAnalytics();
  const [exportar, setExportar] = useState(false);
  const { aba, filtro } = estado;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeading
          title="Métricas"
          description="O que postar, quando postar, de onde cortar e o que está dando errado, a partir das métricas coletadas pelo SociMan. Horários em São Paulo."
        />
        {dono && (
          <Button type="button" variant="outline" onClick={() => setExportar(true)}>
            <Download aria-hidden="true" />
            Exportar
          </Button>
        )}
      </div>

      {filtro.contaId && aba !== "contas" && <ColetaDaConta contaId={filtro.contaId} />}

      <FiltrosGlobais estado={estado} />
      <TrilhaConta estado={estado} />

      <Tabs value={aba} onValueChange={(v) => estado.setAba(v as AbaAnalytics)} className="gap-4">
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <TabsList aria-label="Seções do analytics">
            {ABAS_ANALYTICS.map((a) => (
              <TabsTrigger key={a} value={a}>
                {abaLabel[a]}
                {a === "alertas" && <ContadorAlertas filtro={filtro} />}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {ABAS_ANALYTICS.map((a) => {
          const Conteudo = CONTEUDO[a];
          return (
            <TabsContent key={a} value={a}>
              {a === aba && <Conteudo estado={estado} />}
            </TabsContent>
          );
        })}
      </Tabs>

      <p className="text-xs text-muted-foreground">
        A TikTok só informa vídeos públicos e números acumulados; vídeos privados ou "só amigos" não são coletados. Horários em São Paulo.
      </p>

      {dono && exportar && <ExportarDialog open onOpenChange={setExportar} perfilId={filtro.perfilId ?? ""} contaId={filtro.contaId ?? ""} />}
    </div>
  );
}
