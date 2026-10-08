import { useQuery } from "@tanstack/react-query";
import { CircleAlert, Gauge, Loader2, Plus, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, Page, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { CanalForm } from "../../components/canais/CanalForm";
import { DireitoBadge } from "../../components/canais/DireitoBadge";
import { ProgressBar } from "../../components/marca/CorteStatusBadge";
import { api } from "../../lib/api";
import { canaisKey, formatCount, syncText, type CanalFonte } from "../../lib/canais";
import { useFiltroUrl } from "../../lib/filtros";
import { integracoesQuery, youtubeAviso } from "../../lib/integracoes";
import { formatTime } from "../../lib/tz";
import { usePerfisAtivos } from "../../lib/usePerfis";

const col = dataTableColumns<CanalFonte>();
const columns = col.columns([
  col.accessor("title", {
    header: "Canal",
    cell: (c) => {
      const canal = c.row.original;
      return (
        <Link to={`/app/fontes/${canal.id}`} className="flex min-w-0 items-center gap-3 hover:underline">
          {canal.avatarUrl ? (
            <img src={canal.avatarUrl} alt="" loading="lazy" className="size-9 shrink-0 rounded-full bg-muted object-cover" />
          ) : (
            <span className="tone-dark flex size-9 shrink-0 items-center justify-center rounded-full" aria-hidden="true">
              <Users className="size-4" />
            </span>
          )}
          <span className="min-w-0">
            <span className="block truncate font-semibold">{canal.title}</span>
            {canal.handle && <span className="block truncate text-xs text-muted-foreground">@{canal.handle.replace(/^@/, "")}</span>}
          </span>
        </Link>
      );
    },
  }),
  col.accessor("subscribers", {
    header: "Inscritos",
    enableGlobalFilter: false,
    cell: (c) => formatCount(c.getValue()),
    meta: { className: "hidden md:table-cell tabular-nums", headerClassName: "hidden md:table-cell" },
  }),
  col.accessor("videosConhecidos", {
    header: "Vídeos",
    enableGlobalFilter: false,
    cell: (c) => {
      const canal = c.row.original;
      return `${formatCount(c.getValue())}${canal.videoCount ? ` de ${formatCount(canal.videoCount)}` : ""}`;
    },
    meta: { className: "hidden sm:table-cell tabular-nums", headerClassName: "hidden sm:table-cell" },
  }),
  col.accessor("direito", {
    header: "Direito",
    cell: (c) => <DireitoBadge direito={c.getValue()} />,
  }),
  col.accessor((c) => c.perfis.map((p) => p.name).join(", "), {
    id: "perfis",
    header: "Perfis",
    cell: (c) => <span className="line-clamp-2 text-sm">{c.getValue() || "—"}</span>,
    meta: { className: "hidden lg:table-cell", headerClassName: "hidden lg:table-cell" },
  }),
  col.accessor((c) => syncText(c), {
    id: "sync",
    header: "Busca dos vídeos",
    enableGlobalFilter: false,
    cell: (c) => {
      const canal = c.row.original;
      const tone =
        canal.sync.status === "erro"
          ? "text-destructive"
          : canal.sync.status === "pausado_cota"
            ? "text-warning-foreground"
            : "text-muted-foreground";
      return (
        <span className={`inline-flex items-center gap-1 text-sm ${tone}`}>
          {(canal.sync.status === "sincronizando" || canal.sync.status === "pendente") && (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          )}
          {c.getValue()}
          {canal.archived && <Badge className="ml-1 bg-dark text-dark-foreground">Arquivado</Badge>}
        </span>
      );
    },
  }),
]);

const busySync = (c: CanalFonte) => c.sync.status === "pendente" || c.sync.status === "sincronizando";

// /app/fontes (spec 006, US1; T031): canais-fonte com avatar, inscritos, vídeos, selo de direito
// (aviso em "Sem acordo"), perfis e o estado da busca; "Adicionar canal"; a cota do YouTube (T073).
// A lista se atualiza a cada 5 s enquanto algum canal está buscando vídeos. Filtros na URL (spec 024):
// `q` (título ou @, no servidor), `perfil` e `arquivados`.
export default function CanaisList() {
  usePageMeta({ title: "Canais-fonte" });
  const [adding, setAdding] = useState(false);
  const [filtro, set] = useFiltroUrl();
  const q = filtro.get("q") ?? "";
  const perfilId = filtro.get("perfil") ?? "";
  const archived = filtro.get("arquivados") === "1";
  const perfis = usePerfisAtivos();
  const integracoes = useQuery(integracoesQuery);
  const aviso = youtubeAviso(integracoes.data);

  const params = useMemo(
    () => ({ archived, ...(perfilId ? { perfilId } : {}), ...(q ? { q } : {}) }),
    [archived, perfilId, q],
  );
  const canais = useQuery({
    queryKey: canaisKey(params),
    queryFn: () => api.canais.list(params),
    placeholderData: (previous) => previous,
    refetchInterval: (query) => (query.state.data?.items.some(busySync) ? 5000 : false),
  });

  const perfilNome = perfis.data?.find((p) => p.id === perfilId)?.name;
  const ativos: FiltroAtivo[] = [
    ...(q ? [{ chave: "q", rotulo: "Busca", valor: q, limpar: () => set({ q: null }) }] : []),
    ...(perfilId ? [{ chave: "perfil", rotulo: "Perfil", valor: perfilNome ?? "…", limpar: () => set({ perfil: null }) }] : []),
    ...(archived ? [{ chave: "arquivados", rotulo: "Só arquivados", valor: "sim", limpar: () => set({ arquivados: null }) }] : []),
  ];

  const cota = integracoes.data?.cotaYoutube;

  return (
    <Page>
      <PageHeading
        title="Canais-fonte"
        description="Canais do YouTube de onde saem os cortes. O SociMan busca todos os vídeos e recomenda quais cortar."
      />

      {aviso && (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{aviso.titulo}</AlertTitle>
          <AlertDescription>{aviso.texto}</AlertDescription>
        </Alert>
      )}

      {cota && (
        <section aria-label="Cota do YouTube" className="flex flex-wrap items-center gap-4 rounded-xl bg-card p-4 shadow-card">
          <span className="tone-info flex size-12 items-center justify-center rounded-lg" aria-hidden="true">
            <Gauge className="size-6" />
          </span>
          <div className="min-w-48 flex-1 space-y-1.5">
            <p className="text-sm font-semibold">Cota do YouTube hoje</p>
            <ProgressBar value={cota.limite ? cota.usadas / cota.limite : 0} label="Uso da cota do YouTube" />
          </div>
          <p className="text-sm">
            <strong className="tabular-nums">{formatCount(cota.usadas)}</strong> de {formatCount(cota.limite)} unidades · renova às{" "}
            {formatTime(cota.renovaEm)}
          </p>
        </section>
      )}

      <HeaderCard
        title="Canais"
        description="Selo amarelo: sem acordo registrado (a geração mostra o aviso de direito)."
        actions={
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            <Plus aria-hidden="true" />
            Adicionar canal
          </Button>
        }
      >
        {canais.isError ? (
          <ApiErrorAlert error={canais.error} />
        ) : (
          <DataTable
            label="Canais-fonte"
            columns={columns}
            data={canais.data?.items}
            loading={canais.isPending}
            getRowId={(c) => c.id}
            initialSorting={[{ id: "title", desc: false }]}
            emptyMessage={
              q || perfilId
                ? "Nenhum canal com estes filtros."
                : archived
                  ? "Nenhum canal arquivado."
                  : "Nenhum canal cadastrado. Clique em \"Adicionar canal\"."
            }
            toolbar={
              <FilterBar
                busca={{ valor: q, onChange: (v) => set({ q: v || null }, { replace: true }), placeholder: "Título ou @ do canal" }}
                principais={
                  <>
                    <Field label="Perfil" className="w-full sm:w-48">
                      {({ id }) => (
                        <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value || null })}>
                          <option value="">Todos os perfis</option>
                          {perfis.data?.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
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
                      Só arquivados
                    </label>
                  </>
                }
                ativos={ativos}
                onLimpar={() => set({ q: null, perfil: null, arquivados: null })}
              />
            }
          />
        )}
      </HeaderCard>

      <CanalForm open={adding} onOpenChange={setAdding} perfilIdInicial={perfilId || undefined} />
    </Page>
  );
}
