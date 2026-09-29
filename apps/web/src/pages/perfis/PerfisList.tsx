import type { PerfilFilters, PerfilStatus } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AppLayout } from "../../components/AppLayout";
import { Card, PageHeader } from "../../components/layout";
import { PlatformIcon } from "../../components/PlatformIcon";
import { ProfileAvatar } from "../../components/ProfileAvatar";
import { Button, Field, Input, Select } from "../../components/ui";
import { api } from "../../lib/api";
import { perfilStatusLabel } from "../../lib/perfis";

// /app/perfis: perfis da agência com busca por nome, filtro de status e "Arquivados" (FR-003).
export default function PerfisList() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<PerfilStatus | "">("");
  const [archived, setArchived] = useState(false);
  const deferredQ = useDeferredValue(q.trim());

  const filters: PerfilFilters = { q: deferredQ || undefined, status: status || undefined, archived };
  const { data, isPending, isError } = useQuery({
    queryKey: ["perfis", filters],
    queryFn: () => api.perfis.list(filters),
    placeholderData: (previous) => previous,
  });

  return (
    <AppLayout>
      <PageHeader
        title="Perfis"
        description="Os perfis da agência e as contas de cada um nas plataformas."
        actions={
          <Button type="button" className="!w-auto" onClick={() => navigate("/app/perfis/novo")}>
            <Plus className="size-4" aria-hidden="true" />
            Novo perfil
          </Button>
        }
      />
      <div className="space-y-6">
        <Card>
          <div className="grid gap-4 sm:grid-cols-3 sm:items-end">
            <Field label="Buscar">
              {({ id }) => (
                <Input
                  id={id}
                  type="search"
                  icon={Search}
                  placeholder="Nome do perfil"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              )}
            </Field>
            <Field label="Status">
              {({ id }) => (
                <Select id={id} value={status} onChange={(e) => setStatus(e.target.value as PerfilStatus | "")}>
                  <option value="">Todos</option>
                  {Object.entries(perfilStatusLabel).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <label className="flex items-center gap-2 py-2 text-sm font-medium">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={archived}
                onChange={(e) => setArchived(e.target.checked)}
              />
              Arquivados
            </label>
          </div>
        </Card>

        <Card>
          {isPending && <p aria-live="polite">Carregando…</p>}
          {isError && <p className="text-sm text-danger">Não foi possível carregar os perfis.</p>}
          {data && data.items.length === 0 && (
            <p className="text-sm text-muted">
              {archived ? "Nenhum perfil arquivado encontrado." : "Nenhum perfil encontrado."}
            </p>
          )}
          {data && data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-muted">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Nome</th>
                    <th className="py-2 pr-4 font-medium">Nicho</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 font-medium">Plataformas</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((perfil) => (
                    <tr key={perfil.id} className="border-b border-border last:border-0">
                      <td className="py-2 pr-4">
                        <Link to={`/app/perfis/${perfil.id}`} className="flex items-center gap-3 font-medium hover:underline">
                          <ProfileAvatar name={perfil.name} logo={perfil.logo} />
                          <span>{perfil.name}</span>
                        </Link>
                      </td>
                      <td className="py-2 pr-4">{perfil.niche || "—"}</td>
                      <td className="py-2 pr-4">
                        {perfilStatusLabel[perfil.status]}
                        {perfil.archived && <span className="text-muted"> · arquivado</span>}
                      </td>
                      <td className="py-2">
                        {perfil.platforms.length === 0 ? (
                          <span className="text-muted">—</span>
                        ) : (
                          <span className="flex flex-wrap gap-2">
                            {perfil.platforms.map((platform) => (
                              <PlatformIcon key={platform} platform={platform} />
                            ))}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </AppLayout>
  );
}
