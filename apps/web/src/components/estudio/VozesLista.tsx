/*
 * Vozes da agência (spec 029, T017; antes a aba Vozes do perfil, 025 US2/T028): as vozes de
 * narração de todos os perfis e sem perfil, por gravação (com consentimento) ou sintéticas
 * (descrição em inglês), com o perfil base, o estado, a sincronização com o shop-tts e o uso pelos
 * avatares. Filtros na URL (`perfil`, `q`, `status`, `arquivadas=1`). "Nova voz" cria em rascunho,
 * com o perfil do filtro, e abre o detalhe. O nome é único na agência inteira (Clarification 1).
 */
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Mic, Plus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { EmptyState, HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { perfilDoFiltro, perfilNomeDe, usePerfisTodos, vazioDoPerfil, type PerfilFiltro } from "@/lib/estudio";
import { useFiltroUrl } from "@/lib/filtros";
import { formatDateTime } from "@/lib/tz";
import {
  LIM_VOZ,
  origemVozLabel,
  sincronizacaoLabel,
  STATUS_VOZ,
  statusVozLabel,
  statusVozTone,
  useVozesAgencia,
  type VozOrigem,
  type VozResumo,
  type VozStatus,
} from "@/lib/vozes";
import { PerfilBaseField } from "./PerfilBaseField";
import { PerfilBaseFiltro, usePerfilBaseAtivo } from "./PerfilBaseFiltro";

function colunas(nomePerfil: (v: VozResumo) => string) {
  const col = dataTableColumns<VozResumo>();
  return col.columns([
    col.accessor("name", {
      header: "Voz",
      cell: (c) => {
        const v = c.row.original;
        return (
          <div className="min-w-0">
            <Link to={`/app/vozes/${v.id}`} className="font-medium break-words underline-offset-2 hover:underline">
              {v.name}
            </Link>
            <p className="text-xs text-muted-foreground">{v.tom}</p>
          </div>
        );
      },
    }),
    col.accessor((v) => nomePerfil(v), {
      id: "perfilBase",
      header: "Perfil base",
      meta: { className: "hidden sm:table-cell" },
      cell: (c) => <span className="whitespace-nowrap">{c.getValue()}</span>,
    }),
    col.accessor((v) => origemVozLabel[v.origem], { id: "origem", header: "Origem", meta: { className: "hidden sm:table-cell" } }),
    col.accessor((v) => statusVozLabel[v.status], {
      id: "status",
      header: "Estado",
      cell: (c) => {
        const v = c.row.original;
        return (
          <span className="flex flex-wrap gap-1">
            <Badge className={statusVozTone[v.status]}>{c.getValue()}</Badge>
            {v.revogada && <Badge className="bg-dark text-dark-foreground">Revogada</Badge>}
            {v.archived && !v.revogada && <Badge className="bg-dark text-dark-foreground">Arquivada</Badge>}
          </span>
        );
      },
    }),
    col.accessor((v) => sincronizacaoLabel[v.sincronizacao], { id: "sincronizacao", header: "Serviço de voz", meta: { className: "hidden md:table-cell" } }),
    col.accessor("nUsadaPor", {
      header: "Avatares",
      enableGlobalFilter: false,
      meta: { className: "hidden md:table-cell" },
      cell: (c) => <span className="tabular-nums">{c.getValue()}</span>,
    }),
    col.accessor("updatedAt", {
      header: "Alterada",
      enableGlobalFilter: false,
      meta: { className: "hidden lg:table-cell" },
      cell: (c) => (
        <time dateTime={c.getValue()} className="whitespace-nowrap">
          {formatDateTime(c.getValue())}
        </time>
      ),
    }),
  ]);
}

export function VozesLista({ perfilFiltro, onPerfilFiltro }: { perfilFiltro: PerfilFiltro; onPerfilFiltro: (v: PerfilFiltro) => void }) {
  const perfis = usePerfisTodos();
  const [params, set] = useFiltroUrl();
  const q = params.get("q") ?? "";
  const status = (params.get("status") ?? "") as VozStatus | "";
  const arquivadas = params.get("arquivadas") === "1";
  const [nova, setNova] = useState(false);
  const vozes = useVozesAgencia(perfilFiltro, { q: q || undefined, status: status || undefined, arquivadas });
  const itens = useMemo(() => vozes.data?.pages.flatMap((p) => p.itens), [vozes.data]);
  const columns = useMemo(() => colunas((v) => perfilNomeDe(v, perfis.data)), [perfis.data]);
  const vazio = vazioDoPerfil(perfilFiltro, perfis.data);
  const ativosPerfil = usePerfilBaseAtivo(perfilFiltro, () => onPerfilFiltro("todos"));
  const ativos: FiltroAtivo[] = [
    ...ativosPerfil,
    ...(status ? [{ chave: "status", rotulo: "Estado", valor: statusVozLabel[status] ?? status, limpar: () => set({ status: null }) }] : []),
    ...(arquivadas ? [{ chave: "arquivadas", rotulo: "Arquivadas", valor: "mostrando", limpar: () => set({ arquivadas: null }) }] : []),
  ];

  return (
    <>
      <HeaderCard
        title="Biblioteca da agência"
        description="As vozes que narram os vídeos: de uma gravação (com consentimento) ou sintéticas. A escolhida vira a referência do serviço de voz."
        actions={
          <Button variant="secondary" size="sm" onClick={() => setNova(true)}>
            <Plus aria-hidden="true" />
            Nova voz
          </Button>
        }
      >
        {vozes.isError && <ApiErrorAlert error={vozes.error} />}
        <DataTable
          label="Vozes"
          columns={columns}
          data={itens}
          loading={vozes.isPending}
          getRowId={(v) => v.id}
          empty={
            q || status ? (
              <EmptyState titulo="Nenhuma voz com esses filtros." icone={Mic} />
            ) : (
              <EmptyState
                titulo={`Nenhuma voz${vazio.trecho} ainda.`}
                descricao={`Use "Nova voz" para cadastrar por gravação (15 a 30 s no tom de venda) ou descrever uma voz sintética.${vazio.criarComPerfil ? " A nova voz já nasce com este perfil base." : ""}`}
                icone={Mic}
              />
            )
          }
          toolbar={
            <FilterBar
              busca={{ valor: q, onChange: (v) => set({ q: v || null }, { replace: true }), rotulo: "Buscar vozes", placeholder: "Nome" }}
              principais={
                <>
                  <PerfilBaseFiltro valor={perfilFiltro} onChange={onPerfilFiltro} />
                  <Field label="Estado" className="w-full sm:w-40">
                    {({ id }) => (
                      <NativeSelect id={id} value={status} onChange={(e) => set({ status: e.target.value })}>
                        <option value="">Todos</option>
                        {STATUS_VOZ.map((st) => (
                          <option key={st} value={st}>
                            {statusVozLabel[st]}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <label className="flex h-9 items-center gap-2 text-sm">
                    <Switch checked={arquivadas} onCheckedChange={(on) => set({ arquivadas: on ? "1" : null })} aria-label="Ver arquivadas" />
                    Ver arquivadas
                  </label>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ perfil: null, q: null, status: null, arquivadas: null })}
            />
          }
          pagination={{ hasMore: vozes.hasNextPage, onLoadMore: () => void vozes.fetchNextPage(), loadingMore: vozes.isFetchingNextPage }}
        />
      </HeaderCard>
      <NovaVozDialog perfilId={perfilDoFiltro(perfilFiltro)} open={nova} onOpenChange={setNova} />
    </>
  );
}

function NovaVozDialog({ perfilId, open, onOpenChange }: { perfilId: string | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [origem, setOrigem] = useState<VozOrigem>("gravacao");
  const [tom, setTom] = useState("");
  const [descricao, setDescricao] = useState("");
  const [perfilBase, setPerfilBase] = useState<string | null>(perfilId);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function abrir(o: boolean) {
    if (o) {
      setName("");
      setOrigem("gravacao");
      setTom("");
      setDescricao("");
      setPerfilBase(perfilId);
      setErros({});
      setError(null);
    }
    onOpenChange(o);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = "Dê um nome à voz";
    if (!tom.trim()) errs.tom = 'Descreva o tom (ex.: "vendas animada")';
    if (origem === "sintetica" && !descricao.trim()) errs.descricao = "Descreva a voz em inglês";
    setErros(errs);
    if (Object.keys(errs).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const voz = await api.vozes.criarAgencia({
        name: name.trim(),
        origem,
        tom: tom.trim(),
        descricao: origem === "sintetica" ? descricao.trim() : null,
        perfilId: perfilBase,
      });
      await queryClient.invalidateQueries({ queryKey: ["vozes"] });
      onOpenChange(false);
      void navigate(`/app/vozes/${voz.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && abrir(o)}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>Nova voz</DialogTitle>
            <DialogDescription>Por gravação de uma pessoa real (com consentimento) ou sintética, descrita em inglês.</DialogDescription>
          </DialogHeader>
          <Field label="Nome da voz" error={erros.name}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} value={name} maxLength={LIM_VOZ.nome} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setName(e.target.value)} />
            )}
          </Field>
          <PerfilBaseField value={perfilBase} onChange={setPerfilBase} disabled={busy} hint="O guia deste perfil entra nas gerações da voz." />
          <Field label="Origem">
            {({ id }) => (
              <NativeSelect id={id} value={origem} onChange={(e) => setOrigem(e.target.value as VozOrigem)}>
                <option value="gravacao">Gravação (pessoa real)</option>
                <option value="sintetica">Sintética (descrição)</option>
              </NativeSelect>
            )}
          </Field>
          <Field label="Tom" error={erros.tom} hint='Ex.: "vendas animada", "explicativa calma".'>
            {({ id, describedBy, invalid }) => (
              <Input id={id} value={tom} maxLength={LIM_VOZ.tom} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setTom(e.target.value)} />
            )}
          </Field>
          {origem === "sintetica" && (
            <Field
              label="Descrição da voz (inglês)"
              error={erros.descricao}
              hint="Idade adulta, energia, ritmo e papel. Ex.: warm brazilian woman in her 30s, upbeat, friendly sales tone, medium pace."
            >
              {({ id, describedBy, invalid }) => (
                <Textarea
                  id={id}
                  rows={3}
                  lang="en"
                  value={descricao}
                  maxLength={LIM_VOZ.descricao}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  onChange={(e) => setDescricao(e.target.value)}
                />
              )}
            </Field>
          )}
          {error !== null && <ApiErrorAlert error={error} />}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={busy} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
              Criar voz
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
