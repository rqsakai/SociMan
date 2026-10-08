/*
 * Itens de uma importação da agência (spec 013, US2/US7): origem, situação lida, a escolha do dono,
 * o resultado (criado, atualizado, mantido, não gravado…) com o motivo, o link para a entidade e,
 * depois do desfazer, "desfeito" ou "não desfeito" com o motivo. Filtros por perfil, tipo e
 * resultado (na URL, spec 024).
 */
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Field, NativeSelect } from "@/components/ui/field";
import { useFiltroUrl } from "@/lib/filtros";
import {
  arquivoCurto,
  direitoLabel,
  entidadePath,
  resultadoLabel,
  textoMotivo,
  tipoLabel,
  type Escolha,
  type ItemImportacao,
  type Resultado,
  type TipoItem,
} from "@/lib/importacao";
import { formatDateTime } from "@/lib/tz";
import { SituacaoBadge } from "./SituacaoBadge";

function escolhaTexto(i: ItemImportacao): string {
  const e = (i.escolha ?? {}) as Escolha;
  const partes: string[] = [];
  if (e.marcado === false) partes.push("desmarcado");
  if (e.usar === "markdown") partes.push("usar o markdown");
  if (e.usar === "sociman") partes.push("manter o SociMan");
  if (e.direito) partes.push(`direito ${direitoLabel[e.direito]}`);
  return partes.join(" · ");
}

function Resultado({ i }: { i: ItemImportacao }) {
  const motivo = textoMotivo(i.resultadoMotivo, i.resultadoTexto);
  const desfazer = textoMotivo(i.desfazerMotivo, i.desfazerTexto);
  const path = i.entidade ? entidadePath(i.entidade) : null;
  return (
    <div className="min-w-40 space-y-1 whitespace-normal" data-resultado={i.resultado}>
      <p className="flex flex-wrap items-center gap-1.5">
        <Badge variant={i.resultado === "criado" || i.resultado === "atualizado" ? "default" : "secondary"}>{resultadoLabel[i.resultado]}</Badge>
        {motivo && <span className="text-xs text-muted-foreground">{motivo}</span>}
      </p>
      {i.entidade &&
        (path ? (
          <Link to={path} className="block text-xs text-primary underline-offset-2 hover:underline">
            Abrir {tipoLabel[i.tipo].toLowerCase()}
          </Link>
        ) : (
          null
        ))}
      {i.desfeitoEm && <span className="block text-xs text-muted-foreground">desfeito em {formatDateTime(i.desfeitoEm)}</span>}
      {desfazer && (
        <span className="block text-xs font-medium" data-nao-desfeito={i.desfazerMotivo ?? undefined}>
          não desfeito: {desfazer}
        </span>
      )}
    </div>
  );
}

const col = dataTableColumns<ItemImportacao>();
const columns = col.columns([
  col.accessor((i) => `${i.origem.trecho} ${tipoLabel[i.tipo]} ${i.perfilSlug ?? ""} `, {
    id: "item",
    header: "Item",
    enableSorting: false,
    cell: (c) => {
      const i = c.row.original;
      return (
        <div className="min-w-40 whitespace-normal" data-item={i.n}>
          <span className="block font-medium break-words">{i.origem.trecho || arquivoCurto(i.origem.arquivo)}</span>
          <span className="block text-xs text-muted-foreground">
            {tipoLabel[i.tipo]}
            {i.perfilSlug ? ` · ${i.perfilSlug}` : ""}
          </span>
          <span className="block text-xs break-all text-muted-foreground">
            {arquivoCurto(i.origem.arquivo)}
            {i.origem.linha ? `, linha ${i.origem.linha}` : ""}
          </span>
        </div>
      );
    },
  }),
  col.accessor((i) => `${i.situacao} ${escolhaTexto(i)}`, {
    id: "lido",
    header: "Leitura",
    enableSorting: false,
    meta: { className: "hidden sm:table-cell" },
    cell: (c) => {
      const i = c.row.original;
      const motivo = textoMotivo(i.motivo, i.motivoTexto);
      const escolha = escolhaTexto(i);
      return (
        <div className="min-w-32 space-y-1 whitespace-normal">
          <SituacaoBadge situacao={i.situacao} />
          {motivo && <span className="block text-xs text-muted-foreground">{motivo}</span>}
          {escolha && <span className="block text-xs">{escolha}</span>}
        </div>
      );
    },
  }),
  col.accessor((i) => resultadoLabel[i.resultado], {
    id: "resultado",
    header: "Resultado",
    enableSorting: false,
    cell: (c) => <Resultado i={c.row.original} />,
  }),
]);

export function ItensImportacao({ itens }: { itens: ItemImportacao[] }) {
  const [params, set] = useFiltroUrl();
  const perfil = params.get("perfil") ?? "";
  const tipo = params.get("tipo") ?? "";
  const resultado = params.get("resultado") ?? "";
  const perfis = useMemo(() => [...new Set(itens.map((i) => i.perfilSlug).filter((s): s is string => Boolean(s)))].sort(), [itens]);
  const tipos = useMemo(() => [...new Set(itens.map((i) => i.tipo))], [itens]);
  const filtrados = useMemo(
    () => itens.filter((i) => (!perfil || i.perfilSlug === perfil) && (!tipo || i.tipo === tipo) && (!resultado || i.resultado === resultado)),
    [itens, perfil, tipo, resultado],
  );
  const ativos: FiltroAtivo[] = [
    ...(perfil ? [{ chave: "perfil", rotulo: "Perfil", valor: perfil, limpar: () => set({ perfil: null }) }] : []),
    ...(tipo ? [{ chave: "tipo", rotulo: "Tipo", valor: tipoLabel[tipo as TipoItem] ?? tipo, limpar: () => set({ tipo: null }) }] : []),
    ...(resultado
      ? [{ chave: "resultado", rotulo: "Resultado", valor: resultadoLabel[resultado as Resultado] ?? resultado, limpar: () => set({ resultado: null }) }]
      : []),
  ];
  return (
    <DataTable
      label="Itens da importação"
      columns={columns}
      data={filtrados}
      getRowId={(i) => String(i.n)}
      initialPageSize={50}
      search={{ label: "Buscar item", placeholder: "Buscar item" }}
      emptyMessage="Nenhum item com estes filtros"
      toolbar={
        <FilterBar
          principais={
            <>
              <Field label="Perfil" className="w-full sm:w-44">
                {({ id }) => (
                  <NativeSelect id={id} aria-label="Filtrar por perfil" value={perfil} onChange={(e) => set({ perfil: e.target.value })}>
                    <option value="">Todos os perfis</option>
                    {perfis.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Field label="Tipo" className="w-full sm:w-44">
                {({ id }) => (
                  <NativeSelect id={id} aria-label="Filtrar por tipo" value={tipo} onChange={(e) => set({ tipo: e.target.value })}>
                    <option value="">Todos os tipos</option>
                    {tipos.map((t) => (
                      <option key={t} value={t}>
                        {tipoLabel[t as TipoItem]}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Field label="Resultado" className="w-full sm:w-44">
                {({ id }) => (
                  <NativeSelect id={id} aria-label="Filtrar por resultado" value={resultado} onChange={(e) => set({ resultado: e.target.value })}>
                    <option value="">Todos os resultados</option>
                    {(Object.keys(resultadoLabel) as Resultado[]).map((r) => (
                      <option key={r} value={r}>
                        {resultadoLabel[r]}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            </>
          }
          ativos={ativos}
          onLimpar={() => set({ perfil: null, tipo: null, resultado: null })}
        />
      }
    />
  );
}
