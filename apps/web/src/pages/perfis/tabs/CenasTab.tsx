/*
 * Aba Cenas do perfil (spec 010, US2; FR-007): a biblioteca de cenas (tomadas para o Flow/Veo) com
 * filtros por status, avatar, cenário, produto e tag, busca por nome, ação, fala e produto, "Nova
 * cena", "Duplicar" e "Arquivadas". Também os "Padrões das cenas" (iluminação e estilo e negative que
 * valem quando a cena deixa o campo vazio). A URL aceita `avatarId`, `cenarioId` e
 * `produtoImagemId` (o "onde é usado" dos assets abre a aba já filtrada).
 */
import type { Perfil } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Film, Filter, Loader2, Plus, Save } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PropostaCard } from "@/components/anotacoes/PropostaCard";
import { DataTable, dataTableColumns } from "@/components/data-table";
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
  useCenas,
  type CenaFiltros,
  type CenaResumo,
  type CenaStatus,
} from "@/lib/cenas";
import { formatDateTime } from "@/lib/tz";

type Draft = { q: string; status: string; avatarId: string; cenarioId: string; produtoImagemId: string; tag: string; arquivadas: boolean };

const paraFiltros = (d: Draft): CenaFiltros => ({
  q: d.q.trim() || undefined,
  status: (d.status || undefined) as CenaStatus | undefined,
  avatarId: d.avatarId || undefined,
  cenarioId: d.cenarioId || undefined,
  produtoImagemId: d.produtoImagemId || undefined,
  tag: d.tag.trim().toLowerCase() || undefined,
  arquivadas: d.arquivadas || undefined,
});

function DuplicarBotao({ cena, perfilId }: { cena: CenaResumo; perfilId: string }) {
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
          await invalidarCena(queryClient, null, perfilId);
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

function colunas(perfilId: string) {
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
    col.accessor((c) => c.produtoNome ?? "", { id: "produto", header: "Produto", meta: { className: "hidden md:table-cell" }, cell: (c) => c.getValue() || "—" }),
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
    col.display({ id: "acoes", header: "", cell: (c) => <DuplicarBotao cena={c.row.original} perfilId={perfilId} /> }),
  ]);
}

export function CenasTab({ perfil }: { perfil: Perfil }) {
  const [params] = useSearchParams();
  const inicial: Draft = {
    q: "",
    status: "",
    avatarId: params.get("avatarId") ?? "",
    cenarioId: params.get("cenarioId") ?? "",
    produtoImagemId: params.get("produtoImagemId") ?? "",
    tag: "",
    arquivadas: false,
  };
  const [draft, setDraft] = useState<Draft>(inicial);
  const [filtros, setFiltros] = useState<CenaFiltros>(() => paraFiltros(inicial));
  const cenas = useCenas(perfil.id, filtros);
  const itens = useMemo(() => cenas.data?.pages.flatMap((p) => p.items), [cenas.data]);
  const columns = useMemo(() => colunas(perfil.id), [perfil.id]);

  const opcoes = (tipo: "avatar" | "cenario" | "imagem") => ({
    queryKey: ["assets", perfil.id, "cena-opcoes", tipo],
    queryFn: () => api.assets.list(perfil.id, { tipo: [tipo], archived: "false" as const, limit: 100 }),
  });
  const avatares = useQuery(opcoes("avatar"));
  const cenarios = useQuery(opcoes("cenario"));
  const imagens = useQuery(opcoes("imagem"));

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFiltros(paraFiltros(draft));
  }

  const selectAsset = (label: string, key: "avatarId" | "cenarioId" | "produtoImagemId", lista: { id: string; name: string }[] | undefined) => (
    <Field label={label}>
      {({ id }) => (
        <NativeSelect id={id} value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}>
          <option value="">Todos</option>
          {/* o filtro vindo da URL pode ser de um asset arquivado */}
          {draft[key] && !lista?.some((a) => a.id === draft[key]) && <option value={draft[key]}>Asset escolhido</option>}
          {lista?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );

  return (
    <div className="flex flex-col gap-6">
      <HeaderCard
        title="Cenas"
        description="Tomadas de até 8 s para gerar no Google Flow: avatar, cenário, ação, fala e o prompt pronto para copiar."
        actions={
          !perfil.archived && (
            <Button variant="secondary" size="sm" asChild>
              <Link to={`/app/perfis/${perfil.id}/cenas/nova`}>
                <Plus aria-hidden="true" />
                Nova cena
              </Link>
            </Button>
          )
        }
      >
        <form onSubmit={onSubmit} className="mb-4 grid gap-4 border-b pb-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Filtros das cenas">
          <Field label="Buscar cenas" className="sm:col-span-2">
            {({ id }) => (
              <Input id={id} type="search" placeholder="Nome, ação, fala ou produto" value={draft.q} maxLength={100} onChange={(e) => setDraft({ ...draft, q: e.target.value })} />
            )}
          </Field>
          <Field label="Status">
            {({ id }) => (
              <NativeSelect id={id} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                <option value="">Todos</option>
                {(Object.keys(statusCenaLabel) as CenaStatus[]).map((s) => (
                  <option key={s} value={s}>
                    {statusCenaLabel[s]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Tag">
            {({ id }) => <Input id={id} value={draft.tag} onChange={(e) => setDraft({ ...draft, tag: e.target.value })} />}
          </Field>
          {selectAsset("Avatar", "avatarId", avatares.data?.items)}
          {selectAsset("Cenário", "cenarioId", cenarios.data?.items)}
          {selectAsset("Foto do produto", "produtoImagemId", imagens.data?.items)}
          <div className="flex flex-wrap items-end justify-between gap-3">
            <label className="flex h-9 items-center gap-2 text-sm">
              <Switch checked={draft.arquivadas} onCheckedChange={(arquivadas) => setDraft({ ...draft, arquivadas })} aria-label="Mostrar arquivadas" />
              Arquivadas
            </label>
            <Button type="submit">
              <Filter aria-hidden="true" />
              Filtrar
            </Button>
          </div>
        </form>
        {cenas.isError && <ApiErrorAlert error={cenas.error} />}
        <DataTable
          label="Cenas do perfil"
          columns={columns}
          data={itens}
          loading={cenas.isPending}
          getRowId={(c) => c.id}
          emptyMessage={'Nenhuma cena com esses filtros. Use "Nova cena" para criar.'}
          pagination={{ hasMore: cenas.hasNextPage, onLoadMore: () => void cenas.fetchNextPage(), loadingMore: cenas.isFetchingNextPage }}
        />
      </HeaderCard>
      <PropostasAbertas perfilId={perfil.id} />
      <PadroesCenas perfil={perfil} />
    </div>
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
          <h2>Padrões das cenas</h2>
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
