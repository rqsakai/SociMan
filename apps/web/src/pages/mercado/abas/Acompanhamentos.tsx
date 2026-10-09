/*
 * Aba "Acompanhamentos" (spec 026, US4): os interesses de todos os perfis, com filtro por perfil,
 * origem e situação (na URL com o prefixo `ac`), e as ações pausar / reativar / encerrar.
 */
import { InteressesTabela } from "@/components/mercado/InteressesTabela";
import { EmptyState, HeaderCard } from "@/components/shell";
import { Field, NativeSelect } from "@/components/ui/field";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { useFiltroUrl } from "@/lib/filtros";
import { origemMercadoLabel, ORIGENS_MERCADO, useInteressesTodos, type EstadoFiltroMercado, type MercadoInteresse } from "@/lib/mercado";
import { usePerfisAtivos } from "@/lib/usePerfis";

export function Acompanhamentos({ estado }: { estado: EstadoFiltroMercado }) {
  const [params, set] = useFiltroUrl("ac");
  const perfis = usePerfisAtivos();
  const perfilId = params.get("perfil") ?? estado.filtro.perfilId ?? "";
  const origem = params.get("origem") ?? "";
  const situacao = params.get("situacao") ?? "";
  const lista = useInteressesTodos({
    ...(perfilId ? { perfilId } : {}),
    ...(origem ? { origem: origem as MercadoInteresse["origem"] } : {}),
    ...(situacao ? { situacao: situacao as MercadoInteresse["situacao"] } : {}),
  });

  return (
    <HeaderCard
      title="Acompanhamentos"
      description={lista.data ? `${lista.data.total} acompanhamento${lista.data.total === 1 ? "" : "s"} nos perfis` : "Carregando…"}
      actions={
        <div className="flex flex-wrap gap-2">
          <Field label="Perfil" className="w-44">
            {({ id }) => (
              <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value || null })}>
                <option value="">Todos</option>
                {perfis.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Origem" className="w-44">
            {({ id }) => (
              <NativeSelect id={id} value={origem} onChange={(e) => set({ origem: e.target.value || null })}>
                <option value="">Todas</option>
                {ORIGENS_MERCADO.map((o) => (
                  <option key={o} value={o}>
                    {origemMercadoLabel[o]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Situação" className="w-36">
            {({ id }) => (
              <NativeSelect id={id} value={situacao} onChange={(e) => set({ situacao: e.target.value || null })}>
                <option value="">Todas</option>
                <option value="ativo">Ativo</option>
                <option value="pausado">Pausado</option>
                <option value="encerrado">Encerrado</option>
              </NativeSelect>
            )}
          </Field>
        </div>
      }
    >
      {lista.isError && <ApiErrorAlert error={lista.error} />}
      <InteressesTabela
        itens={lista.data?.itens}
        loading={lista.isPending}
        perfis={perfis.data}
        mostrarPerfil
        empty={<EmptyState titulo="Nenhum acompanhamento" descricao="Cada perfil escolhe o que acompanhar na aba Mercado do perfil: link, categorias do nicho ou lojas seguidas." />}
      />
    </HeaderCard>
  );
}
