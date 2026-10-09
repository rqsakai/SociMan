/*
 * /app/mercado (spec 026, US1): o cockpit do TikTok Shop, carregado sob demanda (o ECharts vem
 * no chunk `graficos`). Abas na URL (`?aba=cockpit|produtos|rankings|lojas|acompanhamentos`),
 * filtros na URL (período padrão de 30 dias fora dela), tudo leitura. Horários e dias no fuso do
 * mercado (BR = São Paulo). Todo número derivado leva o selo "estimado".
 */
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ABAS_MERCADO, abaMercadoLabel, useFiltroMercado, type AbaMercado } from "@/lib/mercado";
import { Acompanhamentos } from "./abas/Acompanhamentos";
import { Cockpit } from "./abas/Cockpit";
import { FiltrosMercado } from "./abas/FiltrosMercado";
import { Lojas } from "./abas/Lojas";
import { Produtos } from "./abas/Produtos";
import { Rankings } from "./abas/Rankings";

const CONTEUDO: Record<AbaMercado, typeof Cockpit> = {
  cockpit: Cockpit,
  produtos: Produtos,
  rankings: Rankings,
  lojas: Lojas,
  acompanhamentos: Acompanhamentos,
};

export default function Mercado() {
  usePageMeta({ title: "Mercado de produtos" });
  const estado = useFiltroMercado();
  const { aba } = estado;

  return (
    <Page>
      <PageHeading
        title="Mercado de produtos"
        description="O que vende no TikTok Shop, coletado pelo SociMan em ritmo humano: preço, comissão, vendas, GMV e retorno por afiliado. Tudo estimado a partir de fotos diárias das páginas."
      />

      <FiltrosMercado estado={estado} />

      <Tabs value={aba} onValueChange={(v) => estado.setAba(v as AbaMercado)}>
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <TabsList aria-label="Seções do mercado">
            {ABAS_MERCADO.map((a) => (
              <TabsTrigger key={a} value={a}>
                {abaMercadoLabel[a]}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {ABAS_MERCADO.map((a) => {
          const Conteudo = CONTEUDO[a];
          return (
            <TabsContent key={a} value={a}>
              {a === aba && <Conteudo estado={estado} />}
            </TabsContent>
          );
        })}
      </Tabs>

      <p className="text-xs text-muted-foreground">
        Os números vêm de fotos diárias das páginas públicas e do Affiliate Center da conta do dono. Vendas e GMV são diferenças entre fotos e não
        descontam cupons nem devoluções; "coletando" é um produto com menos de duas fotos, e "amostra pequena", menos de 7 dias.
      </p>
    </Page>
  );
}
