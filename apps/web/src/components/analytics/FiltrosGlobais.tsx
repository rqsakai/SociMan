/*
 * Filtros globais do analytics (spec 019, FR-002/FR-003/FR-004a), numa linha acima das abas e em
 * coluna no celular. Valem para todas as abas e moram na URL (`de`, `ate`, `perfil`, `conta`,
 * `rede`, `medida`); os padrões somem dela.
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
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ATALHOS, MAX_DIAS, MEDIDAS, REDES, medidaLabel, type EstadoFiltroAnalytics, type Medida } from "@/lib/analytics";
import { api } from "@/lib/api";
import { perfilKey, platformLabel } from "@/lib/perfis";
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

  return (
    <div className="flex flex-col gap-3 rounded-xl bg-card p-4 text-card-foreground shadow-card lg:flex-row lg:flex-wrap lg:items-end">
      <fieldset className="min-w-0 space-y-1.5">
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
            <Input type="date" aria-label="Período de" value={filtro.de} max={filtro.ate} onChange={(e) => e.target.value && setPeriodo(e.target.value, filtro.ate)} className="w-auto" />
            <span className="text-sm text-muted-foreground">a</span>
            <Input type="date" aria-label="Período até" value={filtro.ate} min={filtro.de} onChange={(e) => e.target.value && setPeriodo(filtro.de, e.target.value)} className="w-auto" />
          </div>
        )}
        {periodoInvalido && (
          <p role="alert" className="text-xs text-destructive">
            Período inválido (início depois do fim ou mais de {MAX_DIAS} dias); mostrando os últimos 7 dias.
          </p>
        )}
      </fieldset>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:flex lg:flex-wrap lg:items-end">
        <Field label="Perfil" className="lg:w-48">
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
        <Field label="Conta" className="lg:w-48">
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
        <Field label="Rede" className="lg:w-40">
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
        <Field label="Medida do post" className="lg:w-44">
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
      </div>
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
