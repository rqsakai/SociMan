import { useQuery } from "@tanstack/react-query";
import { CircleAlert, Gauge, Loader2, Plus, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/field";
import { CanalForm } from "../../components/canais/CanalForm";
import { DireitoBadge } from "../../components/canais/DireitoBadge";
import { ProgressBar } from "../../components/marca/CorteStatusBadge";
import { api } from "../../lib/api";
import { canaisKey, formatCount, syncText, type CanalFonte } from "../../lib/canais";
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
// A lista se atualiza a cada 5 s enquanto algum canal está buscando vídeos.
export default function CanaisList() {
  usePageMeta({ title: "Canais-fonte" });
  const [adding, setAdding] = useState(false);
  const [perfilId, setPerfilId] = useState("");
  const [archived, setArchived] = useState(false);
  const perfis = usePerfisAtivos();
  const integracoes = useQuery(integracoesQuery);
  const aviso = youtubeAviso(integracoes.data);

  const params = useMemo(() => ({ archived, ...(perfilId ? { perfilId } : {}) }), [archived, perfilId]);
  const canais = useQuery({
    queryKey: canaisKey(params),
    queryFn: () => api.canais.list(params),
    refetchInterval: (q) => (q.state.data?.items.some(busySync) ? 5000 : false),
  });

  const cota = integracoes.data?.cotaYoutube;

  return (
    <div className="flex flex-col gap-6">
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
        description="Selo amarelo: sem acordo registrado (o envio mostra o aviso de direito)."
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
            search={{ placeholder: "Filtrar canais" }}
            initialSorting={[{ id: "title", desc: false }]}
            emptyMessage={archived ? "Nenhum canal arquivado." : "Nenhum canal cadastrado. Clique em \"Adicionar canal\"."}
            toolbar={
              <>
                <NativeSelect aria-label="Perfil" value={perfilId} onChange={(e) => setPerfilId(e.target.value)} className="w-48">
                  <option value="">Todos os perfis</option>
                  {perfis.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </NativeSelect>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="size-4 accent-primary" checked={archived} onChange={(e) => setArchived(e.target.checked)} />
                  Só arquivados
                </label>
              </>
            }
          />
        )}
      </HeaderCard>

      <CanalForm open={adding} onOpenChange={setAdding} perfilIdInicial={perfilId || undefined} />
    </div>
  );
}
