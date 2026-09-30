/*
 * /app/conteudos (spec 014, US1–US5): todos os vídeos publicáveis de todos os perfis, num lugar só.
 *
 * - Atalhos com contagem no topo e filtros na URL (voltar, recarregar e compartilhar mantêm).
 * - Tabela paginada no servidor ("Carregar mais"): miniatura, título, perfil, origem, duração e um
 *   chip por conta de destino (estado efetivo e data). "Agendar" em cada linha.
 * - Seleção em lote: escolha a conta e use "Aprovar" (só dono), "Pedir aprovação", "Agendar em
 *   sequência", "Trocar horários" (dois agendados) e "Cancelar agendamento". O resultado mostra o
 *   que deu certo e o motivo de cada falha (uma falha não desfaz as outras).
 * - "Enviar vídeo próprio" no topo.
 */
import type { ConteudoItem, LoteResultado } from "@sociman/contract";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, CalendarClock, CalendarRange, CalendarX, Film, Hand, Loader2, ThumbsUp, Upload, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { AgendarDialog } from "@/components/conteudos/AgendarDialog";
import { AtalhosConteudos } from "@/components/conteudos/AtalhosConteudos";
import { DestinoChips } from "@/components/conteudos/DestinoChips";
import { FiltrosConteudos } from "@/components/conteudos/FiltrosConteudos";
import { SequenciaDialog } from "@/components/conteudos/SequenciaDialog";
import { VideoProprioDialog } from "@/components/conteudos/VideoProprioDialog";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { filtersFromParams, formatDuracao, invalidarConteudos, origemLabel, situacaoLabel, useConteudos, useEhDono } from "@/lib/conteudos";
import { contaPlatformText, perfilKey } from "@/lib/perfis";

const col = dataTableColumns<ConteudoItem>();

interface LoteVisto {
  titulo: string;
  resultado: LoteResultado;
  // "Manter mesmo assim" quando a falha é o intervalo mínimo (só no reagendar em lote).
  repetir?: () => Promise<void>;
}

export default function Conteudos() {
  usePageMeta({ title: "Conteúdos" });
  const queryClient = useQueryClient();
  const dono = useEhDono();
  const [params] = useSearchParams();
  const filters = useMemo(() => filtersFromParams(params), [params]);
  const lista = useConteudos(filters);
  const rows = useMemo(() => lista.data?.pages.flatMap((p) => p.items) ?? [], [lista.data]);
  const total = lista.data?.pages[0]?.total;

  const [selecionados, setSelecionados] = useState<Map<string, ConteudoItem>>(new Map());
  const [agendar, setAgendar] = useState<ConteudoItem | null>(null);
  const [videoOpen, setVideoOpen] = useState(false);

  function toggle(item: ConteudoItem) {
    setSelecionados((cur) => {
      const next = new Map(cur);
      if (next.has(item.id)) next.delete(item.id);
      else next.set(item.id, item);
      return next;
    });
  }
  const todosMarcados = rows.length > 0 && rows.every((r) => selecionados.has(r.id));

  const columns = useMemo(
    () =>
      col.columns([
        col.display({
          id: "sel",
          header: () => (
            <input
              type="checkbox"
              aria-label="Selecionar todos os carregados"
              className="size-4 accent-primary"
              checked={todosMarcados}
              onChange={(e) =>
                setSelecionados(e.target.checked ? new Map(rows.map((r) => [r.id, r])) : new Map())
              }
            />
          ),
          cell: (c) => (
            <input
              type="checkbox"
              aria-label={`Selecionar ${c.row.original.titulo || "conteúdo sem título"}`}
              className="size-4 accent-primary"
              checked={selecionados.has(c.row.original.id)}
              onChange={() => toggle(c.row.original)}
            />
          ),
          meta: { className: "w-8" },
        }),
        col.display({
          id: "miniatura",
          header: "",
          cell: (c) =>
            c.row.original.posterUrl ? (
              <img src={c.row.original.posterUrl} alt="" loading="lazy" className="h-16 w-9 rounded bg-muted object-cover" />
            ) : (
              <span className="flex h-16 w-9 items-center justify-center rounded bg-muted">
                <Film className="size-4 text-muted-foreground" aria-hidden="true" />
              </span>
            ),
          meta: { className: "w-12 py-2" },
        }),
        col.accessor("titulo", {
          header: "Conteúdo",
          cell: (c) => {
            const r = c.row.original;
            return (
              <div className="min-w-48">
                <Link to={`/app/conteudos/${r.id}`} className="line-clamp-2 font-semibold hover:underline">
                  {r.titulo || "Sem título"}
                </Link>
                <span className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                  {r.perfil.name}
                  {r.situacao !== "pronto" && (
                    <Badge variant="outline" className="text-[0.65rem]">
                      {situacaoLabel[r.situacao]}
                    </Badge>
                  )}
                  {r.archived && <Badge className="bg-dark text-[0.65rem] text-dark-foreground">Arquivado</Badge>}
                </span>
              </div>
            );
          },
        }),
        col.accessor("origem", {
          header: "Origem",
          cell: (c) => <span className="text-sm whitespace-nowrap">{origemLabel[c.getValue()]}</span>,
          meta: { className: "hidden md:table-cell", headerClassName: "hidden md:table-cell" },
        }),
        col.accessor("durationMs", {
          header: "Duração",
          cell: (c) => <span className="tabular-nums">{formatDuracao(c.getValue())}</span>,
          meta: { className: "hidden sm:table-cell", headerClassName: "hidden sm:table-cell" },
        }),
        col.display({
          id: "destinos",
          header: "Contas",
          cell: (c) => <DestinoChips conteudoId={c.row.original.id} destinos={c.row.original.destinos} />,
        }),
        col.display({
          id: "acoes",
          header: "",
          cell: (c) =>
            !c.row.original.archived && (
              <Button type="button" size="sm" variant="outline" onClick={() => setAgendar(c.row.original)} aria-label={`Agendar ${c.row.original.titulo || "conteúdo"}`}>
                <CalendarClock aria-hidden="true" />
                Agendar
              </Button>
            ),
          meta: { className: "text-right" },
        }),
      ]),
    [rows, selecionados, todosMarcados],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeading title="Conteúdos" description="Tudo o que pode ser publicado, com o estado em cada conta. Aprove, agende e acompanhe daqui." />
        <Button type="button" onClick={() => setVideoOpen(true)}>
          <Upload aria-hidden="true" />
          Enviar vídeo próprio
        </Button>
      </div>

      <AtalhosConteudos />
      <FiltrosConteudos />

      {selecionados.size > 0 && (
        <BarraLote
          itens={[...selecionados.values()]}
          dono={dono}
          onLimpar={() => setSelecionados(new Map())}
          onChanged={() => invalidarConteudos(queryClient)}
        />
      )}

      <HeaderCard title="Conteúdos" description={total === undefined ? undefined : `${total.toLocaleString("pt-BR")} no filtro`}>
        {lista.isError ? (
          <ApiErrorAlert error={lista.error} />
        ) : (
          <DataTable
            manual
            label="Conteúdos"
            columns={columns}
            data={rows}
            loading={lista.isPending}
            getRowId={(r) => r.id}
            isRowSelected={(r) => selecionados.has(r.id)}
            emptyMessage="Nenhum conteúdo neste filtro."
            pagination={{
              total,
              hasMore: Boolean(lista.hasNextPage),
              onLoadMore: () => void lista.fetchNextPage(),
              loadingMore: lista.isFetchingNextPage,
            }}
          />
        )}
      </HeaderCard>

      {agendar && (
        <AgendarDialog
          open
          onOpenChange={(o) => !o && setAgendar(null)}
          conteudo={{ id: agendar.id, perfilId: agendar.perfil.id, titulo: agendar.titulo, situacao: agendar.situacao }}
          destinos={agendar.destinos}
          contaId={params.get("conta")}
        />
      )}
      <VideoProprioDialog open={videoOpen} onOpenChange={setVideoOpen} perfilId={params.get("perfil") ?? undefined} />
    </div>
  );
}

// Barra de ações em lote (US2-5, US4): a conta vale para todas as ações da barra.
function BarraLote({
  itens,
  dono,
  onLimpar,
  onChanged,
}: {
  itens: ConteudoItem[];
  dono: boolean;
  onLimpar: () => void;
  onChanged: () => Promise<void>;
}) {
  const perfilIds = [...new Set(itens.map((i) => i.perfil.id))];
  const perfis = useQueries({
    queries: perfilIds.map((id) => ({ queryKey: perfilKey(id), queryFn: () => api.perfis.get(id) })),
  });
  const contas = perfis.flatMap((p) => p.data?.contas.filter((c) => !c.archived) ?? []);
  const [contaEscolhida, setContaId] = useState("");
  const contaId = contas.some((c) => c.id === contaEscolhida) ? contaEscolhida : (contas[0]?.id ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [visto, setVisto] = useState<LoteVisto | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [sequenciaOpen, setSequenciaOpen] = useState(false);

  const ids = itens.map((i) => i.id);
  const agendados = itens.flatMap((i) => i.destinos.filter((d) => d.conta.id === contaId && d.estado === "agendado"));
  const podeTrocar = itens.length === 2 && agendados.length === 2;

  async function lote(nome: string, titulo: string, fn: () => Promise<LoteResultado>, repetir?: () => Promise<void>) {
    setError(null);
    setBusy(nome);
    try {
      const resultado = await fn();
      setVisto({ titulo, resultado, repetir });
      if (resultado.falhas.length === 0) toast.success(`${titulo}: ${resultado.ok.length} ok.`);
      else toast.warning(`${titulo}: ${resultado.ok.length} ok, ${resultado.falhas.length} com falha.`);
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  function trocar(ignorarIntervalo = false): Promise<void> {
    const [a, b] = agendados as [(typeof agendados)[number], (typeof agendados)[number]];
    return lote(
      "trocar",
      "Trocar horários",
      () =>
        api.agendamentos.loteReagendar({
          itens: [
            { destinoId: a.id, version: a.version, plannedAt: b.plannedAt! },
            { destinoId: b.id, version: b.version, plannedAt: a.plannedAt! },
          ],
          ...(ignorarIntervalo ? { ignorarIntervalo } : {}),
        }),
      ignorarIntervalo ? undefined : () => trocar(true),
    );
  }

  const titulo = (id: string | null | undefined) => itens.find((i) => i.id === id || i.destinos.some((d) => d.id === id))?.titulo || "Item";
  const falhaIntervalo = visto?.resultado.falhas.some((f) => f.code === "intervalo_conflito");

  return (
    <section aria-label="Selecionados" className="sticky top-2 z-10 space-y-3 rounded-xl border border-primary/40 bg-card p-3 shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold">{itens.length} selecionado(s)</p>
        <NativeSelect aria-label="Conta" value={contaId} onChange={(e) => setContaId(e.target.value)} className="h-8 w-60 text-sm">
          {contas.length === 0 && <option value="">Sem contas ativas</option>}
          {contas.map((c) => (
            <option key={c.id} value={c.id}>
              {contaPlatformText(c)} @{c.handle}
              {perfilIds.length > 1 ? ` (${perfis.find((p) => p.data?.perfil.id === c.perfilId)?.data?.perfil.name ?? ""})` : ""}
            </option>
          ))}
        </NativeSelect>
        {dono && (
          <Button
            type="button"
            size="sm"
            disabled={!contaId || busy !== null}
            aria-busy={busy === "aprovar"}
            onClick={() => void lote("aprovar", "Aprovar", () => api.destinos.loteAprovar({ contaId, conteudoIds: ids }))}
          >
            {busy === "aprovar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ThumbsUp aria-hidden="true" />}
            Aprovar
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant={dono ? "outline" : "default"}
          disabled={!contaId || busy !== null}
          aria-busy={busy === "pedir"}
          onClick={() => void lote("pedir", "Pedir aprovação", () => api.destinos.lotePedirAprovacao({ contaId, conteudoIds: ids }))}
        >
          {busy === "pedir" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Hand aria-hidden="true" />}
          Pedir aprovação
        </Button>
        <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => setSequenciaOpen(true)}>
          <CalendarRange aria-hidden="true" />
          Agendar em sequência
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!podeTrocar || busy !== null}
          title={podeTrocar ? undefined : "Selecione dois conteúdos agendados nesta conta"}
          aria-busy={busy === "trocar"}
          onClick={() => void trocar()}
        >
          {busy === "trocar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ArrowLeftRight aria-hidden="true" />}
          Trocar horários
        </Button>
        <ConfirmButton
          label="Cancelar agendamento"
          icon={CalendarX}
          size="sm"
          disabled={agendados.length === 0}
          busy={busy === "cancelar"}
          title={`Cancelar ${agendados.length} agendamento(s)?`}
          description="Os conteúdos continuam aprovados nesta conta, sem data."
          onConfirm={() =>
            void lote("cancelar", "Cancelar agendamento", () =>
              api.agendamentos.loteCancelar({ itens: agendados.map((d) => ({ destinoId: d.id, version: d.version })) }),
            )
          }
        />
        <Button type="button" size="sm" variant="ghost" className="ml-auto" onClick={onLimpar}>
          <X aria-hidden="true" />
          Limpar seleção
        </Button>
      </div>
      {error !== null && <ApiErrorAlert error={error} />}
      {visto && (
        <Alert variant={visto.resultado.falhas.length > 0 ? "destructive" : "default"}>
          <AlertTitle>
            {visto.titulo}: {visto.resultado.ok.length} ok
            {visto.resultado.falhas.length > 0 ? `, ${visto.resultado.falhas.length} com falha` : ""}
          </AlertTitle>
          <AlertDescription>
            {visto.resultado.falhas.length > 0 && (
              <ul className="list-disc pl-5">
                {visto.resultado.falhas.map((f, i) => (
                  <li key={`${f.conteudoId ?? f.destinoId}-${i}`}>
                    {titulo(f.conteudoId ?? f.destinoId)}: {f.message}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              {falhaIntervalo && visto.repetir && (
                <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => void visto.repetir?.()}>
                  Manter mesmo assim
                </Button>
              )}
              <Button type="button" size="sm" variant="ghost" onClick={() => setVisto(null)}>
                Fechar
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}
      <SequenciaDialog
        open={sequenciaOpen}
        onOpenChange={setSequenciaOpen}
        itens={itens.map((i) => ({ id: i.id, titulo: i.titulo, perfilId: i.perfil.id }))}
      />
    </section>
  );
}

