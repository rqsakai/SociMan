import type { Perfil } from "@sociman/contract";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { HeaderCard } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AssetFilters } from "../../../components/assets/AssetFilters";
import { AssetGrid } from "../../../components/assets/AssetGrid";
import { NovoAssetMenu } from "../../../components/assets/NovoAssetMenu";
import { api } from "../../../lib/api";
import { assetsKey, assetsListKey, type AssetListFilters } from "../../../lib/assets";

const PAGE = 48;
const initialFilters: AssetListFilters = { tipo: [], tag: [], q: "", archived: "false" };

// Aba Assets do perfil (spec 007, FR-001/FR-005): filtros (tipo, tag, busca, arquivados), a grade
// de cards com "Carregar mais" (cursor da API, R8) e "Novo asset".
export function AssetsTab({ perfil }: { perfil: Perfil }) {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<AssetListFilters>(initialFilters);
  const onFilters = useCallback((next: AssetListFilters) => setFilters(next), []);

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
    <div className="flex flex-col gap-6">
      <HeaderCard
        title="Biblioteca de assets"
        description="Avatares, cenários, fundos, stickers, marcas d'água e imagens do perfil. Nada é apagado: arquive e restaure."
        actions={<NovoAssetMenu perfilId={perfil.id} disabled={perfil.archived} onCreated={() => queryClient.invalidateQueries({ queryKey: assetsKey(perfil.id) })} />}
      >
        <div className="space-y-4">
          <AssetFilters value={filters} tags={tags} onChange={onFilters} />
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
            <p className="py-4 text-sm text-muted-foreground">
              {filtering ? "Nenhum asset com esses filtros." : 'Nenhum asset ainda. Use "Novo asset" para criar o primeiro.'}
            </p>
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
    </div>
  );
}
