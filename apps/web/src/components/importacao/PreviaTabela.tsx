/*
 * Pré-visualização da importação da agência (spec 013, US1/US2/US3; FR-008, FR-010, FR-014).
 *
 * - contagens por situação, MB novos no HD e os arquivos "não reconhecidos" (com o que faltou);
 * - tabela de todos os itens com filtros por perfil, tipo e situação: origem (arquivo, trecho e
 *   linha), situação com o motivo e, nos que divergem, os dois lados (<ItemDiverge>);
 * - escolhas do dono, linha a linha: marcar/desmarcar os novos, "Manter o SociMan × Usar o
 *   markdown" nos divergentes e o direito dos canais (<EscolhaDireito>);
 * - o perfil da persona da fábrica (um só, no topo do confirmar), quando a API não achou um padrão.
 *
 * As escolhas ficam na página (`escolhas`, só o que o dono mudou); aqui só se lê e se avisa.
 * Membro (`podeEscolher = false`) vê tudo sem os controles (na prática, só o dono gera a prévia).
 */
import { createContext, useContext, useMemo, useState } from "react";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, NativeSelect } from "@/components/ui/field";
import { useFiltroUrl } from "@/lib/filtros";
import {
  arquivoCurto,
  escolhaEfetiva,
  formatMB,
  situacaoLabel,
  textoMotivo,
  tipoLabel,
  type Direito,
  type Escolha,
  type ItemPrevia,
  type Previa,
  type Situacao,
  type TipoItem,
} from "@/lib/importacao";
import { ItemDiverge } from "./ItemDiverge";
import { EscolhaDireito } from "./EscolhaDireito";
import { SituacaoBadge } from "./SituacaoBadge";

interface Ctx {
  escolhas: Record<number, Escolha>;
  mudar: (n: number, e: Escolha) => void;
  podeEscolher: boolean;
}
const EscolhasCtx = createContext<Ctx>({ escolhas: {}, mudar: () => {}, podeEscolher: false });

// Nome legível do item: título, nome, @ ou bordão propostos; senão, o trecho de origem.
const nomeItem = (i: ItemPrevia) => {
  const p = i.proposto ?? {};
  const texto = (v: unknown) => (typeof v === "string" && v ? v : null);
  const handle = texto(p.handle);
  return (
    texto(p.titulo) ??
    texto(p.nome) ??
    (handle ? `@${handle}${texto(p.plataforma) ? ` (${p.plataforma})` : ""}` : null) ??
    texto(p.bordao) ??
    (i.origem.trecho || arquivoCurto(i.origem.arquivo))
  );
};

function Origem({ i }: { i: ItemPrevia }) {
  return (
    <span className="block text-xs break-all text-muted-foreground">
      {arquivoCurto(i.origem.arquivo)}
      {i.origem.linha ? `, linha ${i.origem.linha}` : ""}
      {i.origem.trecho && <span className="block break-words">§ {i.origem.trecho}</span>}
    </span>
  );
}

function CelulaItem({ i }: { i: ItemPrevia }) {
  return (
    <div className="min-w-40 whitespace-normal" data-item={i.n}>
      <span className="block font-medium break-words">{nomeItem(i)}</span>
      <span className="block text-xs text-muted-foreground">
        {tipoLabel[i.tipo]}
        {i.perfilSlug ? ` · ${i.perfilSlug}` : ""}
        {i.bytes ? ` · ${formatMB(i.bytes)}` : ""}
      </span>
      <span className="md:hidden">
        <Origem i={i} />
      </span>
    </div>
  );
}

function CelulaSituacao({ i }: { i: ItemPrevia }) {
  const motivo = textoMotivo(i.motivo, i.motivoTexto);
  return (
    <div className="min-w-44 space-y-2 whitespace-normal">
      <p className="flex flex-wrap items-center gap-1.5">
        <SituacaoBadge situacao={i.situacao} />
        {motivo && <span className="text-xs text-muted-foreground" data-motivo={i.motivo ?? undefined}>{motivo}</span>}
      </p>
      {i.situacao === "diverge" && <ItemDiverge atual={i.atual} proposto={i.proposto} />}
    </div>
  );
}

const direitoProposto = (i: ItemPrevia): Direito => {
  const d = i.proposto?.direito;
  return typeof d === "string" ? (d as Direito) : "sem_acordo";
};
const statusMarkdown = (i: ItemPrevia) => (typeof i.proposto?.statusMarkdown === "string" ? i.proposto.statusMarkdown : null);

function CelulaEscolha({ i }: { i: ItemPrevia }) {
  const { escolhas, mudar, podeEscolher } = useContext(EscolhasCtx);
  const e = escolhaEfetiva(i, escolhas);
  const nome = nomeItem(i);
  if (!podeEscolher) return <span className="text-xs text-muted-foreground">—</span>;

  if (i.situacao === "novo") {
    const marcado = e.marcado !== false;
    return (
      <div className="min-w-40 space-y-2 whitespace-normal">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={marcado} onCheckedChange={(v) => mudar(i.n, { marcado: v === true })} aria-label={`Importar ${nome}`} />
          Importar
        </label>
        {i.tipo === "canal" && (
          <EscolhaDireito
            rotulo={`Direito de ${nome}`}
            valor={e.direito ?? direitoProposto(i)}
            statusMarkdown={statusMarkdown(i)}
            disabled={!marcado}
            onChange={(d) => mudar(i.n, { direito: d })}
          />
        )}
      </div>
    );
  }
  if (i.situacao === "diverge") {
    const usar = e.usar ?? "sociman";
    return (
      <div className="min-w-40 space-y-2 whitespace-normal">
        <NativeSelect aria-label={`Escolha para ${nome}`} value={usar} onChange={(ev) => mudar(i.n, { usar: ev.target.value as "sociman" | "markdown" })}>
          <option value="sociman">Manter o SociMan</option>
          <option value="markdown">Usar o markdown</option>
        </NativeSelect>
        {i.tipo === "canal" && i.motivo === "direito" && usar === "markdown" && (
          <EscolhaDireito rotulo={`Direito de ${nome}`} valor={e.direito ?? direitoProposto(i)} statusMarkdown={statusMarkdown(i)} onChange={(d) => mudar(i.n, { direito: d })} />
        )}
      </div>
    );
  }
  return <span className="text-xs text-muted-foreground">—</span>;
}

const col = dataTableColumns<ItemPrevia>();
const columns = col.columns([
  col.accessor((i) => `${nomeItem(i)} ${tipoLabel[i.tipo]} ${i.perfilSlug ?? ""}`, {
    id: "item",
    header: "Item",
    enableSorting: false,
    cell: (c) => <CelulaItem i={c.row.original} />,
  }),
  col.accessor((i) => `${i.origem.arquivo} ${i.origem.trecho}`, {
    id: "origem",
    header: "Origem",
    enableSorting: false,
    meta: { className: "hidden md:table-cell min-w-48 max-w-72 whitespace-normal" },
    cell: (c) => <Origem i={c.row.original} />,
  }),
  col.accessor((i) => `${situacaoLabel[i.situacao]} ${textoMotivo(i.motivo, i.motivoTexto)}`, {
    id: "situacao",
    header: "Situação",
    enableSorting: false,
    cell: (c) => <CelulaSituacao i={c.row.original} />,
  }),
  col.display({ id: "escolha", header: "Escolha", cell: (c) => <CelulaEscolha i={c.row.original} /> }),
]);

const CONTAGENS: [keyof Previa["contagens"], string, Situacao | null][] = [
  ["novo", "Novos", "novo"],
  ["igual", "Iguais", "igual"],
  ["diverge", "Divergem", "diverge"],
  ["fora", "Fora", "fora"],
  ["aguardandoCota", "Aguardando cota", "aguardando_cota"],
  ["naoReconhecido", "Não reconhecidos", null],
];

export function PreviaTabela({
  previa,
  escolhas,
  onEscolha,
  podeEscolher,
  personaPerfil,
  onPersonaPerfil,
}: {
  previa: Previa;
  escolhas: Record<number, Escolha>;
  onEscolha: (n: number, e: Escolha) => void;
  podeEscolher: boolean;
  personaPerfil: string;
  onPersonaPerfil: (slug: string) => void;
}) {
  // filtros na URL (spec 024)
  const [params, set] = useFiltroUrl();
  const perfil = params.get("perfil") ?? "";
  const tipo = params.get("tipo") ?? "";
  const situacao = params.get("situacao") ?? "";
  const ativos: FiltroAtivo[] = [
    ...(perfil ? [{ chave: "perfil", rotulo: "Perfil", valor: perfil, limpar: () => set({ perfil: null }) }] : []),
    ...(tipo ? [{ chave: "tipo", rotulo: "Tipo", valor: tipoLabel[tipo as TipoItem] ?? tipo, limpar: () => set({ tipo: null }) }] : []),
    ...(situacao
      ? [{ chave: "situacao", rotulo: "Situação", valor: situacaoLabel[situacao as Situacao] ?? situacao, limpar: () => set({ situacao: null }) }]
      : []),
  ];

  const perfis = useMemo(() => [...new Set(previa.itens.map((i) => i.perfilSlug).filter((s): s is string => Boolean(s)))].sort(), [previa.itens]);
  const tipos = useMemo(() => [...new Set(previa.itens.map((i) => i.tipo))], [previa.itens]);
  const itens = useMemo(
    () => previa.itens.filter((i) => (!perfil || i.perfilSlug === perfil) && (!tipo || i.tipo === tipo) && (!situacao || i.situacao === situacao)),
    [previa.itens, perfil, tipo, situacao],
  );
  const ctx = useMemo(() => ({ escolhas, mudar: onEscolha, podeEscolher }), [escolhas, onEscolha, podeEscolher]);
  const aMao = previa.itens.filter((i) => i.tipo === "canal" && i.situacao === "fora");
  const sugestoes = previa.itens.filter((i) => i.situacao === "sugestao");

  return (
    <EscolhasCtx.Provider value={ctx}>
      <div className="space-y-4">
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-label="Contagens da leitura">
          {CONTAGENS.map(([chave, rotulo, sit]) => (
            <div key={chave} className="rounded-lg border p-2.5" data-contagem={chave}>
              <dt className="text-xs text-muted-foreground">{rotulo}</dt>
              <dd className="text-xl font-semibold tabular-nums">{previa.contagens[chave]}</dd>
              {sit && previa.contagens[chave] > 0 && (
                <button type="button" className="text-xs text-primary underline-offset-2 hover:underline" onClick={() => set({ situacao: sit })}>
                  ver
                </button>
              )}
            </div>
          ))}
        </dl>
        <p className="text-sm text-muted-foreground">
          Arquivos novos no HD: <span className="font-medium text-foreground">{formatMB(previa.bytesNovos)}</span>
        </p>

        {previa.arquivosNaoReconhecidos.length > 0 && (
          <Alert>
            <AlertTitle>Arquivos não reconhecidos</AlertTitle>
            <AlertDescription>
              <ul className="list-disc space-y-0.5 pl-4">
                {previa.arquivosNaoReconhecidos.map((a) => (
                  <li key={a.arquivo} className="break-all">
                    {arquivoCurto(a.arquivo)}: faltou {a.faltou.join(", ")}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {previa.persona && (
          <section className="space-y-2 rounded-lg border p-3" aria-labelledby="importacao-persona" data-persona>
            <h3 id="importacao-persona" className="text-sm font-semibold">
              Persona da fábrica
            </h3>
            {previa.persona.perfilPadrao ? (
              <p className="text-sm text-muted-foreground">
                Vai para o perfil <span className="font-medium text-foreground">{previa.persona.perfilPadrao}</span>, onde as imagens dela já estão.
              </p>
            ) : podeEscolher ? (
              <div className="max-w-xs space-y-1">
                <label htmlFor="importacao-persona-perfil" className="text-sm">
                  Em qual perfil a persona entra?
                </label>
                <NativeSelect id="importacao-persona-perfil" value={personaPerfil} onChange={(e) => onPersonaPerfil(e.target.value)}>
                  <option value="">Escolha o perfil</option>
                  {perfis.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </NativeSelect>
                <p className="text-xs text-muted-foreground">Sem perfil, desmarque os itens da persona para confirmar o resto.</p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Sem perfil definido.</p>
            )}
          </section>
        )}

        <DataTable
          label="Itens da leitura"
          columns={columns}
          data={itens}
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
                  <Field label="Situação" className="w-full sm:w-44">
                    {({ id }) => (
                      <NativeSelect id={id} aria-label="Filtrar por situação" value={situacao} onChange={(e) => set({ situacao: e.target.value })}>
                        <option value="">Todas as situações</option>
                        {(Object.keys(situacaoLabel) as Situacao[]).map((s) => (
                          <option key={s} value={s}>
                            {situacaoLabel[s]}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ perfil: null, tipo: null, situacao: null })}
            />
          }
        />

        {aMao.length > 0 && (
          <section className="space-y-2 rounded-lg border p-3" aria-labelledby="importacao-a-mao" data-fontes-a-mao>
            <h3 id="importacao-a-mao" className="text-sm font-semibold">
              Fontes para cadastrar à mão
            </h3>
            <p className="text-xs text-muted-foreground">Linhas do fontes.md sem canal do YouTube identificável. O texto original fica aqui para você cadastrar em Canais-fonte.</p>
            <ul className="space-y-1 text-sm">
              {aMao.map((i) => (
                <li key={i.n} className="break-words">
                  <span className="font-medium">{i.origem.trecho}</span>
                  {typeof i.proposto?.canal === "string" && i.proposto.canal && <span>: {i.proposto.canal}</span>}
                  <span className="text-xs text-muted-foreground">
                    {" "}
                    ({i.perfilSlug ?? arquivoCurto(i.origem.arquivo)}
                    {i.origem.linha ? `, linha ${i.origem.linha}` : ""}): {textoMotivo(i.motivo, i.motivoTexto)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {sugestoes.length > 0 && (
          <section className="space-y-2 rounded-lg border p-3" aria-labelledby="importacao-sugestoes" data-sugestoes>
            <h3 id="importacao-sugestoes" className="text-sm font-semibold">
              Sugestões de bordão
            </h3>
            <p className="text-xs text-muted-foreground">Expressões da casa que não estão no kit. A importação não muda o kit: se quiser, adicione no kit de marca do perfil.</p>
            <ul className="flex flex-wrap gap-1.5 text-sm">
              {sugestoes.map((i) => (
                <li key={i.n} className="rounded-full border px-2 py-0.5">
                  {nomeItem(i)}
                  {i.perfilSlug && <span className="text-xs text-muted-foreground"> · {i.perfilSlug}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </EscolhasCtx.Provider>
  );
}
