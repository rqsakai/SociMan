import type { SecurityEventFilters } from "@sociman/contract";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Filter } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AppLayout } from "../components/AppLayout";
import { Card, PageHeader } from "../components/layout";
import { Button, Field, Input, Select } from "../components/ui";
import { api } from "../lib/api";
import { actorText, eventTypeLabel, localDayBound, outcomeLabel } from "../lib/securityEvents";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });

type Draft = { userId: string; type: string; from: string; to: string };
const emptyDraft: Draft = { userId: "", type: "", from: "", to: "" };

function toFilters(draft: Draft): SecurityEventFilters {
  return {
    userId: draft.userId || undefined,
    type: draft.type || undefined,
    from: draft.from ? localDayBound(draft.from, false) : undefined,
    to: draft.to ? localDayBound(draft.to, true) : undefined,
  };
}

// /app/seguranca (só dono): eventos de segurança, do mais recente para o mais
// antigo, com filtros e paginação por cursor.
export default function SecurityEvents() {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [filters, setFilters] = useState<SecurityEventFilters>({});

  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users.list() });

  const events = useInfiniteQuery({
    queryKey: ["security-events", filters],
    queryFn: ({ pageParam }) => api.securityEvents.list({ ...filters, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFilters(toFilters(draft));
  }

  const items = events.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <AppLayout>
      <PageHeader title="Eventos de segurança" description="Logins, trocas de senha e mudanças de acesso." />
      <div className="space-y-6">
        <Card>
          <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5 lg:items-end">
            <Field label="Usuário">
              {({ id }) => (
                <Select id={id} value={draft.userId} onChange={(e) => setDraft({ ...draft, userId: e.target.value })}>
                  <option value="">Todos</option>
                  {users.data?.items.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Tipo">
              {({ id }) => (
                <Select id={id} value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}>
                  <option value="">Todos</option>
                  {Object.entries(eventTypeLabel).map(([type, label]) => (
                    <option key={type} value={type}>
                      {label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="De">
              {({ id }) => (
                <Input id={id} type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
              )}
            </Field>
            <Field label="Até">
              {({ id }) => (
                <Input id={id} type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
              )}
            </Field>
            <Button type="submit">
              <Filter className="size-4" aria-hidden="true" />
              Filtrar
            </Button>
          </form>
        </Card>

        <Card>
          {events.isPending && <p aria-live="polite">Carregando…</p>}
          {events.isError && <p className="text-sm text-danger">Não foi possível carregar os eventos.</p>}
          {events.isSuccess && items.length === 0 && <p className="text-sm text-muted">Nenhum evento encontrado.</p>}
          {items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-muted">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Data</th>
                    <th className="py-2 pr-4 font-medium">Tipo</th>
                    <th className="py-2 pr-4 font-medium">Resultado</th>
                    <th className="py-2 pr-4 font-medium">Autor</th>
                    <th className="py-2 pr-4 font-medium">Usuário afetado</th>
                    <th className="py-2 font-medium">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((event) => (
                    <tr key={event.id} className="border-b border-border last:border-0">
                      <td className="py-2 pr-4 whitespace-nowrap">{dateFormat.format(new Date(event.occurredAt))}</td>
                      <td className="py-2 pr-4">{eventTypeLabel[event.type] ?? event.type}</td>
                      <td className="py-2 pr-4">{outcomeLabel[event.outcome]}</td>
                      <td className="py-2 pr-4">{actorText(event)}</td>
                      <td className="py-2 pr-4">{event.subjectName ?? "—"}</td>
                      <td className="py-2">{event.ip ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {events.hasNextPage && (
            <div className="mt-4">
              <Button
                type="button"
                variant="ghost"
                className="!w-auto"
                loading={events.isFetchingNextPage}
                onClick={() => void events.fetchNextPage()}
              >
                Carregar mais
              </Button>
            </div>
          )}
        </Card>
      </div>
    </AppLayout>
  );
}
