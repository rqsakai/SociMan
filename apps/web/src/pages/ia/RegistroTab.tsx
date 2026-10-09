/*
 * Aba "Registro" do assistente de IA (spec 008, US3; só o dono): as chamadas, mais recentes primeiro,
 * com filtros por perfil, tipo de campo, desfecho e período (datas no horário de Brasília) e
 * paginação por cursor. "Ver" abre a chamada num Sheet: instrução, entrada, proposta, explicação,
 * avisos, aceitos/rejeitados/aplicados nas sugestões, erro, modelo e tokens. Inclui as da 006.
 * Spec 017: as versões dos guias usadas (com link para cada guia), o rascunho do "Testar guia" e as
 * palavras proibidas que ficaram na proposta.
 * Spec 024: os filtros ficam na URL com o prefixo `reg_` (a tela tem abas) e valem ao mudar.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api } from "../../lib/api";
import { useFiltroUrl } from "../../lib/filtros";
import { emojisLabel, exemploTipoLabel, guiaContaPath, guiaPerfilPath } from "../../lib/guia";
import {
  custoText,
  desfechoLabel,
  desfechoTone,
  iaChamadasKey,
  iaTiposQuery,
  type IaChamada,
  type IaChamadaFilters,
  type IaDesfecho,
  type IaValor,
  type TipoCampoId,
} from "../../lib/ia";
import { formatDateTime } from "../../lib/tz";
import { usePerfisAtivos } from "../../lib/usePerfis";

const col = dataTableColumns<IaChamada>();

// "2026-10-07" → "07/10/2026" (etiqueta do filtro)
const diaText = (dia: string) => dia.split("-").reverse().join("/");

export function RegistroTab({ chamadaInicial }: { chamadaInicial: string | null }) {
  const perfis = usePerfisAtivos();
  const tipos = useQuery(iaTiposQuery);
  const [params, set] = useFiltroUrl("reg_");
  const perfilId = params.get("perfil") ?? "";
  const tipoCampo = params.get("campo") ?? "";
  const desfecho = (params.get("desfecho") ?? "") as IaDesfecho | "";
  const de = params.get("de") ?? "";
  const ate = params.get("ate") ?? "";
  const [aberta, setAberta] = useState<string | null>(chamadaInicial);

  const filters: IaChamadaFilters = {
    ...(perfilId ? { perfilId } : {}),
    ...(tipoCampo ? { tipoCampo: tipoCampo as TipoCampoId } : {}),
    ...(desfecho ? { desfecho: desfecho as IaDesfecho } : {}),
    ...(de ? { de } : {}),
    ...(ate ? { ate } : {}),
  };
  const chamadas = useInfiniteQuery({
    queryKey: iaChamadasKey(filters),
    queryFn: ({ pageParam }) => api.ia.chamadas({ ...filters, limit: 50, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: "",
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  const items = chamadas.data?.pages.flatMap((p) => p.items);
  const rotulo = (id: string) => tipos.data?.items.find((t) => t.id === id)?.rotulo ?? id;

  const columns = useMemo(
    () =>
      col.columns([
        col.accessor("createdAt", { header: "Quando", cell: (c) => formatDateTime(c.getValue()) }),
        col.display({ id: "autor", header: "Autor", cell: (c) => c.row.original.createdBy?.name ?? "—" }),
        col.display({
          id: "perfil",
          header: "Perfil",
          meta: { className: "hidden md:table-cell" },
          cell: (c) => c.row.original.perfil.name,
        }),
        col.accessor("tipoCampo", { header: "Campo", cell: (c) => rotulo(c.getValue()) }),
        col.accessor("desfecho", {
          header: "Desfecho",
          cell: (c) => <Badge className={desfechoTone[c.getValue()]}>{desfechoLabel[c.getValue()]}</Badge>,
        }),
        col.accessor("durationMs", {
          header: "Duração",
          meta: { className: "hidden sm:table-cell text-muted-foreground" },
          cell: (c) => `${(c.getValue() / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`,
        }),
        col.accessor("custoUsd", { header: "Custo", cell: (c) => custoText(c.getValue()) }),
        col.display({
          id: "ver",
          header: "",
          cell: (c) => (
            <Button type="button" variant="ghost" size="sm" aria-label="Ver a chamada" onClick={() => setAberta(c.row.original.id)}>
              <Eye aria-hidden="true" />
              Ver
            </Button>
          ),
        }),
      ]),
    // `rotulo` muda quando os tipos carregam.
    [tipos.data],
  );

  const doCache = items?.find((c) => c.id === aberta);
  const ativos: FiltroAtivo[] = [
    ...(perfilId
      ? [{ chave: "perfil", rotulo: "Perfil", valor: perfis.data?.find((p) => p.id === perfilId)?.name ?? "…", limpar: () => set({ perfil: null }) }]
      : []),
    ...(tipoCampo ? [{ chave: "campo", rotulo: "Tipo de campo", valor: rotulo(tipoCampo), limpar: () => set({ campo: null }) }] : []),
    ...(desfecho ? [{ chave: "desfecho", rotulo: "Desfecho", valor: desfechoLabel[desfecho] ?? desfecho, limpar: () => set({ desfecho: null }) }] : []),
    ...(de ? [{ chave: "de", rotulo: "De", valor: diaText(de), limpar: () => set({ de: null }), mais: true }] : []),
    ...(ate ? [{ chave: "ate", rotulo: "Até", valor: diaText(ate), limpar: () => set({ ate: null }), mais: true }] : []),
  ];

  return (
    <HeaderCard title="Registro das chamadas" description="Cada geração, com o desfecho e o custo aproximado.">
      {chamadas.isError ? (
        <ApiErrorAlert error={chamadas.error} />
      ) : (
        <DataTable
          label="Chamadas ao assistente de IA"
          columns={columns}
          data={items}
          loading={chamadas.isPending}
          getRowId={(c) => c.id}
          emptyMessage="Nenhuma chamada com esses filtros."
          toolbar={
            <FilterBar
              principais={
                <>
                  <Field label="Perfil" className="w-full sm:w-52">
                    {({ id }) => (
                      <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value })}>
                        <option value="">Todos</option>
                        {perfis.data?.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <Field label="Tipo de campo" className="w-full sm:w-56">
                    {({ id }) => (
                      <NativeSelect id={id} value={tipoCampo} onChange={(e) => set({ campo: e.target.value })}>
                        <option value="">Todos</option>
                        {tipos.data?.items.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.rotulo}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <Field label="Desfecho" className="w-full sm:w-40">
                    {({ id }) => (
                      <NativeSelect id={id} value={desfecho} onChange={(e) => set({ desfecho: e.target.value })}>
                        <option value="">Todos</option>
                        {(Object.keys(desfechoLabel) as IaDesfecho[]).map((d) => (
                          <option key={d} value={d}>
                            {desfechoLabel[d]}
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
                    {({ id }) => <DateField id={id} value={de} onChange={(iso) => set({ de: iso || null })} />}
                  </Field>
                  <Field label="Até">
                    {({ id }) => <DateField id={id} value={ate} onChange={(iso) => set({ ate: iso || null })} />}
                  </Field>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ perfil: null, campo: null, desfecho: null, de: null, ate: null })}
            />
          }
          pagination={{
            hasMore: Boolean(chamadas.hasNextPage),
            onLoadMore: () => void chamadas.fetchNextPage(),
            loadingMore: chamadas.isFetchingNextPage,
          }}
        />
      )}
      <ChamadaSheet id={aberta} inicial={doCache} rotulo={rotulo} onClose={() => setAberta(null)} />
    </HeaderCard>
  );
}

function ChamadaSheet({
  id,
  inicial,
  rotulo,
  onClose,
}: {
  id: string | null;
  inicial: IaChamada | undefined;
  rotulo: (id: string) => string;
  onClose: () => void;
}) {
  const detalhe = useQuery({
    queryKey: ["ia-chamada", id],
    queryFn: () => api.ia.chamada(id!),
    enabled: id !== null && !inicial,
  });
  const c = inicial ?? detalhe.data?.chamada;
  return (
    <Sheet open={id !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{c ? rotulo(c.tipoCampo) : "Chamada"}</SheetTitle>
          <SheetDescription>
            {c ? `${c.createdBy?.name ?? "—"} · ${formatDateTime(c.createdAt)} · ${c.perfil.name}` : "Carregando…"}
          </SheetDescription>
        </SheetHeader>
        {detalhe.isError && <ApiErrorAlert error={detalhe.error} className="mx-4" />}
        {c && (
          <dl className="space-y-4 px-4 pb-6 text-sm">
            <Item titulo="Desfecho">
              <Badge className={desfechoTone[c.desfecho]}>{desfechoLabel[c.desfecho]}</Badge>
              {c.desfechoEm && (
                <span className="ml-2 text-muted-foreground">
                  {c.desfechoPor?.name ?? ""} · {formatDateTime(c.desfechoEm)}
                  {c.aplicadaVersao ? ` · versão ${c.aplicadaVersao}` : ""}
                </span>
              )}
            </Item>
            <Item titulo="Instrução">{c.instrucao || <span className="text-muted-foreground italic">(sem instrução)</span>}</Item>
            <Item titulo="Entrada">
              <Valor v={c.entrada} />
            </Item>
            <Item titulo="Proposta">
              <Valor v={c.proposta} />
            </Item>
            {c.explicacao && <Item titulo="Explicação">{c.explicacao}</Item>}
            <GuiaDaChamada c={c} onNavigate={onClose} />
            <DesempenhoDaChamada c={c} onNavigate={onClose} />
            {c.proibidas.length > 0 && <Item titulo="Palavras proibidas na proposta">{c.proibidas.join(" · ")}</Item>}
            {c.avisos.length > 0 && <Item titulo="Avisos">{c.avisos.join(" · ")}</Item>}
            {c.contextoFaltante.length > 0 && <Item titulo="Contexto que faltou">{c.contextoFaltante.join(", ")}</Item>}
            {c.aceitos.length > 0 && <Item titulo="Aceitos enviados">{c.aceitos.join(" · ")}</Item>}
            {c.rejeitados.length > 0 && <Item titulo="Rejeitados enviados">{c.rejeitados.join(" · ")}</Item>}
            {c.itensAplicados && c.itensAplicados.length > 0 && <Item titulo="Itens que entraram no kit">{c.itensAplicados.join(" · ")}</Item>}
            {c.erroCode && <Item titulo="Erro">{c.erroCode}</Item>}
            <Item titulo="Modelo">
              {c.modelServido ?? c.model}
              {c.modelServido && c.modelServido !== c.model ? ` (pedido: ${c.model})` : ""} · regras v{c.regrasVersion}
            </Item>
            <Item titulo="Tokens e custo">
              entrada {c.inputTokens ?? "—"} · saída {c.outputTokens ?? "—"} · cache lido {c.cacheReadTokens ?? "—"} · cache escrito{" "}
              {c.cacheCreationTokens ?? "—"} · {custoText(c.custoUsd)} · {(c.durationMs / 1000).toLocaleString("pt-BR")} s
            </Item>
          </dl>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Item({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-semibold text-muted-foreground uppercase">{titulo}</dt>
      <dd className="break-words whitespace-pre-wrap">{children}</dd>
    </div>
  );
}

// "Guia do perfil vN · Guia da conta vM" (SC-003); no "Testar guia", qual nível veio do formulário.
function GuiaDaChamada({ c, onNavigate }: { c: IaChamada; onNavigate: () => void }) {
  const vp = c.guiaPerfilVersion;
  const vc = c.guiaContaVersion;
  if (vp == null && vc == null && !c.guiaRascunho) return null;
  const contaId = c.alvo.contaId;
  return (
    <Item titulo="Guia usado">
      {vp != null && (
        <Link to={guiaPerfilPath(c.perfil.id)} className="text-primary underline-offset-4 hover:underline" onClick={onNavigate}>
          Guia do perfil v{vp}
        </Link>
      )}
      {vp != null && vc != null && " · "}
      {vc != null &&
        (contaId ? (
          <Link to={guiaContaPath(contaId)} className="text-primary underline-offset-4 hover:underline" onClick={onNavigate}>
            Guia da conta v{vc}
          </Link>
        ) : (
          `Guia da conta v${vc}`
        ))}
      {c.guiaRascunho && (
        <span className="block text-muted-foreground">
          Testado com o rascunho {c.guiaRascunho === "perfil" ? "do perfil" : "da conta"} (não salvo)
        </span>
      )}
    </Item>
  );
}

// spec 023: "Desempenho: perfil vN, conta vM, K exemplos" (SC-007) ou "sem bloco de desempenho",
// só nos tipos que recebem o bloco <desempenho> (postagem.* e guia.testar).
function DesempenhoDaChamada({ c, onNavigate }: { c: IaChamada; onNavigate: () => void }) {
  if (!c.tipoCampo.startsWith("postagem.") && c.tipoCampo !== "guia.testar") return null;
  const vp = c.desempenhoPerfilVersion;
  const vc = c.desempenhoContaVersion;
  if (vp == null && vc == null) {
    return (
      <Item titulo="Desempenho">
        <span className="text-muted-foreground">sem bloco de desempenho</span>
      </Item>
    );
  }
  const exemplos = c.desempenhoExemplos ?? [];
  const n = exemplos.length;
  return (
    <Item titulo="Desempenho">
      <span data-desempenho>
        Desempenho: perfil v{vp ?? 0}, conta v{vc ?? 0}, {n} {n === 1 ? "exemplo" : "exemplos"}
      </span>
      {n > 0 && (
        <span className="block">
          {exemplos.map((id, i) => (
            <Link key={id} to={`/app/metricas/videos/${id}`} className="mr-2 text-primary underline-offset-4 hover:underline" onClick={onNavigate}>
              exemplo {i + 1}
            </Link>
          ))}
        </span>
      )}
    </Item>
  );
}

function Valor({ v }: { v: IaValor | null }) {
  if (!v) return <span className="text-muted-foreground">—</span>;
  const partes: string[] = [];
  if (v.texto !== undefined && v.texto !== null) partes.push(v.texto);
  if (v.titulo) partes.push(`Título: ${v.titulo}`);
  if (v.descricao) partes.push(`Descrição: ${v.descricao}`);
  if (v.hashtags && v.hashtags.length > 0) partes.push(v.hashtags.join(" "));
  if (v.itens && v.itens.length > 0) partes.push(v.itens.map((i) => `• ${i}`).join("\n"));
  // spec 017: guia (montar: proposta; testar: entrada) e as 3 variações do "Testar guia"
  if (v.guia) {
    const g = v.guia;
    const linhas: [string, string][] = [
      ["Tom", g.tom],
      ["Faça", (g.faca ?? []).join(" · ")],
      ["Não faça", (g.naoFaca ?? []).join(" · ")],
      ["Vocabulário", (g.vocabulario ?? []).join(" · ")],
      ["Proibidas", (g.proibidas ?? []).join(" · ")],
      ["Emojis", [g.emojis ? emojisLabel[g.emojis] : "", (g.emojisPreferidos ?? []).join(" ")].filter(Boolean).join(" · ")],
      ["Hashtags fixas", (g.hashtagsFixas ?? []).join(" ")],
      ["Exemplos", (g.exemplos ?? []).map((e) => `${exemploTipoLabel[e.tipo]}: ${e.texto}`).join(" | ")],
    ];
    partes.push(linhas.filter(([, x]) => x).map(([k, x]) => `${k}: ${x}`).join("\n"));
  }
  if (v.variacoes && v.variacoes.length > 0) {
    partes.push(v.variacoes.map((x, i) => `Variação ${i + 1}\n${x.titulo}\n${x.descricao}\n${x.hashtags.join(" ")}`).join("\n\n"));
  }
  return partes.length > 0 ? <>{partes.join("\n\n")}</> : <span className="text-muted-foreground italic">(vazio)</span>;
}
