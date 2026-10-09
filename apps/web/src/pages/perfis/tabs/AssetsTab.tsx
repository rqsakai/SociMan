import type { Perfil } from "@sociman/contract";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useMemo } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { EmptyState, HeaderCard, Page } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AssetFilters } from "../../../components/assets/AssetFilters";
import { AssetGrid } from "../../../components/assets/AssetGrid";
import { NovoAssetMenu } from "../../../components/assets/NovoAssetMenu";
import { api } from "../../../lib/api";
import { assetsKey, assetsListKey, TIPOS, type AssetListFilters, type AssetTipo } from "../../../lib/assets";
import { useFiltroUrl } from "../../../lib/filtros";

const PAGE = 48;
const lista = (v: string | null) => (v ? v.split(",").filter(Boolean) : []);

// Aba Assets do perfil (spec 007, FR-001/FR-005): filtros (tipo, tag, busca, arquivados), a grade
// de cards com "Carregar mais" (cursor da API, R8) e "Novo asset". Spec 024: os filtros ficam na URL
// (`q`, `tipo` e `tag` separados por vírgula, `arquivados=1`).
export function AssetsTab({ perfil }: { perfil: Perfil }) {
  const queryClient = useQueryClient();
  const [params, set] = useFiltroUrl();
  const tipoParam = params.get("tipo");
  const tagParam = params.get("tag");
  const q = params.get("q") ?? "";
  const archived = params.get("arquivados") === "1" ? "all" : "false";
  const filters = useMemo<AssetListFilters>(
    () => ({
      tipo: lista(tipoParam).filter((t): t is AssetTipo => (TIPOS as readonly string[]).includes(t)),
      tag: lista(tagParam),
      q,
      archived,
    }),
    [tipoParam, tagParam, q, archived],
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

  const assets = useInfiniteQuery({
    queryKey: assetsListKey(perfil.id, filters),
    queryFn: ({ pageParam }) =>
      api.assets.list(perfil.id, {
        tipo: filters.tipo.length ? filters.tipo : undefined,
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
  const filtering = filters.tipo.length > 0 || filters.tag.length > 0 || filters.q.trim() !== "";

  return (
    <Page>
      <HeaderCard
        title="Biblioteca de assets"
        description="Avatares, cenários, fundos, stickers, marcas d'água e imagens do perfil. Nada é apagado: arquive e restaure."
        actions={<NovoAssetMenu perfilId={perfil.id} disabled={perfil.archived} onCreated={() => queryClient.invalidateQueries({ queryKey: assetsKey(perfil.id) })} />}
      >
        <div className="space-y-4">
          <AssetFilters
            value={filters}
            tags={tags}
            onChange={onFilters}
            onLimpar={() => set({ q: null, tipo: null, tag: null, arquivados: null })}
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
              titulo={filtering ? "Nenhum asset com esses filtros." : 'Nenhum asset ainda. Use "Novo asset" para criar o primeiro.'}
              className="py-6"
            />
          )}
          {items.length > 0 && <AssetGrid items={items} />}
          {assets.hasNextPage && (
            <div className="flex justify-center">
              <Button
                type="button"
                variant="outline"
                disabled={assets.isFetchingNextPage}
                aria-busy={assets.isFetchingNextPage}
                onClick={() => void assets.fetchNextPage()}
              >
                {assets.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden="true" />}
                Carregar mais
              </Button>
            </div>
          )}
        </div>
      </HeaderCard>
    </Page>
  );
}
