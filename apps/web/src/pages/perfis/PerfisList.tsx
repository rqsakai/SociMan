import type { Perfil, PerfilFilters, PerfilStatus } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { HeaderCard } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/field";
import { PageHeading } from "../../components/PageHeading";
import { PlatformIcon } from "../../components/PlatformIcon";
import { ProfileAvatar } from "../../components/ProfileAvatar";
import { api } from "../../lib/api";
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
    cell: (c) => new Date(c.getValue()).toLocaleDateString("pt-BR"),
    meta: { className: "hidden md:table-cell" },
  }),
]);

// /app/perfis: perfis da agência com busca por texto, filtro de status e "Arquivados" (FR-003).
// Status e "Arquivados" filtram no servidor; a busca, a ordenação e a paginação, na tabela.
export default function PerfisList() {
  const statusId = useId();
  const [status, setStatus] = useState<PerfilStatus | "">("");
  const [archived, setArchived] = useState(false);

  const filters: PerfilFilters = { status: status || undefined, archived };
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["perfis", filters],
    queryFn: () => api.perfis.list(filters),
    placeholderData: (previous) => previous,
  });

  return (
    <div className="space-y-6">
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
          data={data?.items}
          loading={isPending}
          getRowId={(p) => p.id}
          search={{ placeholder: "Nome ou nicho", label: "Buscar" }}
          toolbar={
            <>
              <label htmlFor={statusId} className="flex items-center gap-2 text-sm font-medium">
                Status
                <NativeSelect
                  id={statusId}
                  className="w-40"
                  value={status}
                  onChange={(e) => setStatus(e.target.value as PerfilStatus | "")}
                >
                  <option value="">Todos</option>
                  {Object.entries(perfilStatusLabel).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </NativeSelect>
              </label>
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={archived}
                  onChange={(e) => setArchived(e.target.checked)}
                />
                Arquivados
              </label>
            </>
          }
        />
      </HeaderCard>
    </div>
  );
}
