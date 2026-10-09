import type { Perfil, PerfilFilters, PerfilStatus } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { HeaderCard, Page } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { PageHeading } from "../../components/PageHeading";
import { PlatformIcon } from "../../components/PlatformIcon";
import { ProfileAvatar } from "../../components/ProfileAvatar";
import { api } from "../../lib/api";
import { useFiltroUrl } from "../../lib/filtros";
import { formatDate } from "../../lib/tz";
import { errorText, perfilStatusLabel } from "../../lib/perfis";

const statusBadge: Record<PerfilStatus, string> = {
  ativo: "bg-success text-success-foreground",
  em_preparacao: "bg-warning text-warning-foreground",
  pausado: "bg-dark text-dark-foreground",
};

const col = dataTableColumns<Perfil>();
const columns = col.columns([
  // nome + nicho no mesmo accessor: a busca por texto acha os dois; a ordem segue o nome
  col.accessor((p) => `${p.name} ${p.niche}`, {
    id: "name",
    header: "Nome",
    cell: (c) => {
      const perfil = c.row.original;
      return (
        <Link to={`/app/perfis/${perfil.id}`} className="group flex items-center gap-3">
          <ProfileAvatar name={perfil.name} logo={perfil.logo} />
          <span className="min-w-0">
            <span className="block truncate font-semibold group-hover:underline">{perfil.name}</span>
            <span className="block truncate text-xs text-muted-foreground">{perfil.niche || "Sem nicho"}</span>
          </span>
        </Link>
      );
    },
  }),
  col.accessor((p) => perfilStatusLabel[p.status], {
    id: "status",
    header: "Status",
    cell: (c) => {
      const perfil = c.row.original;
      return (
        <span className="flex flex-wrap gap-1">
          <Badge className={`${statusBadge[perfil.status]} uppercase`}>{c.getValue()}</Badge>
          {perfil.archived && (
            <Badge variant="outline" className="uppercase">
              arquivado
            </Badge>
          )}
        </span>
      );
    },
  }),
  col.accessor((p) => p.platforms.length, {
    id: "plataformas",
    header: "Plataformas",
    enableGlobalFilter: false,
    cell: (c) => {
      const { platforms } = c.row.original;
      return platforms.length === 0 ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        <span className="flex flex-wrap gap-2">
          {platforms.map((platform) => (
            <PlatformIcon key={platform} platform={platform} />
          ))}
        </span>
      );
    },
  }),
  col.accessor("updatedAt", {
    header: "Atualizado em",
    enableGlobalFilter: false,
    cell: (c) => formatDate(c.getValue()),
    meta: { className: "hidden md:table-cell" },
  }),
]);

// Busca sem acento e sem caixa (o `q` da API só olha o nome; aqui vale o nicho também).
const normalizar = (t: string) => t.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

// /app/perfis: perfis da agência com busca por texto, filtro de status e "Arquivados" (FR-003).
// Status e "Arquivados" filtram no servidor; a busca (nome ou nicho, sobre a lista toda), a
// ordenação e a paginação, na tela. Filtros na URL (spec 024): `q`, `status` e `arquivados`.
export default function PerfisList() {
  const [params, set] = useFiltroUrl();
  const q = params.get("q") ?? "";
  const statusParam = params.get("status") ?? "";
  const status = Object.hasOwn(perfilStatusLabel, statusParam) ? (statusParam as PerfilStatus) : "";
  const archived = params.get("arquivados") === "1";

  const filters: PerfilFilters = { status: status || undefined, archived };
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["perfis", filters],
    queryFn: () => api.perfis.list(filters),
    placeholderData: (previous) => previous,
  });
  const linhas = useMemo(() => {
    const termo = normalizar(q.trim());
    return termo ? data?.items.filter((p) => normalizar(`${p.name} ${p.niche}`).includes(termo)) : data?.items;
  }, [data, q]);
  const ativos: FiltroAtivo[] = [
    ...(q ? [{ chave: "q", rotulo: "Busca", valor: q, limpar: () => set({ q: null }) }] : []),
    ...(status ? [{ chave: "status", rotulo: "Status", valor: perfilStatusLabel[status], limpar: () => set({ status: null }) }] : []),
    ...(archived ? [{ chave: "arquivados", rotulo: "Arquivados", valor: "sim", limpar: () => set({ arquivados: null }) }] : []),
  ];

  return (
    <Page>
      <PageHeading title="Perfis" description="Os perfis da agência e as contas de cada um nas plataformas." />
      {isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorText(error)}</AlertDescription>
        </Alert>
      )}
      <HeaderCard
        title="Todos os perfis"
        description="Um nicho por perfil"
        actions={
          <Button asChild variant="secondary" size="sm">
            <Link to="/app/perfis/novo">
              <Plus aria-hidden="true" />
              Novo perfil
            </Link>
          </Button>
        }
      >
        <DataTable
          label="Perfis"
          columns={columns}
          data={linhas}
          loading={isPending}
          getRowId={(p) => p.id}
          emptyMessage={!q && !status && archived ? "Nenhum perfil arquivado." : undefined}
          toolbar={
            <FilterBar
              busca={{ valor: q, onChange: (v) => set({ q: v || null }, { replace: true }), placeholder: "Nome ou nicho" }}
              principais={
                <>
                  <Field label="Status" className="w-full sm:w-40">
                    {({ id }) => (
                      <NativeSelect id={id} value={status} onChange={(e) => set({ status: e.target.value || null })}>
                        <option value="">Todos</option>
                        {Object.entries(perfilStatusLabel).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <label className="flex h-9 items-center gap-2 text-sm font-medium">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={archived}
                      onChange={(e) => set({ arquivados: e.target.checked ? "1" : null })}
                    />
                    Arquivados
                  </label>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ q: null, status: null, arquivados: null })}
            />
          }
        />
      </HeaderCard>
    </Page>
  );
}
