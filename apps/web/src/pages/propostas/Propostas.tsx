/*
 * "Propostas dos agentes" (spec 009, US4; T049). A caixa de tudo o que os agentes (e as pessoas)
 * anotaram nos itens: filtros por perfil, cliente, tipo e situação no servidor e "Carregar mais".
 * Aplicar e descartar acontecem no próprio item (o link leva até ele).
 */
import { Filter } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { AgenteSelo } from "@/components/mcp/AgenteSelo";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import {
  aceitarCenaHref,
  alvoTipoLabel,
  situacaoAnotacaoLabel,
  situacaoAnotacaoTone,
  tipoAnotacaoLabel,
  useAnotacoes,
  type Anotacao,
  type AnotacaoFilters,
  type AnotacaoSituacao,
  type AnotacaoTipo,
} from "@/lib/anotacoes";
import { useAuth } from "@/lib/authStore";
import { useMcpClientes } from "@/lib/mcp";
import { usePerfisAtivos } from "@/lib/usePerfis";
import { formatDateTime } from "@/lib/tz";

type Draft = { perfilId: string; autorClienteId: string; tipo: string; situacao: string };
const inicial: Draft = { perfilId: "", autorClienteId: "", tipo: "", situacao: "aberta" };

const paraFiltros = (d: Draft): AnotacaoFilters => ({
  perfilId: d.perfilId || undefined,
  autorClienteId: d.autorClienteId || undefined,
  tipo: (d.tipo || undefined) as AnotacaoFilters["tipo"],
  situacao: (d.situacao || undefined) as AnotacaoFilters["situacao"],
});

const col = dataTableColumns<Anotacao>();
const columns = col.columns([
  col.accessor("createdAt", {
    header: "Quando",
    enableGlobalFilter: false,
    cell: (c) => <time dateTime={c.getValue()} className="whitespace-nowrap">{formatDateTime(c.getValue())}</time>,
  }),
  col.accessor((a) => a.autor.nome ?? "—", {
    id: "autor",
    header: "Autor",
    cell: (c) => (c.row.original.autor.tipo === "mcp_client" ? <AgenteSelo nome={c.getValue()} /> : <span>{c.getValue()}</span>),
  }),
  col.accessor((a) => `${alvoTipoLabel[a.alvo.tipo]} ${a.alvo.titulo ?? ""}`, {
    id: "item",
    header: "Item",
    cell: (c) => {
      const alvo = c.row.original.alvo;
      return (
        <div className="min-w-0 space-y-0.5">
          <p className="text-xs text-muted-foreground">{alvoTipoLabel[alvo.tipo]}</p>
          {alvo.link ? (
            <Link to={alvo.link} className="font-medium underline-offset-2 hover:underline">
              {alvo.titulo || "abrir item"}
            </Link>
          ) : (
            <span className="font-medium">{alvo.titulo || "—"}</span>
          )}
          {alvo.arquivado && (
            <Badge variant="outline" className="ml-1">
              item arquivado
            </Badge>
          )}
          {/* spec 010: a proposta de cena é aceita no formulário da cena */}
          {aceitarCenaHref(c.row.original) && (
            <Link to={aceitarCenaHref(c.row.original)!} className="block text-sm font-medium text-primary underline-offset-2 hover:underline">
              Aceitar
            </Link>
          )}
        </div>
      );
    },
  }),
  col.accessor((a) => tipoAnotacaoLabel[a.tipo], { id: "tipo", header: "Tipo", meta: { className: "hidden md:table-cell" } }),
  col.accessor("texto", {
    header: "Texto",
    cell: (c) => <p className="line-clamp-3 max-w-md text-sm break-words whitespace-pre-wrap">{c.getValue()}</p>,
  }),
  col.accessor((a) => situacaoAnotacaoLabel[a.situacao], {
    id: "situacao",
    header: "Situação",
    cell: (c) => <Badge className={situacaoAnotacaoTone[c.row.original.situacao]}>{c.getValue()}</Badge>,
  }),
]);

export default function Propostas() {
  usePageMeta({ title: "Propostas dos agentes" });
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const perfis = usePerfisAtivos();
  // Só o dono lista os clientes MCP; o membro filtra pelos autores já carregados.
  const clientes = useMcpClientes(isOwner);
  const [draft, setDraft] = useState<Draft>(inicial);
  const [filtros, setFiltros] = useState<AnotacaoFilters>(() => paraFiltros(inicial));
  const anotacoes = useAnotacoes(filtros);
  const itens = anotacoes.data?.pages.flatMap((p) => p.anotacoes);

  const opcoesCliente = useMemo(() => {
    if (isOwner) return (clientes.data?.clientes ?? []).map((c) => ({ id: c.id, nome: c.nome }));
    const vistos = new Map<string, string>();
    for (const a of itens ?? []) if (a.autor.tipo === "mcp_client" && a.autor.id) vistos.set(a.autor.id, a.autor.nome ?? "—");
    return [...vistos].map(([id, nome]) => ({ id, nome }));
  }, [isOwner, clientes.data, itens]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFiltros(paraFiltros(draft));
  }

  return (
    <div className="space-y-6">
      <PageHeading
        title="Propostas dos agentes"
        description="Anotações e propostas de texto gravadas pelos agentes nos itens. Aplique ou descarte no próprio item: nada muda sem o seu clique."
      />
      <HeaderCard title="Caixa de propostas" description="Da mais nova para a mais antiga" tone="dark">
        <form onSubmit={onSubmit} className="mb-4 grid gap-4 border-b pb-4 sm:grid-cols-2 lg:grid-cols-[repeat(4,minmax(0,1fr))_auto] lg:items-end">
          <Field label="Perfil">
            {({ id }) => (
              <NativeSelect id={id} value={draft.perfilId} onChange={(e) => setDraft({ ...draft, perfilId: e.target.value })}>
                <option value="">Todos</option>
                {perfis.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Cliente">
            {({ id }) => (
              <NativeSelect id={id} value={draft.autorClienteId} onChange={(e) => setDraft({ ...draft, autorClienteId: e.target.value })}>
                <option value="">Todos</option>
                {opcoesCliente.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nome}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Tipo">
            {({ id }) => (
              <NativeSelect id={id} value={draft.tipo} onChange={(e) => setDraft({ ...draft, tipo: e.target.value })}>
                <option value="">Todos</option>
                {(Object.keys(tipoAnotacaoLabel) as AnotacaoTipo[]).map((t) => (
                  <option key={t} value={t}>
                    {tipoAnotacaoLabel[t]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Situação">
            {({ id }) => (
              <NativeSelect id={id} value={draft.situacao} onChange={(e) => setDraft({ ...draft, situacao: e.target.value })}>
                <option value="">Todas</option>
                {(Object.keys(situacaoAnotacaoLabel) as AnotacaoSituacao[]).map((s) => (
                  <option key={s} value={s}>
                    {situacaoAnotacaoLabel[s]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Button type="submit">
            <Filter aria-hidden="true" />
            Filtrar
          </Button>
        </form>
        {anotacoes.isError && <ApiErrorAlert error={anotacoes.error} />}
        <DataTable
          label="Propostas dos agentes"
          columns={columns}
          data={itens}
          loading={anotacoes.isPending}
          getRowId={(a) => a.id}
          search={{ placeholder: "Buscar na lista carregada", label: "Buscar nas propostas" }}
          emptyMessage="Nenhuma proposta encontrada."
          pagination={{
            hasMore: anotacoes.hasNextPage,
            onLoadMore: () => void anotacoes.fetchNextPage(),
            loadingMore: anotacoes.isFetchingNextPage,
          }}
        />
      </HeaderCard>
    </div>
  );
}
