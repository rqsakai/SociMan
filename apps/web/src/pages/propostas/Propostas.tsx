/*
 * "Propostas dos agentes" (spec 009, US4; T049). A caixa de tudo o que os agentes (e as pessoas)
 * anotaram nos itens: filtros no servidor e "Carregar mais". Aplicar e descartar acontecem no
 * próprio item (o link leva até ele).
 *
 * Spec 024 (T051, T062): uma busca só (`q` no servidor), a FilterBar com o estado no endereço
 * (`q`, `perfil`, `situacao`, `autor`, `tipo`; sem `situacao` = "Aberta", `situacao=todas` = todas)
 * e dois vazios: sem filtro ("Ainda não chegou nenhuma proposta") e com filtro.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { AgenteSelo } from "@/components/mcp/AgenteSelo";
import { PageHeading } from "@/components/PageHeading";
import { EmptyState, HeaderCard, Page, usePageMeta } from "@/components/shell";
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
import { api } from "@/lib/api";
import { useAuth } from "@/lib/authStore";
import { useFiltroUrl } from "@/lib/filtros";
import { useMcpClientes } from "@/lib/mcp";
import { usePerfisAtivos } from "@/lib/usePerfis";
import { formatDateTime } from "@/lib/tz";

// Sem `situacao` no endereço, a caixa mostra as abertas; "todas" tira o filtro.
const SITUACAO_PADRAO: AnotacaoSituacao = "aberta";
const TODAS = "todas";
const CHAVES = ["q", "perfil", "situacao", "autor", "tipo"] as const;

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
  const [params, set] = useFiltroUrl();
  const q = params.get("q") ?? "";
  const perfilId = params.get("perfil") ?? "";
  const situacaoUrl = params.get("situacao") ?? "";
  const situacao = situacaoUrl || SITUACAO_PADRAO;
  const autorId = params.get("autor") ?? "";
  const tipo = params.get("tipo") ?? "";

  const filtros = useMemo<AnotacaoFilters>(
    () => ({
      q: q || undefined,
      perfilId: perfilId || undefined,
      autorClienteId: autorId || undefined,
      tipo: (tipo || undefined) as AnotacaoFilters["tipo"],
      situacao: (situacao === TODAS ? undefined : situacao) as AnotacaoFilters["situacao"],
    }),
    [q, perfilId, autorId, tipo, situacao],
  );
  const anotacoes = useAnotacoes(filtros);
  const itens = anotacoes.data?.pages.flatMap((p) => p.anotacoes);

  const opcoesCliente = useMemo(() => {
    if (isOwner) return (clientes.data?.clientes ?? []).map((c) => ({ id: c.id, nome: c.nome }));
    const vistos = new Map<string, string>();
    for (const a of itens ?? []) if (a.autor.tipo === "mcp_client" && a.autor.id) vistos.set(a.autor.id, a.autor.nome ?? "—");
    return [...vistos].map(([id, nome]) => ({ id, nome }));
  }, [isOwner, clientes.data, itens]);

  const limpar = () => set(Object.fromEntries(CHAVES.map((k) => [k, null])));
  const nomePerfil = perfis.data?.find((p) => p.id === perfilId)?.name ?? "perfil";
  const nomeAutor = opcoesCliente.find((c) => c.id === autorId)?.nome ?? "agente";
  const ativos: FiltroAtivo[] = [
    ...(q ? [{ chave: "q", rotulo: "Busca", valor: q, limpar: () => set({ q: null }) }] : []),
    ...(perfilId ? [{ chave: "perfil", rotulo: "Perfil", valor: nomePerfil, limpar: () => set({ perfil: null }) }] : []),
    ...(situacaoUrl
      ? [
          {
            chave: "situacao",
            rotulo: "Situação",
            valor: situacaoUrl === TODAS ? "Todas" : (situacaoAnotacaoLabel[situacaoUrl as AnotacaoSituacao] ?? situacaoUrl),
            limpar: () => set({ situacao: null }),
          },
        ]
      : []),
    ...(autorId ? [{ chave: "autor", rotulo: "Autor", valor: nomeAutor, limpar: () => set({ autor: null }), mais: true }] : []),
    ...(tipo ? [{ chave: "tipo", rotulo: "Tipo", valor: tipoAnotacaoLabel[tipo as AnotacaoTipo] ?? tipo, limpar: () => set({ tipo: null }), mais: true }] : []),
  ];

  // Caixa padrão (só abertas) vazia: alguma proposta já chegou? Decide entre os dois vazios.
  const padraoVazio = ativos.length === 0 && anotacoes.isSuccess && (itens?.length ?? 0) === 0;
  const algumaJaChegou = useQuery({
    queryKey: ["anotacoes", "alguma"],
    queryFn: () => api.anotacoes.list({ limit: 1 }),
    enabled: padraoVazio,
    select: (r) => r.anotacoes.length > 0,
  });

  const vazio =
    ativos.length > 0 ? (
      <EmptyState
        titulo="Nenhuma proposta com estes filtros"
        acao={
          <Button size="sm" variant="outline" onClick={limpar}>
            Limpar filtros
          </Button>
        }
      />
    ) : algumaJaChegou.data ? (
      <EmptyState
        titulo="Nenhuma proposta aberta"
        descricao="As propostas já aplicadas, descartadas ou arquivadas ficam em Situação: Todas."
        acao={
          <Button size="sm" variant="outline" onClick={() => set({ situacao: TODAS })}>
            Ver todas
          </Button>
        }
      />
    ) : (
      <EmptyState
        titulo="Ainda não chegou nenhuma proposta"
        descricao="Propostas são sugestões dos agentes da agência (OpenClaw). Elas só chegam depois que os agentes forem ligados ao SociMan pelo MCP, e nada muda até alguém aplicar."
        acao={
          isOwner && (
            <Button size="sm" asChild>
              <Link to="/app/configuracoes/agentes">Configurar agentes (MCP)</Link>
            </Button>
          )
        }
      />
    );

  return (
    <Page>
      <PageHeading
        title="Propostas dos agentes"
        description="Anotações e propostas de texto gravadas pelos agentes nos itens. Aplique ou descarte no próprio item: nada muda sem o seu clique."
      />
      <HeaderCard title="Caixa de propostas" description="Da mais nova para a mais antiga">
        {anotacoes.isError && <ApiErrorAlert error={anotacoes.error} />}
        <DataTable
          label="Propostas dos agentes"
          columns={columns}
          data={itens}
          loading={anotacoes.isPending || (padraoVazio && algumaJaChegou.isPending)}
          getRowId={(a) => a.id}
          toolbar={
            <FilterBar
              busca={{ valor: q, onChange: (v) => set({ q: v || null }, { replace: true }), placeholder: "Buscar no texto das propostas" }}
              principais={
                <>
                  <Field label="Perfil" className="w-full sm:w-48">
                    {({ id }) => (
                      <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value || null })}>
                        <option value="">Todos</option>
                        {perfis.data?.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <Field label="Situação" className="w-full sm:w-40">
                    {({ id }) => (
                      <NativeSelect
                        id={id}
                        value={situacao}
                        onChange={(e) => set({ situacao: e.target.value === SITUACAO_PADRAO ? null : e.target.value })}
                      >
                        <option value={TODAS}>Todas</option>
                        {(Object.keys(situacaoAnotacaoLabel) as AnotacaoSituacao[]).map((s) => (
                          <option key={s} value={s}>
                            {situacaoAnotacaoLabel[s]}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                </>
              }
              mais={
                <>
                  <Field label="Autor">
                    {({ id }) => (
                      <NativeSelect id={id} value={autorId} onChange={(e) => set({ autor: e.target.value || null })}>
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
                      <NativeSelect id={id} value={tipo} onChange={(e) => set({ tipo: e.target.value || null })}>
                        <option value="">Todos</option>
                        {(Object.keys(tipoAnotacaoLabel) as AnotacaoTipo[]).map((t) => (
                          <option key={t} value={t}>
                            {tipoAnotacaoLabel[t]}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                </>
              }
              ativos={ativos}
              onLimpar={limpar}
            />
          }
          empty={vazio}
          pagination={{
            hasMore: anotacoes.hasNextPage,
            onLoadMore: () => void anotacoes.fetchNextPage(),
            loadingMore: anotacoes.isFetchingNextPage,
          }}
        />
      </HeaderCard>
    </Page>
  );
}
