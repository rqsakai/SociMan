/*
 * Cenas da agência (spec 029, T017; antes a aba Cenas do perfil, 010 US2/FR-007): as tomadas para o
 * Flow/Veo de todos os perfis e sem perfil, com o perfil base de cada uma, filtros por perfil base,
 * status, avatar, cenário, produto e tag, busca por nome, ação, fala e produto, "Nova cena",
 * "Duplicar" e "Arquivadas". Com um perfil no filtro, também as propostas de cena dos agentes e os
 * "Padrões das cenas" desse perfil. Os filtros ficam na URL (`perfil`, `q`, `status`, `tag`,
 * `arquivadas=1`, `avatarId`, `cenarioId`, `produtoImagemId` e `produtoId`; o "onde é usado" dos
 * assets e dos produtos abre a lista já filtrada) e valem ao mudar.
 */
import type { Perfil } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Film, Loader2, Plus, Save } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PropostaCard } from "@/components/anotacoes/PropostaCard";
import { BUSCA_DEBOUNCE_MS } from "@/components/data-table/FilterBar";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAnotacoes } from "@/lib/anotacoes";
import {
  cenaPadroesKey,
  invalidarCena,
  LIM,
  modoCenaLabel,
  statusCenaLabel,
  statusCenaTone,
  useCenaPadroes,
  useCenasAgencia,
  type CenaFiltros,
  type CenaResumo,
  type CenaStatus,
} from "@/lib/cenas";
import { useFiltroUrl } from "@/lib/filtros";
import { assetKey } from "@/lib/assets";
import { perfilDoFiltro, perfilNomeDe, TETO_TEXTO, vazioDoPerfil, useAssetsOpcoes, usePerfisTodos, useProdutosOpcoes, type PerfilFiltro } from "@/lib/estudio";
import { formatDateTime } from "@/lib/tz";
import { PerfilBaseFiltro, usePerfilBaseAtivo } from "./PerfilBaseFiltro";

type AssetFiltro = "avatarId" | "cenarioId" | "produtoImagemId";

// O asset do filtro que não está nas opções (arquivado): o detalhe, só para o nome e o perfil.
function useAssetForaDasOpcoes(id: string, itens: { id: string }[] | undefined) {
  const fora = Boolean(id) && itens !== undefined && !itens.some((a) => a.id === id);
  const q = useQuery({ queryKey: assetKey(id), queryFn: () => api.assets.get(id), enabled: fora, retry: false });
  return fora ? q.data?.asset : undefined;
}

// Campo "Tag" em "Mais filtros": aplica 300 ms depois da última tecla, como a busca da barra.
function TagFiltro({ id, valor, onChange }: { id: string; valor: string; onChange: (v: string) => void }) {
  const [texto, setTexto] = useState(valor);
  const enviado = useRef(valor);
  useEffect(() => {
    enviado.current = valor;
    setTexto(valor);
  }, [valor]);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });
  useEffect(() => {
    const final = texto.trim().toLowerCase();
    if (final === enviado.current) return;
    const t = setTimeout(() => {
      enviado.current = final;
      onChangeRef.current(final);
    }, BUSCA_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [texto]);
  return <Input id={id} value={texto} maxLength={100} onChange={(e) => setTexto(e.target.value)} />;
}

function DuplicarBotao({ cena }: { cena: CenaResumo }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      disabled={busy}
      aria-busy={busy}
      aria-label={`Duplicar ${cena.nome}`}
      onClick={async () => {
        setBusy(true);
        try {
          const nova = await api.cenas.duplicar(cena.id);
          toast.success("Cena duplicada como rascunho.");
          await invalidarCena(queryClient, null);
          void navigate(`/app/cenas/${nova.id}`);
        } catch (err) {
          toast.error(err instanceof Error ? err.message : "Não foi possível duplicar.");
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Copy aria-hidden="true" />}
      <span className="hidden sm:inline">Duplicar</span>
    </Button>
  );
}

function Miniatura({ cena }: { cena: CenaResumo }) {
  return (
    <span className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
      {cena.thumbUrl ? <img src={cena.thumbUrl} alt="" loading="lazy" className="size-full object-cover" /> : <Film className="size-5 text-muted-foreground" aria-hidden="true" />}
    </span>
  );
}

function colunas(nomeProduto: (id: string) => string, nomePerfil: (c: CenaResumo) => string) {
  const col = dataTableColumns<CenaResumo>();
  return col.columns([
    col.accessor("nome", {
      header: "Cena",
      cell: (c) => {
        const cena = c.row.original;
        return (
          <div className="flex min-w-0 items-center gap-3">
            <Miniatura cena={cena} />
            <div className="min-w-0">
              <Link to={`/app/cenas/${cena.id}`} className="font-medium break-words underline-offset-2 hover:underline">
                {cena.nome}
              </Link>
              <p className="text-xs text-muted-foreground">
                {[cena.avatar?.nome, cena.cenario?.nome].filter(Boolean).join(" · ") || "Sem avatar nem cenário"}
              </p>
              {cena.tags.length > 0 && <p className="text-xs text-muted-foreground">{cena.tags.map((t) => `#${t}`).join(" ")}</p>}
            </div>
          </div>
        );
      },
    }),
    col.accessor((c) => nomePerfil(c), {
      id: "perfilBase",
      header: "Perfil base",
      meta: { className: "hidden sm:table-cell" },
      cell: (c) => <span className="whitespace-nowrap">{c.getValue()}</span>,
    }),
    col.accessor((c) => statusCenaLabel[c.status], {
      id: "status",
      header: "Status",
      cell: (c) => (
        <span className="flex flex-wrap gap-1">
          <Badge className={statusCenaTone[c.row.original.status]}>{c.getValue()}</Badge>
          {c.row.original.arquivada && <Badge className="bg-dark text-dark-foreground">Arquivada</Badge>}
        </span>
      ),
    }),
    col.accessor("duracaoS", {
      header: "Duração",
      enableGlobalFilter: false,
      meta: { className: "hidden md:table-cell" },
      cell: (c) => (
        <span className="whitespace-nowrap">
          {c.getValue()} s<span className="block text-xs text-muted-foreground">{modoCenaLabel[c.row.original.modo]}</span>
        </span>
      ),
    }),
    col.accessor((c) => (c.produtoId ? nomeProduto(c.produtoId) : (c.produtoNome ?? "")), {
      id: "produto",
      header: "Produto",
      meta: { className: "hidden md:table-cell" },
      cell: (c) => {
        const id = c.row.original.produtoId;
        if (!id) return c.getValue() || "—";
        return (
          <Link to={`/app/produtos/${id}`} className="underline-offset-2 hover:underline">
            {c.getValue()}
          </Link>
        );
      },
    }),
    col.accessor((c) => `${c.tomadas} / ${c.usos}`, {
      id: "tomadas",
      header: "Tomadas / usos",
      enableGlobalFilter: false,
      meta: { className: "hidden lg:table-cell" },
    }),
    col.accessor("updatedAt", {
      header: "Alterada",
      enableGlobalFilter: false,
      meta: { className: "hidden lg:table-cell" },
      cell: (c) => <time dateTime={c.getValue()} className="whitespace-nowrap">{formatDateTime(c.getValue())}</time>,
    }),
    col.display({ id: "acoes", header: "", cell: (c) => <DuplicarBotao cena={c.row.original} /> }),
  ]);
}

export function CenasLista({ perfilFiltro, onPerfilFiltro }: { perfilFiltro: PerfilFiltro; onPerfilFiltro: (v: PerfilFiltro) => void }) {
  const [params, set] = useFiltroUrl();
  const perfis = usePerfisTodos();
  const perfilBase = perfilDoFiltro(perfilFiltro);
  const perfil = perfis.data?.find((p) => p.id === perfilBase) ?? null;
  const q = params.get("q") ?? "";
  const status = (params.get("status") ?? "") as CenaStatus | "";
  const tag = params.get("tag") ?? "";
  const arquivadas = params.get("arquivadas") === "1";
  const ids: Record<AssetFiltro, string> = {
    avatarId: params.get("avatarId") ?? "",
    cenarioId: params.get("cenarioId") ?? "",
    produtoImagemId: params.get("produtoImagemId") ?? "",
  };
  const produtoId = params.get("produtoId") ?? "";
  const filtros: CenaFiltros = {
    q: q || undefined,
    status: status || undefined,
    avatarId: ids.avatarId || undefined,
    cenarioId: ids.cenarioId || undefined,
    produtoImagemId: ids.produtoImagemId || undefined,
    produtoId: produtoId || undefined,
    tag: tag || undefined,
    arquivadas: arquivadas || undefined,
  };
  const cenas = useCenasAgencia(perfilFiltro, filtros);
  const itens = useMemo(() => cenas.data?.pages.flatMap((p) => p.items), [cenas.data]);
  // Produtos do catálogo (spec 012): nomes da coluna e opções do filtro, inclusive fora de aprovado.
  // A agência inteira (todas as páginas até o teto), os do perfil do filtro primeiro.
  const produtos = useProdutosOpcoes("todos", perfilBase);
  const produtosLista = useMemo(() => produtos.itens ?? [], [produtos.itens]);
  const columns = useMemo(() => {
    const nomes = new Map(produtosLista.map((p) => [p.id, p.nomeComercial ?? p.name]));
    return colunas(
      (id) => nomes.get(id) ?? "Produto do catálogo",
      (c) => perfilNomeDe(c, perfis.data),
    );
  }, [produtosLista, perfis.data]);

  const avatares = useAssetsOpcoes("avatar", perfilBase);
  const cenarios = useAssetsOpcoes("cenario", perfilBase);
  const imagens = useAssetsOpcoes("imagem", perfilBase);
  const opcoesAsset = { avatarId: avatares, cenarioId: cenarios, produtoImagemId: imagens } as const;
  const rotulos: Record<AssetFiltro, string> = { avatarId: "Avatar", cenarioId: "Cenário", produtoImagemId: "Foto do produto" };
  // "Nome · Perfil" (ou "Nome · Sem perfil"), como no formulário da cena
  const comPerfil = (a: { name: string; perfilId?: string | null; perfilNome?: string | null }) => `${a.name} · ${perfilNomeDe(a, perfis.data)}`;
  // o filtro vindo da URL ("Onde é usado") pode ser de um asset arquivado, fora das opções: busca o nome
  const foraAvatar = useAssetForaDasOpcoes(ids.avatarId, avatares.itens);
  const foraCenario = useAssetForaDasOpcoes(ids.cenarioId, cenarios.itens);
  const foraImagem = useAssetForaDasOpcoes(ids.produtoImagemId, imagens.itens);
  const fora: Record<AssetFiltro, { name: string; perfilId?: string | null; perfilNome?: string | null } | undefined> = {
    avatarId: foraAvatar,
    cenarioId: foraCenario,
    produtoImagemId: foraImagem,
  };
  const nomeAsset = (key: AssetFiltro) => {
    const a = opcoesAsset[key].itens?.find((x) => x.id === ids[key]) ?? fora[key];
    return a ? comPerfil(a) : "Asset escolhido";
  };

  const selectAsset = (key: AssetFiltro, className?: string) => (
    <Field label={rotulos[key]} className={className} hint={opcoesAsset[key].truncado ? TETO_TEXTO : undefined}>
      {({ id, describedBy }) => (
        <NativeSelect id={id} value={ids[key]} aria-describedby={describedBy} onChange={(e) => set({ [key]: e.target.value })}>
          <option value="">Todos</option>
          {ids[key] && !opcoesAsset[key].itens?.some((a) => a.id === ids[key]) && <option value={ids[key]}>{nomeAsset(key)}</option>}
          {opcoesAsset[key].itens?.map((a) => (
            <option key={a.id} value={a.id}>
              {comPerfil(a)}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );

  const ativosPerfil = usePerfilBaseAtivo(perfilFiltro, () => onPerfilFiltro("todos"));
  const ativos: FiltroAtivo[] = [
    ...ativosPerfil,
    ...(status ? [{ chave: "status", rotulo: "Status", valor: statusCenaLabel[status] ?? status, limpar: () => set({ status: null }) }] : []),
    ...(ids.avatarId ? [{ chave: "avatarId", rotulo: "Avatar", valor: nomeAsset("avatarId"), limpar: () => set({ avatarId: null }) }] : []),
    ...(arquivadas ? [{ chave: "arquivadas", rotulo: "Arquivadas", valor: "mostrando", limpar: () => set({ arquivadas: null }) }] : []),
    ...(ids.cenarioId
      ? [{ chave: "cenarioId", rotulo: "Cenário", valor: nomeAsset("cenarioId"), limpar: () => set({ cenarioId: null }), mais: true }]
      : []),
    ...(ids.produtoImagemId
      ? [{ chave: "produtoImagemId", rotulo: "Foto do produto", valor: nomeAsset("produtoImagemId"), limpar: () => set({ produtoImagemId: null }), mais: true }]
      : []),
    ...(produtoId
      ? [
          {
            chave: "produtoId",
            rotulo: "Produto do catálogo",
            valor: (() => {
              const p = produtosLista.find((x) => x.id === produtoId);
              return p ? `${p.nomeComercial ?? p.name} · ${perfilNomeDe(p, perfis.data)}` : "Produto escolhido";
            })(),
            limpar: () => set({ produtoId: null }),
            mais: true,
          },
        ]
      : []),
    ...(tag ? [{ chave: "tag", rotulo: "Tag", valor: `#${tag}`, limpar: () => set({ tag: null }), mais: true }] : []),
  ];

  return (
    <>
      <HeaderCard
        title="Biblioteca da agência"
        description="Tomadas de até 8 s para gerar no Google Flow: avatar, cenário, ação, fala e o prompt pronto para copiar."
        actions={
          <Button variant="secondary" size="sm" asChild>
            <Link to={`/app/estudio/cenas/nova${perfilBase ? `?perfil=${perfilBase}` : ""}`}>
              <Plus aria-hidden="true" />
              Nova cena
            </Link>
          </Button>
        }
      >
        {cenas.isError && <ApiErrorAlert error={cenas.error} />}
        <DataTable
          label="Cenas"
          columns={columns}
          data={itens}
          loading={cenas.isPending}
          getRowId={(c) => c.id}
          emptyMessage={
            q || status || tag || arquivadas || ids.avatarId || ids.cenarioId || ids.produtoImagemId || produtoId
              ? 'Nenhuma cena com esses filtros. Use "Nova cena" para criar.'
              : `Nenhuma cena${vazioDoPerfil(perfilFiltro, perfis.data).trecho} ainda. Use "Nova cena" para criar a primeira${perfilBase ? ": ela já nasce com este perfil base" : ""}.`
          }
          toolbar={
            <FilterBar
              busca={{
                valor: q,
                onChange: (v) => set({ q: v || null }, { replace: true }),
                rotulo: "Buscar cenas",
                placeholder: "Nome, ação, fala ou produto",
              }}
              principais={
                <>
                  <PerfilBaseFiltro valor={perfilFiltro} onChange={onPerfilFiltro} />
                  <Field label="Status" className="w-full sm:w-40">
                    {({ id }) => (
                      <NativeSelect id={id} value={status} onChange={(e) => set({ status: e.target.value })}>
                        <option value="">Todos</option>
                        {(Object.keys(statusCenaLabel) as CenaStatus[]).map((st) => (
                          <option key={st} value={st}>
                            {statusCenaLabel[st]}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  {selectAsset("avatarId", "w-full sm:w-48")}
                  <label className="flex h-9 items-center gap-2 text-sm">
                    <Switch checked={arquivadas} onCheckedChange={(on) => set({ arquivadas: on ? "1" : null })} aria-label="Mostrar arquivadas" />
                    Arquivadas
                  </label>
                </>
              }
              mais={
                <>
                  {selectAsset("cenarioId")}
                  {selectAsset("produtoImagemId")}
                  <Field label="Produto do catálogo" hint={produtos.truncado ? TETO_TEXTO : undefined}>
                    {({ id, describedBy }) => (
                      <NativeSelect id={id} value={produtoId} aria-describedby={describedBy} onChange={(e) => set({ produtoId: e.target.value })}>
                        <option value="">Todos</option>
                        {produtoId && !produtosLista.some((p) => p.id === produtoId) && <option value={produtoId}>Produto escolhido</option>}
                        {produtosLista.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.nomeComercial ?? p.name} · {perfilNomeDe(p, perfis.data)}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <Field label="Tag">{({ id }) => <TagFiltro id={id} valor={tag} onChange={(v) => set({ tag: v || null })} />}</Field>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ perfil: null, q: null, status: null, tag: null, arquivadas: null, avatarId: null, cenarioId: null, produtoImagemId: null, produtoId: null })}
            />
          }
          pagination={{ hasMore: cenas.hasNextPage, onLoadMore: () => void cenas.fetchNextPage(), loadingMore: cenas.isFetchingNextPage }}
        />
      </HeaderCard>
      {perfil && <PropostasAbertas perfilId={perfil.id} />}
      {perfil && <PadroesCenas key={perfil.id} perfil={perfil} />}
    </>
  );
}

// "Padrões das cenas" (spec 010): estilo e negative do perfil; sem linha = padrão do código (version 0).
function PadroesCenas({ perfil }: { perfil: Perfil }) {
  const queryClient = useQueryClient();
  const padroes = useCenaPadroes(perfil.id);
  const [estilo, setEstilo] = useState("");
  const [negative, setNegative] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const p = padroes.data;
  useEffect(() => {
    if (!p) return;
    setEstilo(p.estilo);
    setNegative(p.negative);
  }, [p]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!p) return;
    setError(null);
    setBusy(true);
    try {
      await api.cenas.padroesPut(perfil.id, { version: p.version, estilo: estilo.trim(), negative: negative.trim() });
      toast.success("Padrões das cenas salvos. As cenas em rascunho já usam os novos.");
      await Promise.all([queryClient.invalidateQueries({ queryKey: cenaPadroesKey(perfil.id) }), queryClient.invalidateQueries({ queryKey: ["cena"] })]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Padrões das cenas de {perfil.name}</h2>
        </CardTitle>
        <CardDescription>Valem quando a cena deixa "Iluminação e estilo" ou "Negative prompt" vazio. Em inglês.</CardDescription>
      </CardHeader>
      <CardContent>
        {padroes.isError && <ApiErrorAlert error={padroes.error} />}
        {p && (
          <form onSubmit={salvar} className="space-y-4">
            <Field label="Iluminação e estilo padrão" hint={`Padrão do SociMan: ${p.padraoCodigo.estilo}`}>
              {({ id, describedBy }) => (
                <Textarea id={id} rows={2} maxLength={LIM.estilo} aria-describedby={describedBy} value={estilo} disabled={perfil.archived} onChange={(e) => setEstilo(e.target.value)} />
              )}
            </Field>
            <Field label="Negative prompt padrão" hint={`Padrão do SociMan: ${p.padraoCodigo.negative}`}>
              {({ id, describedBy }) => (
                <Textarea id={id} rows={2} maxLength={LIM.negative} aria-describedby={describedBy} value={negative} disabled={perfil.archived} onChange={(e) => setNegative(e.target.value)} />
              )}
            </Field>
            {error !== null && <ApiErrorAlert error={error} onReload={() => void queryClient.invalidateQueries({ queryKey: cenaPadroesKey(perfil.id) })} />}
            {!perfil.archived && (
              <Button type="submit" variant="outline" disabled={busy || !estilo.trim() || !negative.trim() || (estilo === p.estilo && negative === p.negative)} aria-busy={busy}>
                {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                Salvar padrões
              </Button>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  );
}

// Propostas de cena abertas dos agentes (spec 010, US5): "Aceitar" abre o formulário preenchido.
function PropostasAbertas({ perfilId }: { perfilId: string }) {
  const q = useAnotacoes({ perfilId, tipo: "proposta_cena", situacao: "aberta" });
  const itens = q.data?.pages.flatMap((p) => p.anotacoes) ?? [];
  if (itens.length === 0) return null;
  return (
    <Card className="shadow-card" aria-labelledby="propostas-cena">
      <CardHeader>
        <CardTitle>
          <h2 id="propostas-cena">Propostas de cena dos agentes ({itens.length})</h2>
        </CardTitle>
        <CardDescription>Nada vira cena sem você: "Aceitar" abre o formulário preenchido, e só o "Salvar" grava.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {itens.map((a) => (
            <li key={a.id}>
              <PropostaCard anotacao={a} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
