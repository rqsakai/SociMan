import { Field, NativeSelect } from "@/components/ui/field";
import { nomePerfil, SEM_PERFIL, usePerfisTodos, type PerfilFiltro } from "@/lib/estudio";
import type { FiltroAtivo } from "@/components/data-table";

// Filtro "Perfil base" das listas do AI Studio (spec 029, T017): "Todos", "Sem perfil" e os perfis
// (os arquivados também, marcados). Vai na `FilterBar`; o estado é o `perfil` da URL.
export function PerfilBaseFiltro({
  valor,
  onChange,
  className = "w-full sm:w-52",
  rotulo = "Perfil base",
}: {
  valor: PerfilFiltro;
  onChange: (v: PerfilFiltro) => void;
  className?: string;
  // com dois filtros na mesma tela (fundo e marca d'água do kit), um rótulo próprio para cada
  rotulo?: string;
}) {
  const perfis = usePerfisTodos();
  const conhecido = valor === "todos" || valor === "sem" || perfis.data?.some((p) => p.id === valor);
  return (
    <Field label={rotulo} className={className}>
      {({ id }) => (
        <NativeSelect id={id} value={valor} onChange={(e) => onChange(e.target.value)} data-testid="filtro-perfil-base">
          <option value="todos">Todos</option>
          <option value="sem">{SEM_PERFIL}</option>
          {!conhecido && <option value={valor}>Perfil escolhido</option>}
          {perfis.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.archived ? `${p.name} (arquivado)` : p.name}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );
}

// A etiqueta removível do filtro, para o `ativos` da FilterBar.
export function usePerfilBaseAtivo(valor: PerfilFiltro, limpar: () => void): FiltroAtivo[] {
  const perfis = usePerfisTodos();
  if (valor === "todos") return [];
  return [{ chave: "perfil", rotulo: "Perfil base", valor: valor === "sem" ? SEM_PERFIL : nomePerfil(perfis.data, valor), limpar }];
}
