/*
 * AI Studio › Vídeos (spec 011, US1, T022; FR-051): os roteiros com vídeo local de todos os perfis
 * (`GET /api/roteiros`), com miniatura, nome, perfil, estado, produtos, cenas e data. Filtros na URL
 * (`perfil` base da 029, `q`, `status`, `arquivados=1`). "Novo vídeo" começa pela escolha do perfil
 * (o do filtro já vem escolhido).
 */
import { Plus, Video } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { PerfilBaseFiltro, usePerfilBaseAtivo } from "@/components/estudio/PerfilBaseFiltro";
import { PageHeading } from "@/components/PageHeading";
import { EmptyState, HeaderCard, Page, usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { perfilDoFiltro, usePerfilFiltro, usePerfisTodos, vazioDoPerfil } from "@/lib/estudio";
import { useFiltroUrl } from "@/lib/filtros";
import { etapaFalhouLabel, STATUS_ROTEIRO, statusRoteiroLabel, statusRoteiroTone, useRoteirosAgencia, type RoteiroResumo, type RoteiroStatus } from "@/lib/roteiros";
import { formatDateTime } from "@/lib/tz";

function colunas() {
  const col = dataTableColumns<RoteiroResumo>();
  return col.columns([
    col.accessor("nome", {
      header: "Vídeo",
      cell: (c) => {
        const r = c.row.original;
        return (
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-16 w-9 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
              {r.miniaturaUrl ? <img src={r.miniaturaUrl} alt="" loading="lazy" className="size-full object-cover" /> : <Video className="size-4 text-muted-foreground" aria-hidden="true" />}
            </span>
            <div className="min-w-0">
              <Link to={`/app/roteiros/${r.id}`} className="font-medium break-words underline-offset-2 hover:underline">
                {r.nome}
              </Link>
              {r.produtos.length > 0 && <p className="text-xs break-words text-muted-foreground">{r.produtos.join(" · ")}</p>}
            </div>
          </div>
        );
      },
    }),
    col.accessor((r) => r.perfilNome ?? "—", { id: "perfil", header: "Perfil", meta: { className: "hidden sm:table-cell" } }),
    col.accessor((r) => statusRoteiroLabel[r.status], {
      id: "status",
      header: "Estado",
      cell: (c) => {
        const r = c.row.original;
        return (
          <span className="flex flex-wrap gap-1">
            <Badge className={statusRoteiroTone[r.status]}>{c.getValue()}</Badge>
            {r.status === "falhou" && r.etapaFalhou && <span className="text-xs text-muted-foreground">em {etapaFalhouLabel[r.etapaFalhou]}</span>}
            {r.arquivado && <Badge className="bg-dark text-dark-foreground">Arquivado</Badge>}
          </span>
        );
      },
    }),
    col.accessor("cenas", {
      header: "Cenas",
      enableGlobalFilter: false,
      meta: { className: "hidden md:table-cell" },
      cell: (c) => <span className="tabular-nums">{c.getValue()}</span>,
    }),
    col.accessor("updatedAt", {
      header: "Alterado",
      enableGlobalFilter: false,
      meta: { className: "hidden lg:table-cell" },
      cell: (c) => (
        <time dateTime={c.getValue()} className="whitespace-nowrap">
          {formatDateTime(c.getValue())}
        </time>
      ),
    }),
  ]);
}

export default function RoteirosList() {
  const [perfil, setPerfil] = usePerfilFiltro();
  const [params, set] = useFiltroUrl();
  const q = params.get("q") ?? "";
  const status = (params.get("status") ?? "") as RoteiroStatus | "";
  const arquivados = params.get("arquivados") === "1";
  const perfilBase = perfilDoFiltro(perfil);
  const perfis = usePerfisTodos();
  const roteiros = useRoteirosAgencia(perfil, { q: q || undefined, status: status || undefined, arquivados });
  const itens = useMemo(() => roteiros.data?.pages.flatMap((p) => p.itens), [roteiros.data]);
  const columns = useMemo(() => colunas(), []);
  const ativosPerfil = usePerfilBaseAtivo(perfil, () => setPerfil("todos"));
  const ativos: FiltroAtivo[] = [
    ...ativosPerfil,
    ...(status ? [{ chave: "status", rotulo: "Estado", valor: statusRoteiroLabel[status] ?? status, limpar: () => set({ status: null }) }] : []),
    ...(arquivados ? [{ chave: "arquivados", rotulo: "Arquivados", valor: "mostrando", limpar: () => set({ arquivados: null }) }] : []),
  ];
  const novoHref = `/app/estudio/videos/novo${perfilBase ? `?perfil=${perfilBase}` : ""}`;
  const vazio = vazioDoPerfil(perfil, perfis.data);
  usePageMeta({ title: "Vídeos", breadcrumbs: [{ label: "AI Studio" }] });

  return (
    <Page>
      <PageHeading title="Vídeos" description="Roteiros com vídeo gerado no computador da casa: texto, narração, keyframes, clipes e o vídeo final." />
      <HeaderCard
        title="Biblioteca da agência"
        description="Cada vídeo é de um perfil; o vídeo final vira um conteúdo do perfil, sem destino aprovado."
        actions={
          <Button variant="secondary" size="sm" asChild>
            <Link to={novoHref}>
              <Plus aria-hidden="true" />
              Novo vídeo
            </Link>
          </Button>
        }
      >
        {roteiros.isError && <ApiErrorAlert error={roteiros.error} />}
        <DataTable
          label="Vídeos"
          columns={columns}
          data={itens}
          loading={roteiros.isPending}
          getRowId={(r) => r.id}
          empty={
            q || status ? (
              <EmptyState titulo="Nenhum vídeo com esses filtros." icone={Video} />
            ) : (
              <EmptyState
                titulo={`Nenhum vídeo${vazio.trecho} ainda.`}
                descricao={`Use "Novo vídeo" para criar o primeiro roteiro${vazio.criarComPerfil ? ": ele já começa com este perfil" : ""}.`}
                icone={Video}
              />
            )
          }
          toolbar={
            <FilterBar
              busca={{ valor: q, onChange: (v) => set({ q: v || null }, { replace: true }), rotulo: "Buscar vídeos", placeholder: "Nome ou brief" }}
              principais={
                <>
                  <PerfilBaseFiltro valor={perfil} onChange={setPerfil} rotulo="Perfil" semOpcaoSemPerfil />
                  <Field label="Estado" className="w-full sm:w-48">
                    {({ id }) => (
                      <NativeSelect id={id} value={status} onChange={(e) => set({ status: e.target.value })}>
                        <option value="">Todos</option>
                        {STATUS_ROTEIRO.map((st) => (
                          <option key={st} value={st}>
                            {statusRoteiroLabel[st]}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <label className="flex h-9 items-center gap-2 text-sm">
                    <Switch checked={arquivados} onCheckedChange={(on) => set({ arquivados: on ? "1" : null })} aria-label="Só arquivados" />
                    Só arquivados
                  </label>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ perfil: null, q: null, status: null, arquivados: null })}
            />
          }
          pagination={{ hasMore: roteiros.hasNextPage, onLoadMore: () => void roteiros.fetchNextPage(), loadingMore: roteiros.isFetchingNextPage }}
        />
      </HeaderCard>
    </Page>
  );
}
