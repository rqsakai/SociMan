/*
 * Aba "Registro" do assistente de IA (spec 008, US3; só o dono): as chamadas, mais recentes primeiro,
 * com filtros por perfil, tipo de campo, desfecho e período (datas no horário de Brasília) e
 * paginação por cursor. "Ver" abre a chamada num Sheet: instrução, entrada, proposta, explicação,
 * avisos, aceitos/rejeitados/aplicados nas sugestões, erro, modelo e tokens. Inclui as da 006.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api } from "../../lib/api";
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

export function RegistroTab({ chamadaInicial }: { chamadaInicial: string | null }) {
  const perfis = usePerfisAtivos();
  const tipos = useQuery(iaTiposQuery);
  const [perfilId, setPerfilId] = useState("");
  const [tipoCampo, setTipoCampo] = useState("");
  const [desfecho, setDesfecho] = useState("");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
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

  return (
    <HeaderCard title="Registro das chamadas" description="Cada geração, com o desfecho e o custo aproximado.">
      <div className="flex flex-wrap items-end gap-3 pb-4">
        <Field label="Perfil" className="w-full sm:w-52">
          {({ id }) => (
            <NativeSelect id={id} value={perfilId} onChange={(e) => setPerfilId(e.target.value)}>
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
            <NativeSelect id={id} value={tipoCampo} onChange={(e) => setTipoCampo(e.target.value)}>
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
            <NativeSelect id={id} value={desfecho} onChange={(e) => setDesfecho(e.target.value)}>
              <option value="">Todos</option>
              {(Object.keys(desfechoLabel) as IaDesfecho[]).map((d) => (
                <option key={d} value={d}>
                  {desfechoLabel[d]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="De" className="w-full sm:w-40">
          {({ id }) => <Input id={id} type="date" value={de} onChange={(e) => setDe(e.target.value)} />}
        </Field>
        <Field label="Até" className="w-full sm:w-40">
          {({ id }) => <Input id={id} type="date" value={ate} onChange={(e) => setAte(e.target.value)} />}
        </Field>
      </div>
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

function Valor({ v }: { v: IaValor | null }) {
  if (!v) return <span className="text-muted-foreground">—</span>;
  const partes: string[] = [];
  if (v.texto !== undefined && v.texto !== null) partes.push(v.texto);
  if (v.titulo) partes.push(`Título: ${v.titulo}`);
  if (v.descricao) partes.push(`Descrição: ${v.descricao}`);
  if (v.hashtags && v.hashtags.length > 0) partes.push(v.hashtags.join(" "));
  if (v.itens && v.itens.length > 0) partes.push(v.itens.map((i) => `• ${i}`).join("\n"));
  return partes.length > 0 ? <>{partes.join("\n\n")}</> : <span className="text-muted-foreground italic">(vazio)</span>;
}
