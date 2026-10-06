/*
 * Filtros da lista de Conteúdos (spec 014, US1; R10). Tudo mora na URL (voltar, recarregar e
 * compartilhar o link mantêm a lista): perfil, conta (as do perfil escolhido), rede, estado por
 * conta (ou "sem conta"), origem, período agendado, período de criação, busca e "arquivados".
 * Os <select> são nativos (os e2e usam selectOption).
 */
import type { Platform } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { estadoEfetivoLabel, filtroParams, origemLabel, type EstadoEfetivo, type Origem } from "@/lib/conteudos";
import { contaPlatformText, perfilKey, platformLabel } from "@/lib/perfis";
import { usePerfisAtivos } from "@/lib/usePerfis";

// Cada filtro escolhido empilha no histórico ("Voltar" volta ao filtro anterior); só a busca
// digitada substitui a entrada (`replace`), para não empilhar a cada pausa. Vazio tira o parâmetro.
export function useFiltroUrl() {
  const [params, setParams] = useSearchParams();
  const set = (patch: Record<string, string | null>, opts: { replace?: boolean } = {}) =>
    setParams(
      // parte da URL do momento, não dos params do render: no react-router 7 a navegação vai num
      // transition, e dois patches seguidos (ex.: período e logo o perfil) apagariam um ao outro
      () => {
        const next = new URLSearchParams(window.location.search);
        for (const [k, v] of Object.entries(patch)) {
          if (v) next.set(k, v);
          else next.delete(k);
        }
        return next;
      },
      { replace: Boolean(opts.replace) },
    );
  return [params, set] as const;
}

export function FiltrosConteudos() {
  const [params, set] = useFiltroUrl();
  const perfis = usePerfisAtivos();
  const perfilId = params.get("perfil") ?? "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: Boolean(perfilId) });
  const contas = perfil.data?.contas.filter((c) => !c.archived) ?? [];

  // Busca: digitação local, grava na URL depois de 300 ms parado.
  const qUrl = params.get("q") ?? "";
  const [q, setQ] = useState(qUrl);
  useEffect(() => setQ(qUrl), [qUrl]);
  useEffect(() => {
    if (q === qUrl) return;
    const t = setTimeout(() => set({ q: q.trim() ? q.slice(0, 100) : null }, { replace: true }), 300);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const algum = filtroParams.some((k) => k !== "ordem" && params.has(k));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            type="search"
            aria-label="Buscar"
            placeholder="Buscar nos títulos, ganchos…"
            value={q}
            maxLength={100}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
          />
        </div>
        <Field label="Perfil" className="w-full sm:w-52">
          {({ id }) => (
            <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value, conta: null })}>
              <option value="">Todos os perfis</option>
              {perfis.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Conta" className="w-full sm:w-52">
          {({ id }) => (
            <NativeSelect id={id} value={params.get("conta") ?? ""} disabled={!perfilId} onChange={(e) => set({ conta: e.target.value })}>
              <option value="">{perfilId ? "Todas as contas" : "Escolha um perfil"}</option>
              {contas.map((c) => (
                <option key={c.id} value={c.id}>
                  {contaPlatformText(c)} @{c.handle}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Rede" className="w-full sm:w-40">
          {({ id }) => (
            <NativeSelect id={id} value={params.get("plataforma") ?? ""} onChange={(e) => set({ plataforma: e.target.value })}>
              <option value="">Todas</option>
              {(Object.keys(platformLabel) as Platform[]).map((p) => (
                <option key={p} value={p}>
                  {platformLabel[p]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Estado" className="w-full sm:w-44">
          {({ id }) => (
            <NativeSelect id={id} value={params.get("estado") ?? ""} onChange={(e) => set({ estado: e.target.value })}>
              <option value="">Todos</option>
              <option value="sem_conta">Sem conta</option>
              {(Object.keys(estadoEfetivoLabel) as EstadoEfetivo[]).map((s) => (
                <option key={s} value={s}>
                  {estadoEfetivoLabel[s]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Origem" className="w-full sm:w-40">
          {({ id }) => (
            <NativeSelect id={id} value={params.get("origem") ?? ""} onChange={(e) => set({ origem: e.target.value })}>
              <option value="">Todas</option>
              {(Object.keys(origemLabel) as Origem[]).map((o) => (
                <option key={o} value={o}>
                  {origemLabel[o]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Periodo label="Agendado" de="agendadoDe" ate="agendadoAte" params={params} set={set} />
        <Periodo label="Criado" de="criadoDe" ate="criadoAte" params={params} set={set} />
        <Field label="Ordem" className="w-full sm:w-44">
          {({ id }) => (
            <NativeSelect id={id} value={params.get("ordem") ?? ""} onChange={(e) => set({ ordem: e.target.value })}>
              <option value="">Mais recentes</option>
              <option value="agenda">Próximos na agenda</option>
            </NativeSelect>
          )}
        </Field>
        <label className="flex h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={params.get("arquivados") === "1"}
            onChange={(e) => set({ arquivados: e.target.checked ? "1" : null })}
          />
          Arquivados
        </label>
        {algum && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-9"
            onClick={() => set(Object.fromEntries(filtroParams.map((k) => [k, null])))}
          >
            <X aria-hidden="true" />
            Limpar filtros
          </Button>
        )}
      </div>
    </div>
  );
}

function Periodo({
  label,
  de,
  ate,
  params,
  set,
}: {
  label: string;
  de: string;
  ate: string;
  params: URLSearchParams;
  set: (patch: Record<string, string | null>) => void;
}) {
  const vDe = params.get(de) ?? "";
  const vAte = params.get(ate) ?? "";
  const invertido = Boolean(vDe && vAte && vDe > vAte);
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{label}</legend>
      <div className="flex items-center gap-1.5">
        <Input type="date" aria-label={`${label} de`} value={vDe} onChange={(e) => set({ [de]: e.target.value })} className="w-auto" />
        <span className="text-sm text-muted-foreground">a</span>
        <Input
          type="date"
          aria-label={`${label} até`}
          value={vAte}
          aria-invalid={invertido}
          onChange={(e) => set({ [ate]: e.target.value })}
          className="w-auto"
        />
      </div>
      {invertido && (
        <p role="alert" className="text-xs text-destructive">
          A data inicial é depois da final.
        </p>
      )}
    </fieldset>
  );
}
