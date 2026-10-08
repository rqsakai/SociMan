import type { SecurityEvent, SecurityEventFilters } from "@sociman/contract";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { HeaderCard, Page } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { PageHeading } from "../components/PageHeading";
import { api } from "../lib/api";
import { useFiltroUrl } from "../lib/filtros";
import { errorText } from "../lib/perfis";
import { formatDateTime } from "../lib/tz";
import { actorText, eventTypeLabel, localDayBound, outcomeLabel } from "../lib/securityEvents";


// "2026-10-07" → "07/10/2026" (etiqueta do filtro)
const diaText = (dia: string) => dia.split("-").reverse().join("/");

const col = dataTableColumns<SecurityEvent>();
const columns = col.columns([
  col.accessor("occurredAt", {
    header: "Data",
    enableGlobalFilter: false,
    cell: (c) => <time dateTime={c.getValue()} title={c.getValue()} className="whitespace-nowrap">{formatDateTime(c.getValue())}</time>,
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
// rodam no servidor (na URL, aplicados ao mudar) e a lista vem por cursor ("Carregar mais"); a busca
// e a ordenação da tabela valem sobre o que já foi carregado.
export default function SecurityEvents() {
  const [params, set] = useFiltroUrl();
  const userId = params.get("usuario") ?? "";
  const type = params.get("tipo") ?? "";
  const from = params.get("de") ?? "";
  const to = params.get("ate") ?? "";
  const filters: SecurityEventFilters = {
    userId: userId || undefined,
    type: type || undefined,
    from: from ? localDayBound(from, false) : undefined,
    to: to ? localDayBound(to, true) : undefined,
  };

  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users.list() });

  const events = useInfiniteQuery({
    queryKey: ["security-events", filters],
    queryFn: ({ pageParam }) => api.securityEvents.list({ ...filters, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });

  const items = events.data?.pages.flatMap((page) => page.items);
  const ativos: FiltroAtivo[] = [
    ...(userId
      ? [{ chave: "usuario", rotulo: "Usuário", valor: users.data?.items.find((u) => u.id === userId)?.name ?? "…", limpar: () => set({ usuario: null }) }]
      : []),
    ...(type ? [{ chave: "tipo", rotulo: "Tipo", valor: eventTypeLabel[type] ?? type, limpar: () => set({ tipo: null }) }] : []),
    ...(from ? [{ chave: "de", rotulo: "De", valor: diaText(from), limpar: () => set({ de: null }), mais: true }] : []),
    ...(to ? [{ chave: "ate", rotulo: "Até", valor: diaText(to), limpar: () => set({ ate: null }), mais: true }] : []),
  ];

  return (
    <Page>
      <PageHeading title="Eventos de segurança" description="Logins, trocas de senha e mudanças de acesso." />
      {events.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorText(events.error)}</AlertDescription>
        </Alert>
      )}
      <HeaderCard title="Registro" description="Do mais recente para o mais antigo">
        <DataTable
          label="Eventos de segurança"
          columns={columns}
          data={items}
          loading={events.isPending}
          getRowId={(e) => String(e.id)}
          search={{ placeholder: "Buscar na lista carregada", label: "Buscar nos eventos" }}
          toolbar={
            <FilterBar
              principais={
                <>
                  <Field label="Usuário" className="w-full sm:w-48">
                    {({ id }) => (
                      <NativeSelect id={id} value={userId} onChange={(e) => set({ usuario: e.target.value })}>
                        <option value="">Todos</option>
                        {users.data?.items.map((user) => (
                          <option key={user.id} value={user.id}>
                            {user.name}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <Field label="Tipo" className="w-full sm:w-56">
                    {({ id }) => (
                      <NativeSelect id={id} value={type} onChange={(e) => set({ tipo: e.target.value })}>
                        <option value="">Todos</option>
                        {Object.entries(eventTypeLabel).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                </>
              }
              mais={
                <>
                  <Field label="De">
                    {({ id }) => <DateField id={id} value={from} onChange={(iso) => set({ de: iso || null })} />}
                  </Field>
                  <Field label="Até">
                    {({ id }) => <DateField id={id} value={to} onChange={(iso) => set({ ate: iso || null })} />}
                  </Field>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ usuario: null, tipo: null, de: null, ate: null })}
            />
          }
          emptyMessage="Nenhum evento encontrado."
          pagination={{
            hasMore: events.hasNextPage,
            onLoadMore: () => void events.fetchNextPage(),
            loadingMore: events.isFetchingNextPage,
          }}
        />
      </HeaderCard>
    </Page>
  );
}
