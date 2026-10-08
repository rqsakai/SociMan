/*
 * /app/envios (spec 006, US3; T054).
 * - Aba "Selecionados": os vídeos escolhidos, por perfil, com "Gerar cortes" (todos ou os
 *   marcados), "Descartar", "Colar link" e "Enviar arquivo".
 * - Aba "Gerações": status ao vivo ("Na fila (2º)", "Processando: 3 clipes prontos", "Importando
 *   4/6", "Pronto", "Sem clipes", "Falhou" com "Tentar de novo"; "Confirmar qualidade" com "Enviar
 *   mesmo assim"/"Descartar"), com polling de 5 s enquanto houver envio em andamento.
 * Perfil, aba e o status das gerações ficam na URL (?perfil=…&aba=envios&status=…).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Link2, Loader2, RotateCcw, Scissors, Trash2, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { DataTable, dataTableColumns, FilterBar } from "@/components/data-table";
import { PageHeading } from "@/components/PageHeading";
import { EmptyState, HeaderCard, Page, usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DireitoBadge } from "../../components/canais/DireitoBadge";
import { VideoThumb } from "../../components/canais/VideoCard";
import { ColarLinkDialog, EnviarArquivoDialog } from "../../components/envios/AvulsoDialogs";
import { EnviarDialog, envioDireito, envioTitulo } from "../../components/envios/EnviarDialog";
import { EnvioStatus } from "../../components/envios/EnvioStatus";
import { api } from "../../lib/api";
import { emAndamento, envioStatusLabel, enviosKey, origemLabel, type Envio, type EnvioStatus as Status } from "../../lib/envios";
import { useFiltroUrl } from "../../lib/filtros";
import { errorText } from "../../lib/perfis";
import { formatDateTime } from "../../lib/tz";
import { usePerfisAtivos } from "../../lib/usePerfis";

const ENVIOS_STATUS: Status[] = ["na_fila", "aguardando_openshorts", "confirmar_qualidade", "processando", "importando", "pronto", "sem_clipes", "falhou"];

export default function EnviosList() {
  usePageMeta({ title: "Geração de cortes" });
  const [params, setParams] = useSearchParams();
  const perfis = usePerfisAtivos();
  const perfilId = params.get("perfil") ?? "";
  const aba = params.get("aba") === "envios" ? "envios" : "selecionados";
  const set = (k: string, v: string) =>
    setParams(
      (cur) => {
        const next = new URLSearchParams(cur);
        if (v) next.set(k, v);
        else next.delete(k);
        return next;
      },
      { replace: true },
    );

  const perfilName = (id: string) => perfis.data?.find((p) => p.id === id)?.name ?? "Perfil";

  return (
    <Page>
      <PageHeading title="Geração de cortes" description="Dos vídeos selecionados ao SociShorts e de volta como cortes do perfil." />
      <Tabs value={aba} onValueChange={(v) => set("aba", v === "selecionados" ? "" : v)}>
        {/* spec 024 (T054): o Perfil vale para as duas abas e fica na linha delas, à direita */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <TabsList aria-label="Seções da geração de cortes">
            <TabsTrigger value="selecionados">Selecionados</TabsTrigger>
            <TabsTrigger value="envios">Gerações</TabsTrigger>
          </TabsList>
          <Field label="Perfil" className="w-full sm:w-72">
            {({ id }) => (
              <NativeSelect id={id} value={perfilId} onChange={(e) => set("perfil", e.target.value)}>
                <option value="">Todos os perfis</option>
                {perfis.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
        <TabsContent value="selecionados">
          <Selecionados perfilId={perfilId} perfilName={perfilName} perfisIds={perfis.data?.map((p) => p.id) ?? []} />
        </TabsContent>
        <TabsContent value="envios">
          <EnviosTabela perfilId={perfilId} perfilName={perfilName} />
        </TabsContent>
      </Tabs>
    </Page>
  );
}

function Selecionados({ perfilId, perfilName, perfisIds }: { perfilId: string; perfilName: (id: string) => string; perfisIds: string[] }) {
  const query = useQuery({
    queryKey: enviosKey({ perfilId: perfilId || undefined, status: ["selecionado"] }),
    queryFn: () => api.envios.list({ ...(perfilId ? { perfilId } : {}), status: ["selecionado"], limit: 100 }),
  });
  const grupos = useMemo(() => {
    const map = new Map<string, Envio[]>();
    for (const e of query.data?.items ?? []) map.set(e.perfilId, [...(map.get(e.perfilId) ?? []), e]);
    return [...map.entries()].sort(([a], [b]) => perfilName(a).localeCompare(perfilName(b), "pt-BR"));
  }, [query.data, perfilName]);

  if (query.isError) return <ApiErrorAlert error={query.error} />;
  if (query.isPending) return <p className="py-6 text-sm text-muted-foreground">Carregando…</p>;

  return (
    <Page>
      {perfilId && !grupos.some(([id]) => id === perfilId) && <GrupoSelecionados perfilId={perfilId} perfilName={perfilName(perfilId)} envios={[]} />}
      {grupos.map(([id, envios]) => (
        <GrupoSelecionados key={id} perfilId={id} perfilName={perfilName(id)} envios={envios} />
      ))}
      {!perfilId && grupos.length === 0 && (
        <EmptyState
          className="rounded-xl bg-card shadow-card"
          titulo="Nenhum vídeo selecionado."
          descricao={
            <>
              Escolha vídeos em{" "}
              <Link to="/app/descobrir" className="underline">
                Descobrir
              </Link>
              {perfisIds.length > 0 ? " ou escolha um perfil para colar um link ou enviar um arquivo." : "."}
            </>
          }
        />
      )}
    </Page>
  );
}

function GrupoSelecionados({ perfilId, perfilName, envios }: { perfilId: string; perfilName: string; envios: Envio[] }) {
  const queryClient = useQueryClient();
  const [marcados, setMarcados] = useState<string[]>([]);
  const [enviar, setEnviar] = useState<Envio[] | null>(null);
  const [link, setLink] = useState(false);
  const [arquivo, setArquivo] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const escolhidos = marcados.length > 0 ? envios.filter((e) => marcados.includes(e.id)) : envios;

  async function descartar(e: Envio) {
    setBusy(e.id);
    try {
      await api.envios.archive(e.id, e.version);
      toast.success("Descartado dos selecionados.");
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["envios"] }), queryClient.invalidateQueries({ queryKey: ["videos-fonte"] })]);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <HeaderCard
      title={perfilName}
      description={envios.length === 1 ? "1 vídeo selecionado" : `${envios.length} vídeos selecionados`}
      actions={
        <>
          <Button variant="secondary" size="sm" onClick={() => setLink(true)}>
            <Link2 aria-hidden="true" />
            Colar link
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setArquivo(true)}>
            <Upload aria-hidden="true" />
            Enviar arquivo
          </Button>
          <Button size="sm" className="bg-card text-card-foreground hover:bg-card/90" disabled={envios.length === 0} onClick={() => setEnviar(escolhidos)}>
            <Scissors aria-hidden="true" />
            {marcados.length > 0 ? `${marcados.length} ${marcados.length === 1 ? "selecionado" : "selecionados"} → Gerar cortes` : "Gerar cortes"}
          </Button>
        </>
      }
    >
      {envios.length === 0 ? (
        <EmptyState
          className="py-6"
          titulo="Nenhum vídeo selecionado para este perfil."
          acao={
            <Button variant="outline" size="sm" asChild>
              <Link to={`/app/descobrir?perfil=${perfilId}`}>Escolher em Descobrir</Link>
            </Button>
          }
        />
      ) : (
        <ul aria-label={`Selecionados de ${perfilName}`} className="divide-y">
          {envios.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-3 py-3">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                aria-label={`Marcar ${envioTitulo(e)}`}
                checked={marcados.includes(e.id)}
                onChange={() => setMarcados((m) => (m.includes(e.id) ? m.filter((x) => x !== e.id) : [...m, e.id]))}
              />
              {e.video ? <VideoThumb video={e.video} className="w-24" /> : null}
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2 text-sm font-semibold">{envioTitulo(e)}</p>
                <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>{e.canal?.title ?? origemLabel[e.origem]}</span>
                  <DireitoBadge direito={envioDireito(e)} />
                  <span>selecionado em {formatDateTime(e.createdAt)}</span>
                </p>
              </div>
              <Button type="button" variant="ghost" size="sm" disabled={busy !== null} aria-busy={busy === e.id} onClick={() => void descartar(e)} aria-label={`Descartar ${envioTitulo(e)}`}>
                {busy === e.id ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Trash2 aria-hidden="true" />}
                Descartar
              </Button>
            </li>
          ))}
        </ul>
      )}
      <EnviarDialog
        open={enviar !== null}
        onOpenChange={(open) => !open && setEnviar(null)}
        perfilId={perfilId}
        perfilName={perfilName}
        envios={enviar ?? []}
        onSent={() => setMarcados([])}
      />
      <ColarLinkDialog open={link} onOpenChange={setLink} perfilId={perfilId} />
      <EnviarArquivoDialog open={arquivo} onOpenChange={setArquivo} perfilId={perfilId} />
    </HeaderCard>
  );
}

function EnviosTabela({ perfilId, perfilName }: { perfilId: string; perfilName: (id: string) => string }) {
  const queryClient = useQueryClient();
  const [filtros, setFiltros] = useFiltroUrl();
  const statusUrl = filtros.get("status") ?? "";
  const status = (ENVIOS_STATUS as string[]).includes(statusUrl) ? (statusUrl as Status) : "";
  const [busy, setBusy] = useState<string | null>(null);
  const query = useQuery({
    queryKey: enviosKey({ perfilId: perfilId || undefined, status: status || "todos" }),
    queryFn: () => api.envios.list({ ...(perfilId ? { perfilId } : {}), status: status ? [status] : ENVIOS_STATUS, limit: 100 }),
    refetchInterval: (q) => (q.state.data?.items.some(emAndamento) ? 5000 : false),
  });

  async function act(e: Envio, kind: string, fn: () => Promise<unknown>, done: string) {
    setBusy(`${e.id}:${kind}`);
    try {
      await fn();
      toast.success(done);
      await queryClient.invalidateQueries({ queryKey: ["envios"] });
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  const col = dataTableColumns<Envio>();
  const columns = col.columns([
    col.accessor((e) => envioTitulo(e), {
      id: "video",
      header: "Vídeo",
      cell: (c) => {
        const e = c.row.original;
        return (
          <Link to={`/app/envios/${e.id}`} className="flex min-w-56 items-center gap-3 hover:underline">
            {e.video ? <VideoThumb video={e.video} className="w-20" /> : null}
            <span className="min-w-0">
              <span className="line-clamp-2 text-sm font-semibold">{c.getValue()}</span>
              <span className="block text-xs text-muted-foreground">{e.canal?.title ?? origemLabel[e.origem]}</span>
            </span>
          </Link>
        );
      },
      meta: { className: "whitespace-normal" },
    }),
    col.accessor((e) => perfilName(e.perfilId), {
      id: "perfil",
      header: "Perfil",
      meta: { className: "hidden md:table-cell", headerClassName: "hidden md:table-cell" },
    }),
    col.accessor("status", {
      header: "Status",
      cell: (c) => {
        const e = c.row.original;
        return (
          <div className="space-y-1">
            <EnvioStatus envio={e} />
            {e.errorMessage && (e.status === "falhou" || e.status === "sem_clipes" || e.status === "aguardando_openshorts") && (
              <p className="line-clamp-2 max-w-64 text-xs text-muted-foreground">{e.errorMessage}</p>
            )}
          </div>
        );
      },
    }),
    col.accessor((e) => e.sentAt ?? e.createdAt, {
      id: "data",
      header: "Iniciada em",
      enableGlobalFilter: false,
      cell: (c) => <time dateTime={c.getValue()}>{formatDateTime(c.getValue())}</time>,
      meta: { className: "hidden lg:table-cell whitespace-nowrap", headerClassName: "hidden lg:table-cell" },
    }),
    col.display({
      id: "acoes",
      header: "",
      cell: (c) => {
        const e = c.row.original;
        const b = (k: string) => busy === `${e.id}:${k}`;
        if (e.status === "confirmar_qualidade") {
          return (
            <div className="flex flex-wrap justify-end gap-2">
              <ConfirmButton
                label="Gerar mesmo assim"
                size="sm"
                busy={b("q")}
                title="Gerar mesmo com qualidade baixa?"
                description="O SociShorts avisou que o vídeo tem qualidade baixa. Os clipes podem sair piores."
                onConfirm={() => act(e, "q", () => api.envios.confirmarQualidade(e.id, { version: e.version, enviar: true }), "Geração retomada.")}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy !== null}
                onClick={() => void act(e, "d", () => api.envios.confirmarQualidade(e.id, { version: e.version, enviar: false }), "Geração descartada.")}
              >
                Descartar
              </Button>
            </div>
          );
        }
        if (e.status === "falhou") {
          return (
            <div className="flex justify-end">
              <Button type="button" variant="outline" size="sm" disabled={busy !== null} aria-busy={b("r")} onClick={() => void act(e, "r", () => api.envios.retry(e.id, e.version), "Geração de volta na fila.")}>
                {b("r") ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
                Tentar de novo
              </Button>
            </div>
          );
        }
        if (e.status === "pronto") {
          return (
            <div className="flex justify-end">
              <Button size="sm" asChild>
                <Link to={`/app/envios/${e.id}`}>
                  <Eye aria-hidden="true" />
                  Revisar clipes
                </Link>
              </Button>
            </div>
          );
        }
        return null;
      },
      meta: { className: "text-right" },
    }),
  ]);

  return (
    <HeaderCard title="Gerações" description="Atualiza sozinho enquanto há geração em andamento. O acompanhamento continua com o app fechado.">
      {query.isError ? (
        <ApiErrorAlert error={query.error} />
      ) : (
        <DataTable
          label="Gerações"
          columns={columns}
          data={query.data?.items}
          loading={query.isPending}
          getRowId={(e) => e.id}
          search={{ placeholder: "Buscar gerações", label: "Buscar" }}
          emptyMessage={status ? "Nenhuma geração com este status." : "Nenhuma geração ainda."}
          toolbar={
            // spec 024 (T054): a "Buscar" filtra as linhas carregadas (a tabela liga a busca da
            // barra); o status vai para a URL (?status=…)
            <FilterBar
              principais={
                <Field label="Status" className="w-full sm:w-52">
                  {({ id }) => (
                    <NativeSelect id={id} value={status} onChange={(e) => setFiltros({ status: e.target.value || null })}>
                      <option value="">Todos os status</option>
                      {ENVIOS_STATUS.map((s) => (
                        <option key={s} value={s}>
                          {envioStatusLabel[s]}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
              }
              ativos={status ? [{ chave: "status", rotulo: "Status", valor: envioStatusLabel[status], limpar: () => setFiltros({ status: null }) }] : []}
              onLimpar={() => setFiltros({ status: null })}
            />
          }
        />
      )}
    </HeaderCard>
  );
}
