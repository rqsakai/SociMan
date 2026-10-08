/*
 * Filtros globais do analytics (spec 019, FR-002/FR-003/FR-004a), na <FilterBar> (spec 024) acima
 * das abas. Valem para todas as abas e moram na URL (`de`, `ate`, `perfil`, `conta`, `rede`,
 * `medida`); os padrões somem dela. Principais: período, perfil e conta; em "Mais filtros": rede e
 * medida.
 *
 * - Período: atalhos 24 h, 7 d (padrão), 14 d, 30 d, 90 d e Tudo, ou "Personalizado" (duas datas).
 * - Perfil → Conta (as contas não arquivadas do perfil, da rede escolhida); trocar o perfil limpa a conta.
 * - Rede e "Medida do post" (views em 1 h, 24 h ou 7 d).
 * Com conta filtrada, a trilha "Contas → @conta" leva de volta à aba Contas sem a conta.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { FilterBar, type FiltroAtivo } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { ATALHOS, MAX_DIAS, MEDIDAS, REDES, medidaLabel, type EstadoFiltroAnalytics, type Medida } from "@/lib/analytics";
import { api } from "@/lib/api";
import { perfilKey, platformLabel } from "@/lib/perfis";
import { formatDateKey } from "@/lib/tz";
import { usePerfisAtivos } from "@/lib/usePerfis";

export function useContasDoPerfil(perfilId: string | undefined) {
  const perfil = useQuery({ queryKey: perfilKey(perfilId ?? ""), queryFn: () => api.perfis.get(perfilId!), enabled: Boolean(perfilId) });
  return perfil.data?.contas ?? [];
}

export function FiltrosGlobais({ estado }: { estado: EstadoFiltroAnalytics }) {
  const { filtro, atalho, periodoInvalido, set, setAtalho, setPeriodo } = estado;
  const perfis = usePerfisAtivos();
  const contas = useContasDoPerfil(filtro.perfilId).filter((c) => (!c.archived || c.id === filtro.contaId) && (!filtro.rede || c.platform === filtro.rede));
  const [personalizado, setPersonalizado] = useState(false);
  const mostrarDatas = personalizado || atalho === "personalizado";
  const conta = contas.find((c) => c.id === filtro.contaId);

  // etiquetas: o período só fora do padrão (7 d); a medida só fora do padrão (24 h). Os rótulos
  // curtos ("Medida") evitam que o "Remover filtro: …" case com o getByLabel do campo.
  const ativos: FiltroAtivo[] = [
    ...(atalho !== "7d"
      ? [
          {
            chave: "periodo",
            rotulo: "Período",
            valor: atalho === "personalizado" ? `${formatDateKey(filtro.de)} a ${formatDateKey(filtro.ate)}` : ATALHOS.find((a) => a.id === atalho)!.label,
            limpar: () => {
              setPersonalizado(false);
              setAtalho("7d");
            },
          },
        ]
      : []),
    ...(filtro.perfilId
      ? [{ chave: "perfil", rotulo: "Perfil", valor: perfis.data?.find((p) => p.id === filtro.perfilId)?.name ?? "…", limpar: () => set({ perfil: null, conta: null }) }]
      : []),
    ...(filtro.contaId ? [{ chave: "conta", rotulo: "Conta", valor: conta ? `@${conta.handle}` : "…", limpar: () => set({ conta: null }) }] : []),
    ...(filtro.rede ? [{ chave: "rede", rotulo: "Rede", valor: platformLabel[filtro.rede as (typeof REDES)[number]], limpar: () => set({ rede: null, conta: null }), mais: true }] : []),
    ...(filtro.medida !== "h24" ? [{ chave: "medida", rotulo: "Medida", valor: medidaLabel[filtro.medida], limpar: () => set({ medida: null }), mais: true }] : []),
  ];

  return (
    <div className="rounded-xl bg-card p-4 text-card-foreground shadow-card">
      <FilterBar
        principais={
          <>
            <fieldset className="w-full min-w-0 space-y-1.5 sm:w-auto">
              <legend className="text-sm font-medium">Período</legend>
              <div className="flex flex-wrap gap-1" role="group" aria-label="Atalhos de período">
                {ATALHOS.map((a) => {
                  const ativo = !mostrarDatas && atalho === a.id;
                  return (
                    <Button
                      key={a.id}
                      type="button"
                      size="sm"
                      variant={ativo ? "default" : "outline"}
                      aria-pressed={ativo}
                      onClick={() => {
                        setPersonalizado(false);
                        setAtalho(a.id);
                      }}
                    >
                      {a.label}
                    </Button>
                  );
                })}
                <Button type="button" size="sm" variant={mostrarDatas ? "default" : "outline"} aria-pressed={mostrarDatas} onClick={() => setPersonalizado(true)}>
                  Personalizado
                </Button>
              </div>
              {mostrarDatas && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <DateField aria-label="Período de" value={filtro.de} max={filtro.ate} onChange={(iso) => iso && setPeriodo(iso, filtro.ate)} className="w-40" />
                  <span className="text-sm text-muted-foreground">a</span>
                  <DateField aria-label="Período até" value={filtro.ate} min={filtro.de} onChange={(iso) => iso && setPeriodo(filtro.de, iso)} className="w-40" />
                </div>
              )}
              {periodoInvalido && (
                <p role="alert" className="text-xs text-destructive">
                  Período inválido (início depois do fim ou mais de {MAX_DIAS} dias); mostrando os últimos 7 dias.
                </p>
              )}
            </fieldset>
            <Field label="Perfil" className="w-full sm:w-48">
              {({ id }) => (
                <NativeSelect id={id} value={filtro.perfilId ?? ""} onChange={(e) => set({ perfil: e.target.value || null, conta: null })}>
                  <option value="">Todos os perfis</option>
                  {perfis.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Conta" className="w-full sm:w-48">
              {({ id }) => (
                <NativeSelect id={id} value={filtro.contaId ?? ""} disabled={!filtro.perfilId} onChange={(e) => set({ conta: e.target.value || null })}>
                  <option value="">{filtro.perfilId ? "Todas as contas" : "Escolha um perfil"}</option>
                  {contas.map((c) => (
                    <option key={c.id} value={c.id}>
                      @{c.handle} ({platformLabel[c.platform]}){c.archived ? " (arquivada)" : ""}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          </>
        }
        mais={
          <>
            <Field label="Rede">
              {({ id }) => (
                <NativeSelect id={id} value={filtro.rede ?? ""} onChange={(e) => set({ rede: e.target.value || null, conta: null })}>
                  <option value="">Todas as redes</option>
                  {REDES.map((r) => (
                    <option key={r} value={r}>
                      {platformLabel[r]}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Medida do post">
              {({ id }) => (
                <NativeSelect id={id} value={filtro.medida} onChange={(e) => set({ medida: (e.target.value as Medida) === "h24" ? null : e.target.value })}>
                  {MEDIDAS.map((m) => (
                    <option key={m} value={m}>
                      {medidaLabel[m]}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          </>
        }
        ativos={ativos}
        onLimpar={() => {
          setPersonalizado(false);
          set({ de: null, ate: null, perfil: null, conta: null, rede: null, medida: null });
        }}
      />
    </div>
  );
}

// "Contas → @conta": volta à aba Contas sem a conta, mantendo os outros filtros.
export function TrilhaConta({ estado }: { estado: EstadoFiltroAnalytics }) {
  const { search } = useLocation();
  const contas = useContasDoPerfil(estado.filtro.perfilId);
  const conta = contas.find((c) => c.id === estado.filtro.contaId);
  if (!estado.filtro.contaId) return null;
  const semConta = new URLSearchParams(search);
  semConta.delete("conta");
  semConta.set("aba", "contas");
  return (
    <nav aria-label="Trilha da conta" className="flex items-center gap-1 text-sm text-muted-foreground">
      <Link to={{ search: `?${semConta.toString()}` }} className="underline-offset-2 hover:underline">
        Contas
      </Link>
      <ChevronRight className="size-4" aria-hidden="true" />
      <span className="font-medium text-foreground" aria-current="page">
        {conta ? `@${conta.handle}` : "Conta"}
      </span>
    </nav>
  );
}
