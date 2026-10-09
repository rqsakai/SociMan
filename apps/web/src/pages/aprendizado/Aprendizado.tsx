/*
 * /app/aprendizado?perfil=… (spec 023, R12; página própria desde a 024, R10): aprender com o
 * desempenho do perfil. Carregada sob demanda (React.lazy em App.tsx), porque os cards usam o
 * ECharts da 019 (chunk `graficos`).
 *
 * - Perfil na URL (`?perfil=`). Sem ele, abre no último perfil lembrado neste aparelho ou no único
 *   perfil; sem nenhum perfil, o vazio com "Novo perfil". O link antigo /app/perfis/:id/aprendizado
 *   redireciona para cá (App.tsx).
 * - Abas na URL (`?aba=analise|temas|recomendacoes|diagnostico|ia`, padrão "analise"), com a conta e
 *   a medida do post (`?conta=…&medida=h1|h24|d7`, padrão 24 h fora da URL), na FilterBar.
 * - A estatística é calculada pela API na leitura; nada aqui publica, agenda nem aprova (princípio I).
 * - Escritas (temas, classificações, decisões, preferências, análises da IA, conferências) só para o
 *   dono humano; o membro vê tudo sem botões e sem custo.
 */
import { useQuery } from "@tanstack/react-query";
import { Lightbulb, Plus } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { FilterBar, type FiltroAtivo } from "@/components/data-table/FilterBar";
import { PageHeading } from "@/components/PageHeading";
import { EmptyState, Page, usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import {
  ABAS_APRENDIZADO,
  abaAprendizadoLabel,
  lembrarPerfil,
  MEDIDAS_APRENDIZADO,
  medidaAprendizadoLabel,
  perfilLembrado,
  useFiltroAprendizado,
  type AbaAprendizado,
  type EstadoFiltroAprendizado,
} from "@/lib/aprendizado";
import { useFiltroUrl } from "@/lib/filtros";
import { perfilKey } from "@/lib/perfis";
import { usePerfisAtivos } from "@/lib/usePerfis";
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
  const [params, set] = useFiltroUrl();
  const id = params.get("perfil") ?? "";
  const perfis = usePerfisAtivos();
  usePageMeta({ title: "Aprendizado" });

  // sem ?perfil=: o último lembrado (se ainda ativo) ou o único perfil
  const lista = perfis.data;
  useEffect(() => {
    if (id || !lista) return;
    const lembrado = perfilLembrado();
    const escolhido = lista.find((p) => p.id === lembrado)?.id ?? (lista.length === 1 ? lista[0]!.id : null);
    if (escolhido) set({ perfil: escolhido }, { replace: true });
  }, [id, lista, set]);

  useEffect(() => {
    if (id) lembrarPerfil(id);
  }, [id]);

  if (!id) {
    if (perfis.isError) return <ApiErrorAlert error={perfis.error} />;
    if (!lista) return <Skeleton className="h-96 w-full" />;
    return (
      <Page>
        <PageHeading title="Aprendizado" description="Por que um post rendeu, que assuntos ampliar ou cortar e o que conferir quando a rede não entrega." />
        {lista.length === 0 ? (
          <EmptyState
            icone={Lightbulb}
            titulo="Nenhum perfil ainda"
            descricao="O aprendizado é por perfil: crie um perfil e conecte as contas para começar."
            acao={
              <Button asChild size="sm">
                <Link to="/app/perfis/novo">
                  <Plus aria-hidden="true" />
                  Novo perfil
                </Link>
              </Button>
            }
          />
        ) : (
          <section aria-label="Filtros do aprendizado" className="rounded-xl bg-card p-4 shadow-card">
            <FilterBar principais={<SeletorPerfil valor="" perfis={lista} onChange={(p) => set({ perfil: p || null })} />} />
          </section>
        )}
      </Page>
    );
  }
  return <AprendizadoDoPerfil key={id} id={id} perfis={lista} onPerfil={(p) => set({ perfil: p, conta: null })} />;
}

function SeletorPerfil({ valor, perfis, onChange, extra }: { valor: string; perfis: Perfil[]; onChange: (id: string) => void; extra?: Perfil }) {
  const opcoes = extra && !perfis.some((p) => p.id === extra.id) ? [...perfis, extra] : perfis;
  return (
    <Field label="Perfil" className="w-full sm:w-56">
      {({ id: fid }) => (
        <NativeSelect id={fid} value={valor} onChange={(e) => onChange(e.target.value)}>
          {!valor && <option value="">Escolha o perfil…</option>}
          {opcoes.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );
}

function AprendizadoDoPerfil({ id, perfis, onPerfil }: { id: string; perfis: Perfil[] | undefined; onPerfil: (id: string) => void }) {
  const detalhe = useQuery({ queryKey: perfilKey(id), queryFn: () => api.perfis.get(id) });
  const estado = useFiltroAprendizado();
  usePageMeta({
    title: "Aprendizado",
    breadcrumbs: detalhe.data ? [{ label: detalhe.data.perfil.name, to: `/app/perfis/${id}` }] : [],
  });

  if (detalhe.isPending) return <Skeleton className="h-96 w-full" />;
  if (detalhe.isError) return <ApiErrorAlert error={detalhe.error} />;
  const { perfil } = detalhe.data;
  const contas = detalhe.data.contas.filter((c) => !c.archived);
  const { aba, filtro } = estado;
  const comMedida = COM_MEDIDA.includes(aba);
  const conta = contas.find((c) => c.id === filtro.contaId);

  const ativos: FiltroAtivo[] = [
    ...(conta ? [{ chave: "conta", rotulo: "Conta", valor: `@${conta.handle.replace(/^@/, "")}`, limpar: () => estado.set({ conta: null }) }] : []),
    ...(comMedida && filtro.medida !== "h24"
      ? [{ chave: "medida", rotulo: "Medida", valor: medidaAprendizadoLabel[filtro.medida], limpar: () => estado.set({ medida: null }) }]
      : []),
  ];

  return (
    <Page>
      <PageHeading
        title={`Aprendizado: ${perfil.name}`}
        description="Por que um post rendeu, que assuntos ampliar ou cortar e o que conferir quando a rede não entrega. Tudo é sugestão: só muda algo quando o dono aceita. Horários em São Paulo."
      />

      <section aria-label="Filtros do aprendizado" className="rounded-xl bg-card p-4 shadow-card">
        <FilterBar
          principais={
            <>
              <SeletorPerfil valor={perfil.id} perfis={perfis ?? []} extra={perfil} onChange={onPerfil} />
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
              {comMedida && (
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
            </>
          }
          ativos={ativos}
          onLimpar={() => estado.set({ conta: null, medida: null })}
        />
      </section>
      <Tabs value={aba} onValueChange={(v) => estado.setAba(v as AbaAprendizado)} className="min-w-0">
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
    </Page>
  );
}
