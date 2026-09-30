import type { SecurityEvent, SecurityEventFilters } from "@sociman/contract";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Filter } from "lucide-react";
import { useState, type FormEvent } from "react";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { HeaderCard } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageHeading } from "../components/PageHeading";
import { api } from "../lib/api";
import { errorText } from "../lib/perfis";
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

const col = dataTableColumns<SecurityEvent>();
const columns = col.columns([
  col.accessor("occurredAt", {
    header: "Data",
    enableGlobalFilter: false,
    cell: (c) => <span className="whitespace-nowrap">{dateFormat.format(new Date(c.getValue()))}</span>,
  }),
  col.accessor((e) => eventTypeLabel[e.type] ?? e.type, {
    id: "type",
    header: "Tipo",
    cell: (c) => <span className="font-semibold">{c.getValue()}</span>,
  }),
  col.accessor((e) => outcomeLabel[e.outcome], {
    id: "outcome",
    header: "Resultado",
    cell: (c) => (
      <Badge
        className={
          c.row.original.outcome === "ok"
            ? "bg-success text-success-foreground uppercase"
            : "bg-destructive text-destructive-foreground uppercase"
        }
      >
        {c.getValue()}
      </Badge>
    ),
  }),
  col.accessor((e) => actorText(e), { id: "actor", header: "Autor", meta: { className: "hidden sm:table-cell" } }),
  col.accessor((e) => e.subjectName ?? "—", { id: "subject", header: "Usuário afetado" }),
  col.accessor((e) => e.ip ?? "—", {
    id: "ip",
    header: "IP",
    meta: { className: "hidden md:table-cell font-mono text-xs" },
  }),
]);

// /app/seguranca (só dono): eventos de segurança, do mais recente para o mais antigo. Os filtros
// rodam no servidor e a lista vem por cursor ("Carregar mais"); a busca e a ordenação da tabela
// valem sobre o que já foi carregado.
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

  const items = events.data?.pages.flatMap((page) => page.items);

  return (
    <div className="space-y-6">
      <PageHeading title="Eventos de segurança" description="Logins, trocas de senha e mudanças de acesso." />
      {events.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorText(events.error)}</AlertDescription>
        </Alert>
      )}
      <HeaderCard title="Registro" description="Do mais recente para o mais antigo" tone="dark">
        <form
          onSubmit={onSubmit}
          className="grid gap-4 border-b pb-4 mb-4 sm:grid-cols-2 lg:grid-cols-[repeat(4,minmax(0,1fr))_auto] lg:items-end"
        >
          <Field label="Usuário">
            {({ id }) => (
              <NativeSelect id={id} value={draft.userId} onChange={(e) => setDraft({ ...draft, userId: e.target.value })}>
                <option value="">Todos</option>
                {users.data?.items.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Tipo">
            {({ id }) => (
              <NativeSelect id={id} value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}>
                <option value="">Todos</option>
                {Object.entries(eventTypeLabel).map(([type, label]) => (
                  <option key={type} value={type}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
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
            <Filter aria-hidden="true" />
            Filtrar
          </Button>
        </form>

        <DataTable
          label="Eventos de segurança"
          columns={columns}
          data={items}
          loading={events.isPending}
          getRowId={(e) => String(e.id)}
          search={{ placeholder: "Buscar na lista carregada", label: "Buscar nos eventos" }}
          emptyMessage="Nenhum evento encontrado."
          pagination={{
            hasMore: events.hasNextPage,
            onLoadMore: () => void events.fetchNextPage(),
            loadingMore: events.isFetchingNextPage,
          }}
        />
      </HeaderCard>
    </div>
  );
}
