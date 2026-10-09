import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useMemo } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { AssetFilters } from "@/components/assets/AssetFilters";
import { AssetGrid } from "@/components/assets/AssetGrid";
import { NovoAssetMenu } from "@/components/assets/NovoAssetMenu";
import { EmptyState, HeaderCard } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { type AssetListFilters, type AssetTipo } from "@/lib/assets";
import { perfilDoFiltro, usePerfisTodos, vazioDoPerfil, type PerfilFiltro } from "@/lib/estudio";
import { useFiltroUrl } from "@/lib/filtros";
import { PerfilBaseFiltro, usePerfilBaseAtivo } from "./PerfilBaseFiltro";

const PAGE = 48;
const lista = (v: string | null) => (v ? v.split(",").filter(Boolean) : []);

export const assetsAgenciaKey = ["assets", "agencia"] as const;

// Biblioteca de assets da agência (spec 029, T017; antes a aba Assets do perfil, 007): os `tipos`
// fixos da página (avatares, cenários ou os de arquivo único), filtros na URL (`q`, `tipo`, `tag`,
// `arquivados=1` e o `perfil` base), a grade com o perfil base de cada card e "Carregar mais".
export function AssetsLista({
  tipos,
  perfilFiltro,
  onPerfilFiltro,
  titulo,
  descricao,
}: {
  tipos: AssetTipo[];
  perfilFiltro: PerfilFiltro;
  onPerfilFiltro: (v: PerfilFiltro) => void;
  titulo: string;
  descricao: string;
}) {
  const queryClient = useQueryClient();
  const [params, set] = useFiltroUrl();
  const tipoParam = params.get("tipo");
  const tagParam = params.get("tag");
  const q = params.get("q") ?? "";
  const archived = params.get("arquivados") === "1" ? "all" : "false";
  const filters = useMemo<AssetListFilters>(
    () => ({
      tipo: lista(tipoParam).filter((t): t is AssetTipo => (tipos as readonly string[]).includes(t)),
      tag: lista(tagParam),
      q,
      archived,
    }),
    [tipoParam, tagParam, q, archived, tipos],
  );
  const onFilters = (patch: Partial<AssetListFilters>) =>
    set(
      {
        ...("q" in patch ? { q: patch.q || null } : {}),
        ...(patch.tipo ? { tipo: patch.tipo.join(",") || null } : {}),
        ...(patch.tag ? { tag: patch.tag.join(",") || null } : {}),
        ...(patch.archived ? { arquivados: patch.archived === "all" ? "1" : null } : {}),
      },
      // a busca digitada não empilha no histórico
      { replace: "q" in patch },
    );

  const tiposQuery = filters.tipo.length ? filters.tipo : tipos;
  const assets = useInfiniteQuery({
    queryKey: [...assetsAgenciaKey, perfilFiltro, tiposQuery, filters],
    queryFn: ({ pageParam }) =>
      api.assets.listarAgencia({
        tipo: tiposQuery,
        perfilId: perfilFiltro === "todos" ? undefined : perfilFiltro,
        tag: filters.tag.length ? filters.tag : undefined,
        q: filters.q.trim() || undefined,
        archived: filters.archived,
        limit: PAGE,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  const items = useMemo(() => assets.data?.pages.flatMap((p) => p.items) ?? [], [assets.data]);
  const tags = assets.data?.pages[0]?.tags ?? [];
  // o filtro de perfil sozinho não conta: quem vem do card do perfil vê o convite para criar
  const filtering = filters.tipo.length > 0 || filters.tag.length > 0 || filters.q.trim() !== "";
  const perfis = usePerfisTodos();
  const vazio = vazioDoPerfil(perfilFiltro, perfis.data);
  const botaoNovo = tipos.length === 1 && tipos[0] === "avatar" ? "Novo avatar" : tipos.length === 1 && tipos[0] === "cenario" ? "Novo cenário" : "Novo asset";
  const ativosPerfil = usePerfilBaseAtivo(perfilFiltro, () => onPerfilFiltro("todos"));

  return (
    <HeaderCard
      title="Biblioteca da agência"
      description={descricao}
      actions={
        <NovoAssetMenu
          perfilId={perfilDoFiltro(perfilFiltro)}
          tipos={tipos}
          onCreated={() => queryClient.invalidateQueries({ queryKey: ["assets"] })}
        />
      }
    >
      <div className="space-y-4">
        <AssetFilters
          value={filters}
          tags={tags}
          tipos={tipos.length > 1 ? tipos : []}
          onChange={onFilters}
          onLimpar={() => {
            set({ q: null, tipo: null, tag: null, arquivados: null, perfil: null });
          }}
          principaisExtra={<PerfilBaseFiltro valor={perfilFiltro} onChange={onPerfilFiltro} />}
          ativosExtra={ativosPerfil}
        />
        {assets.isPending && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4" aria-live="polite">
            <span className="sr-only">Carregando…</span>
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="aspect-square rounded-xl" />
            ))}
          </div>
        )}
        {assets.isError && <ApiErrorAlert error={assets.error} />}
        {assets.data && items.length === 0 && (
          <EmptyState
            titulo={filtering ? "Nenhum item com esses filtros." : `Nenhum item${vazio.trecho} ainda.`}
            descricao={
              filtering
                ? undefined
                : `Use "${botaoNovo}" para criar o primeiro${vazio.criarComPerfil ? ": ele já nasce com este perfil base" : ""}.`
            }
            className="py-6"
          />
        )}
        {items.length > 0 && <AssetGrid items={items} label={titulo} />}
        {assets.hasNextPage && (
          <div className="flex justify-center">
            <Button type="button" variant="outline" disabled={assets.isFetchingNextPage} aria-busy={assets.isFetchingNextPage} onClick={() => void assets.fetchNextPage()}>
              {assets.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden="true" />}
              Carregar mais
            </Button>
          </div>
        )}
      </div>
    </HeaderCard>
  );
}
