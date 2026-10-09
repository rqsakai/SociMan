/*
 * Filtros do mercado (spec 026, FR-043/FR-051) na <FilterBar> (spec 024): período (7/30/90 d ou
 * personalizado), perfil (só restringe aos interesses e categorias dele), "só acompanhados" e a
 * busca; em "Mais filtros": origem do interesse. Tudo na URL; os padrões somem dela.
 */
import { useState } from "react";
import { FilterBar, type FiltroAtivo } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { ATALHOS_MERCADO, MAX_DIAS_MERCADO, ORIGENS_MERCADO, origemMercadoLabel, type EstadoFiltroMercado } from "@/lib/mercado";
import { addDays, formatDateKey, localDateKey } from "@/lib/tz";
import { usePerfisAtivos } from "@/lib/usePerfis";

export function FiltrosMercado({ estado }: { estado: EstadoFiltroMercado }) {
  const { filtro, periodoPadrao, set, setPeriodo } = estado;
  const perfis = usePerfisAtivos();
  const [personalizado, setPersonalizado] = useState(false);
  const hoje = localDateKey(new Date());
  const dias = Math.round((Date.parse(`${filtro.ate}T00:00:00Z`) - Date.parse(`${filtro.de}T00:00:00Z`)) / 86_400_000) + 1;
  const atalho = filtro.ate === hoje ? ATALHOS_MERCADO.find((a) => a.dias === dias)?.id : undefined;
  const mostrarDatas = personalizado || !atalho;

  const ativos: FiltroAtivo[] = [
    ...(!periodoPadrao
      ? [
          {
            chave: "periodo",
            rotulo: "Período",
            valor: atalho ? ATALHOS_MERCADO.find((a) => a.id === atalho)!.label : `${formatDateKey(filtro.de)} a ${formatDateKey(filtro.ate)}`,
            limpar: () => {
              setPersonalizado(false);
              setPeriodo(addDays(hoje, -29), hoje);
            },
          },
        ]
      : []),
    ...(filtro.perfilId ? [{ chave: "perfil", rotulo: "Perfil", valor: perfis.data?.find((p) => p.id === filtro.perfilId)?.name ?? "…", limpar: () => set({ perfil: null, pagina: null }) }] : []),
    ...(filtro.soAcompanhados ? [{ chave: "acompanhados", rotulo: "Só acompanhados", valor: "sim", limpar: () => set({ acompanhados: null, pagina: null }) }] : []),
    ...(filtro.origem ? [{ chave: "origem", rotulo: "Origem", valor: origemMercadoLabel[filtro.origem as keyof typeof origemMercadoLabel] ?? filtro.origem, limpar: () => set({ origem: null, pagina: null }), mais: true }] : []),
  ];

  return (
    <div className="rounded-xl bg-card p-4 text-card-foreground shadow-card">
      <FilterBar
        busca={{ valor: filtro.q ?? "", onChange: (v) => set({ q: v || null, pagina: null }, { replace: true }), rotulo: "Buscar produto", placeholder: "Título ou id do produto" }}
        principais={
          <>
            <fieldset className="w-full min-w-0 space-y-1.5 sm:w-auto">
              <legend className="text-sm font-medium">Período</legend>
              <div className="flex flex-wrap gap-1" role="group" aria-label="Atalhos de período">
                {ATALHOS_MERCADO.map((a) => {
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
                        setPeriodo(addDays(hoje, -(a.dias - 1)), hoje);
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
              <p className="text-xs text-muted-foreground">Até {MAX_DIAS_MERCADO} dias, no fuso do mercado.</p>
            </fieldset>
            <Field label="Perfil" className="w-full sm:w-48">
              {({ id }) => (
                <NativeSelect id={id} value={filtro.perfilId ?? ""} onChange={(e) => set({ perfil: e.target.value || null, pagina: null })}>
                  <option value="">Todos os perfis</option>
                  {perfis.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" className="size-4 accent-primary" checked={filtro.soAcompanhados} onChange={(e) => set({ acompanhados: e.target.checked ? "1" : null, pagina: null })} />
              Só acompanhados
            </label>
          </>
        }
        mais={
          <Field label="Origem do acompanhamento" className="w-full sm:w-56">
            {({ id }) => (
              <NativeSelect id={id} value={filtro.origem ?? ""} onChange={(e) => set({ origem: e.target.value || null, pagina: null })}>
                <option value="">Todas</option>
                {ORIGENS_MERCADO.map((o) => (
                  <option key={o} value={o}>
                    {origemMercadoLabel[o]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        }
        ativos={ativos}
        onLimpar={() => {
          setPersonalizado(false);
          set({ de: null, ate: null, perfil: null, acompanhados: null, origem: null, q: null, pagina: null });
        }}
      />
    </div>
  );
}
