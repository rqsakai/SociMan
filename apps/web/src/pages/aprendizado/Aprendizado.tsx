/*
 * /app/perfis/:id/aprendizado (spec 023, R12): aprender com o desempenho do perfil. Carregada sob
 * demanda (React.lazy em App.tsx), porque os cards usam o ECharts da 019 (chunk `graficos`).
 *
 * - Abas na URL (`?aba=analise|temas|recomendacoes|diagnostico|ia`, padrão "analise"), com a conta e
 *   a medida do post (`?conta=…&medida=h1|h24|d7`, padrão 24 h fora da URL).
 * - A estatística é calculada pela API na leitura; nada aqui publica, agenda nem aprova (princípio I).
 * - Escritas (temas, classificações, decisões, preferências, análises da IA, conferências) só para o
 *   dono humano; o membro vê tudo sem botões e sem custo.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PageHeading } from "@/components/PageHeading";
import { usePageMeta } from "@/components/shell";
import { Field, NativeSelect } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import {
  ABAS_APRENDIZADO,
  abaAprendizadoLabel,
  MEDIDAS_APRENDIZADO,
  medidaAprendizadoLabel,
  useFiltroAprendizado,
  type AbaAprendizado,
  type EstadoFiltroAprendizado,
} from "@/lib/aprendizado";
import { perfilKey } from "@/lib/perfis";
import type { Conta, Perfil } from "@sociman/contract";
import { Analise } from "./abas/Analise";
import { AnalisesIa } from "./abas/AnalisesIa";
import { Diagnostico } from "./abas/Diagnostico";
import { Recomendacoes } from "./abas/Recomendacoes";
import { Temas } from "./abas/Temas";

export interface AbaProps {
  perfil: Perfil;
  contas: Conta[];
  estado: EstadoFiltroAprendizado;
}

const CONTEUDO: Record<AbaAprendizado, (p: AbaProps) => React.ReactNode> = {
  analise: Analise,
  temas: Temas,
  recomendacoes: Recomendacoes,
  diagnostico: Diagnostico,
  ia: AnalisesIa,
};

// As abas que usam o filtro de período e de medida (Temas lista classificações por conta).
const COM_MEDIDA: AbaAprendizado[] = ["analise", "recomendacoes", "ia"];

export default function Aprendizado() {
  const { id = "" } = useParams();
  const detalhe = useQuery({ queryKey: perfilKey(id), queryFn: () => api.perfis.get(id) });
  const estado = useFiltroAprendizado();
  usePageMeta({
    title: "Aprendizado",
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(detalhe.data ? [{ label: detalhe.data.perfil.name, to: `/app/perfis/${id}` }] : []),
    ],
  });

  if (detalhe.isPending) return <Skeleton className="h-96 w-full" />;
  if (detalhe.isError) return <ApiErrorAlert error={detalhe.error} />;
  const { perfil } = detalhe.data;
  const contas = detalhe.data.contas.filter((c) => !c.archived);
  const { aba, filtro } = estado;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Link to={`/app/perfis/${perfil.id}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden="true" />
        {perfil.name}
      </Link>
      <PageHeading
        title={`Aprendizado: ${perfil.name}`}
        description="Por que um post rendeu, que assuntos ampliar ou cortar e o que conferir quando a rede não entrega. Tudo é sugestão: só muda algo quando o dono aceita. Horários em São Paulo."
      />

      <section aria-label="Filtros do aprendizado" className="flex flex-wrap items-end gap-3 rounded-xl bg-card p-4 shadow-card">
        <Field label="Conta" className="w-full sm:w-64">
          {({ id: fid }) => (
            <NativeSelect id={fid} value={filtro.contaId ?? ""} onChange={(e) => estado.set({ conta: e.target.value || null })}>
              <option value="">Todas as contas do perfil</option>
              {contas.map((c) => (
                <option key={c.id} value={c.id}>
                  @{c.handle.replace(/^@/, "")}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {COM_MEDIDA.includes(aba) && (
          <Field label="Medida do post" className="w-full sm:w-48">
            {({ id: fid }) => (
              <NativeSelect id={fid} value={filtro.medida} onChange={(e) => estado.set({ medida: e.target.value === "h24" ? null : e.target.value })}>
                {MEDIDAS_APRENDIZADO.map((m) => (
                  <option key={m} value={m}>
                    {medidaAprendizadoLabel[m]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        )}
      </section>

      <Tabs value={aba} onValueChange={(v) => estado.setAba(v as AbaAprendizado)} className="min-w-0 gap-4">
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <TabsList aria-label="Seções do aprendizado">
            {ABAS_APRENDIZADO.map((a) => (
              <TabsTrigger key={a} value={a}>
                {abaAprendizadoLabel[a]}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {ABAS_APRENDIZADO.map((a) => {
          const Conteudo = CONTEUDO[a];
          return (
            <TabsContent key={a} value={a} className="min-w-0">
              {a === aba && <Conteudo perfil={perfil} contas={contas} estado={estado} />}
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  );
}
