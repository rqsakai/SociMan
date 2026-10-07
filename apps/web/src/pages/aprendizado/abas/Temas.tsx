/*
 * Aba "Temas" do aprendizado (spec 023, US1; FR-001 a FR-007).
 *
 * - Taxonomia do perfil: criar, editar, juntar (A → B), arquivar e restaurar, cada tema com o
 *   histórico e a reversão do dono. "Propor com IA" devolve de 3 a 15 temas que só valem ao salvar
 *   (como o "montar guia" da 017); o custo da proposta só aparece para o dono.
 * - Classificação dos posts: o tema, os secundários, o estilo do gancho, a justificativa e a origem
 *   (IA ou dono). O dono corrige (a IA nunca sobrescreve) e pede "Classificar pendentes", que a
 *   trilha do agendador atende na próxima volta, respeitando o limite diário.
 * O membro vê tudo, sem botões.
 */
import { ApiError } from "@sociman/contract";
import { Archive, ArchiveRestore, Combine, History, Loader2, Pencil, Plus, Save, Sparkles, Tags, Trash2, Wand2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ClassificacaoEditor } from "@/components/aprendizado/ClassificacaoEditor";
import { formatarValor, HistoricoDialog } from "@/components/aprendizado/HistoricoDialog";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { HeaderCard } from "@/components/shell";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import {
  estiloGanchoLabel,
  formatUsd,
  useClassificacaoVersions,
  useClassificacoes,
  useInvalidarAprendizado,
  useTemas,
  useTemaVersions,
  type AprendizadoClassificacao,
  type AprendizadoTema,
  type AprendizadoTemaIn,
  type EstiloGancho,
} from "@/lib/aprendizado";
import { useEhDono } from "@/lib/conteudos";
import { formatNumero } from "@/lib/metricas";
import type { AbaProps } from "../Aprendizado";

const linkVideo = (id: string) => `/app/metricas/videos/${id}`;

// "marvel, mcu , vingadores" → ["marvel", "mcu", "vingadores"] (o servidor normaliza e valida)
const palavras = (s: string) =>
  s
    .split(/[,\n]/)
    .map((p) => p.trim())
    .filter(Boolean);

const temaLabels: Record<string, string> = {
  nome: "Nome",
  descricao: "Descrição",
  palavras_chave: "Palavras-chave",
  archived: "Arquivado",
  juntado_em_id: "Juntado em",
};

export function Temas({ perfil, contas, estado }: AbaProps) {
  const dono = useEhDono();
  const [arquivados, setArquivados] = useState(false);
  const temas = useTemas(perfil.id, arquivados);
  const invalidar = useInvalidarAprendizado();
  const atualizar = () => invalidar(perfil.id);

  const ativos = temas.data?.items.filter((t) => !t.archived) ?? [];

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <HeaderCard
        title="Temas do perfil"
        description={
          temas.data
            ? `${formatNumero(ativos.length)} ${ativos.length === 1 ? "tema ativo" : "temas ativos"} (até 30) · taxonomia v${temas.data.taxonomiaVersao}`
            : "Carregando…"
        }
        actions={
          <label className="flex items-center gap-2 text-sm text-white">
            <input type="checkbox" className="size-4 accent-primary" checked={arquivados} onChange={(e) => setArquivados(e.target.checked)} />
            Mostrar arquivados
          </label>
        }
      >
        <div className="flex flex-col gap-4 pb-2">
          {dono && <PropostaIa perfilId={perfil.id} temNada={ativos.length === 0} onSalvo={atualizar} />}
          {temas.isError ? (
            <ApiErrorAlert error={temas.error} />
          ) : temas.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : temas.data.items.length === 0 ? (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
              Nenhum tema ainda. {dono ? "Crie os temas à mão ou peça uma proposta à IA a partir dos posts publicados." : "O dono define os temas do perfil."}
            </p>
          ) : (
            <ul className="divide-y" aria-label="Temas">
              {temas.data.items.map((t) => (
                <TemaItem key={t.id} tema={t} todos={temas.data.items} dono={dono} onMudou={atualizar} />
              ))}
            </ul>
          )}
          {dono && <NovoTema perfilId={perfil.id} onCriado={atualizar} />}
        </div>
      </HeaderCard>

      <Classificacoes perfilId={perfil.id} contaId={estado.filtro.contaId} contasCount={contas.length} temas={ativos} dono={dono} onMudou={atualizar} />
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Um tema da lista: nome, descrição, palavras-chave, n de posts e as ações do dono.

function TemaItem({ tema, todos, dono, onMudou }: { tema: AprendizadoTema; todos: AprendizadoTema[]; dono: boolean; onMudou: () => Promise<unknown> }) {
  const [editando, setEditando] = useState(false);
  const [juntar, setJuntar] = useState(false);
  const [historico, setHistorico] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const destino = tema.juntadoEmId ? todos.find((t) => t.id === tema.juntadoEmId) : null;

  async function arquivar() {
    setBusy(true);
    setErro(null);
    try {
      if (tema.archived) await api.aprendizado.temas.restore(tema.id, tema.version);
      else await api.aprendizado.temas.archive(tema.id, tema.version);
      toast.success(tema.archived ? `Tema "${tema.nome}" restaurado.` : `Tema "${tema.nome}" arquivado. Os posts dele foram para "Sem tema".`);
      await onMudou();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-col gap-2 py-3" aria-label={`Tema ${tema.nome}`}>
      {editando ? (
        <TemaForm
          inicial={tema}
          rotulo="Salvar tema"
          onCancelar={() => setEditando(false)}
          onEnviar={async (body) => {
            await api.aprendizado.temas.update(tema.id, { version: tema.version, ...body });
            toast.success("Tema salvo.");
            setEditando(false);
            await onMudou();
          }}
        />
      ) : (
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-1">
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{tema.nome}</span>
              <Badge variant="secondary">
                {formatNumero(tema.nPosts)} {tema.nPosts === 1 ? "post" : "posts"}
              </Badge>
              {tema.archived && <Badge variant="outline">{destino ? `juntado em ${destino.nome}` : "arquivado"}</Badge>}
            </p>
            {tema.descricao && <p className="text-sm text-muted-foreground">{tema.descricao}</p>}
            {tema.palavrasChave.length > 0 && (
              <p className="flex flex-wrap gap-1" aria-label="Palavras-chave">
                {tema.palavrasChave.map((p) => (
                  <span key={p} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {p}
                  </span>
                ))}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Button type="button" size="sm" variant="ghost" onClick={() => setHistorico(true)} aria-label={`Histórico do tema ${tema.nome}`}>
              <History aria-hidden="true" />
              Histórico
            </Button>
            {dono && !tema.archived && (
              <>
                <Button type="button" size="sm" variant="outline" onClick={() => setEditando(true)} aria-label={`Editar o tema ${tema.nome}`}>
                  <Pencil aria-hidden="true" />
                  Editar
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => setJuntar(true)} aria-label={`Juntar o tema ${tema.nome} a outro`}>
                  <Combine aria-hidden="true" />
                  Juntar
                </Button>
              </>
            )}
            {dono && !tema.juntadoEmId && (
              <ConfirmButton
                size="sm"
                label={tema.archived ? "Restaurar" : "Arquivar"}
                icon={tema.archived ? ArchiveRestore : Archive}
                busy={busy}
                title={tema.archived ? `Restaurar o tema "${tema.nome}"?` : `Arquivar o tema "${tema.nome}"?`}
                description={
                  tema.archived
                    ? "O tema volta para a taxonomia. Os posts que foram para \"Sem tema\" continuam lá até serem classificados de novo."
                    : `Os ${formatNumero(tema.nPosts)} posts deste tema vão para "Sem tema" e a IA os classifica de novo (as correções do dono ficam para você revisar). Dá para restaurar depois.`
                }
                onConfirm={arquivar}
              />
            )}
          </div>
        </div>
      )}
      {erro !== null && <ApiErrorAlert error={erro} onReload={() => void onMudou()} />}
      {juntar && <JuntarDialog tema={tema} destinos={todos.filter((t) => !t.archived && t.id !== tema.id)} onFechar={() => setJuntar(false)} onJuntado={onMudou} />}
      {historico && <HistoricoTema tema={tema} onFechar={() => setHistorico(false)} onMudou={onMudou} />}
    </li>
  );
}

function HistoricoTema({ tema, onFechar, onMudou }: { tema: AprendizadoTema; onFechar: () => void; onMudou: () => Promise<unknown> }) {
  const versions = useTemaVersions(tema.id);
  return (
    <HistoricoDialog
      aberto
      onFechar={onFechar}
      titulo={`Histórico do tema "${tema.nome}"`}
      descricao="Reverter uma junção devolve os posts movidos ao tema de origem."
      versions={versions.data?.items}
      carregando={versions.isPending}
      erro={versions.error}
      labels={temaLabels}
      formatValue={(_, v) => formatarValor(v)}
      onRevert={async (toVersion) => {
        await api.aprendizado.temas.revert(tema.id, tema.version, toVersion);
        await Promise.all([onMudou(), versions.refetch()]);
      }}
      onReload={async () => {
        await Promise.all([onMudou(), versions.refetch()]);
      }}
    />
  );
}

function JuntarDialog({ tema, destinos, onFechar, onJuntado }: { tema: AprendizadoTema; destinos: AprendizadoTema[]; onFechar: () => void; onJuntado: () => Promise<unknown> }) {
  const [destinoId, setDestinoId] = useState(destinos[0]?.id ?? "");
  const [erro, setErro] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const destino = destinos.find((d) => d.id === destinoId);

  async function confirmar() {
    if (!destinoId) return;
    setBusy(true);
    setErro(null);
    try {
      const out = await api.aprendizado.temas.juntar(tema.id, { version: tema.version, destinoId });
      toast.success(`"${tema.nome}" juntado em "${out.destino.nome}": ${formatNumero(out.movidas)} ${out.movidas === 1 ? "post movido" : "posts movidos"}.`);
      onFechar();
      await onJuntado();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AlertDialog open onOpenChange={(o) => !o && onFechar()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Juntar &quot;{tema.nome}&quot; a outro tema?</AlertDialogTitle>
          <AlertDialogDescription>
            Os posts de &quot;{tema.nome}&quot; passam para o tema escolhido, e &quot;{tema.nome}&quot; é arquivado. A junção fica no histórico e pode ser revertida.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {destinos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Não há outro tema ativo para receber os posts.</p>
        ) : (
          <Field label="Juntar em">
            {({ id }) => (
              <NativeSelect id={id} value={destinoId} onChange={(e) => setDestinoId(e.target.value)}>
                {destinos.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nome}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        )}
        {erro !== null && <ApiErrorAlert error={erro} />}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            disabled={!destino || busy}
            onClick={(e) => {
              e.preventDefault();
              void confirmar();
            }}
          >
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            Juntar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------------------------
// Formulário de tema (criar e editar)

function TemaForm({
  inicial,
  rotulo,
  onEnviar,
  onCancelar,
}: {
  inicial?: Partial<AprendizadoTemaIn>;
  rotulo: string;
  onEnviar: (body: AprendizadoTemaIn) => Promise<void>;
  onCancelar?: () => void;
}) {
  const [nome, setNome] = useState(inicial?.nome ?? "");
  const [descricao, setDescricao] = useState(inicial?.descricao ?? "");
  const [chaves, setChaves] = useState((inicial?.palavrasChave ?? []).join(", "));
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErro(null);
    try {
      await onEnviar({ nome: nome.trim(), descricao: descricao.trim(), palavrasChave: palavras(chaves) });
      if (!inicial) {
        setNome("");
        setDescricao("");
        setChaves("");
      }
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void enviar(e)} className="flex flex-col gap-3" aria-label={rotulo}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Nome do tema" hint="Até 40 caracteres; único no perfil.">
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={nome} maxLength={40} required onChange={(e) => setNome(e.target.value)} />}
        </Field>
        <Field label="Palavras-chave" hint="Separadas por vírgula. Casam os vídeos-fonte no Descobrir (sem acento e sem caixa).">
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={chaves} onChange={(e) => setChaves(e.target.value)} />}
        </Field>
      </div>
      <Field label="Descrição" hint="Uma frase curta (até 200 caracteres), que a IA lê ao classificar.">
        {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} rows={2} maxLength={200} value={descricao} onChange={(e) => setDescricao(e.target.value)} />}
      </Field>
      {erro !== null && <ApiErrorAlert error={erro} />}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" disabled={busy || !nome.trim()} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : inicial ? <Save aria-hidden="true" /> : <Plus aria-hidden="true" />}
          {rotulo}
        </Button>
        {onCancelar && (
          <Button type="button" size="sm" variant="ghost" onClick={onCancelar}>
            Cancelar
          </Button>
        )}
      </div>
    </form>
  );
}

function NovoTema({ perfilId, onCriado }: { perfilId: string; onCriado: () => Promise<unknown> }) {
  const [aberto, setAberto] = useState(false);
  if (!aberto) {
    return (
      <div>
        <Button type="button" variant="outline" size="sm" onClick={() => setAberto(true)}>
          <Plus aria-hidden="true" />
          Novo tema
        </Button>
      </div>
    );
  }
  return (
    <div className="rounded-lg border p-3">
      <TemaForm
        rotulo="Criar tema"
        onCancelar={() => setAberto(false)}
        onEnviar={async (body) => {
          await api.aprendizado.temas.create(perfilId, body);
          toast.success(`Tema "${body.nome}" criado.`);
          await onCriado();
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Proposta da IA: nada salvo até "Salvar temas" (tudo ou nada, com o selo da IA no histórico).

function PropostaIa({ perfilId, temNada, onSalvo }: { perfilId: string; temNada: boolean; onSalvo: () => Promise<unknown> }) {
  const [instrucao, setInstrucao] = useState("");
  const [busy, setBusy] = useState<"propor" | "salvar" | null>(null);
  const [erro, setErro] = useState<unknown>(null);
  const [proposta, setProposta] = useState<{ chamadaId: string; custoUsd: number | null; temas: AprendizadoTemaIn[] } | null>(null);

  async function propor() {
    setBusy("propor");
    setErro(null);
    try {
      const out = await api.aprendizado.taxonomiaPropor(perfilId, { instrucao: instrucao.trim() });
      setProposta({ chamadaId: out.chamadaId, custoUsd: out.custoUsd ?? null, temas: out.temas });
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(null);
    }
  }

  async function salvar() {
    if (!proposta) return;
    setBusy("salvar");
    setErro(null);
    try {
      const out = await api.aprendizado.temas.lote(perfilId, { temas: proposta.temas, chamadaId: proposta.chamadaId });
      toast.success(`${formatNumero(out.items.length)} temas salvos.`);
      setProposta(null);
      await onSalvo();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(null);
    }
  }

  const editar = (i: number, patch: Partial<AprendizadoTemaIn>) =>
    setProposta((p) => (p ? { ...p, temas: p.temas.map((t, j) => (j === i ? { ...t, ...patch } : t)) } : p));

  return (
    <section aria-label="Proposta de temas da IA" className="flex flex-col gap-3 rounded-lg border border-dashed p-3">
      {!proposta ? (
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Instrução para a IA (opcional)" className="min-w-0 flex-1 basis-64">
            {({ id }) => <Input id={id} value={instrucao} placeholder="ex.: separe Marvel de DC" onChange={(e) => setInstrucao(e.target.value)} />}
          </Field>
          <Button type="button" variant={temNada ? "default" : "outline"} disabled={busy !== null} aria-busy={busy === "propor"} onClick={() => void propor()}>
            {busy === "propor" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Wand2 aria-hidden="true" />}
            Propor com IA
          </Button>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="flex items-center gap-2 text-sm font-medium">
              <Sparkles className="size-4 text-primary" aria-hidden="true" />
              Proposta da IA: {formatNumero(proposta.temas.length)} temas (nada salvo ainda)
            </p>
            {proposta.custoUsd !== null && <span className="text-xs text-muted-foreground">custo aproximado {formatUsd(proposta.custoUsd)}</span>}
          </div>
          <ol className="flex flex-col gap-2" aria-label="Temas propostos">
            {proposta.temas.map((t, i) => (
              <li key={i} className="grid gap-2 rounded-md bg-muted/40 p-2 sm:grid-cols-[1fr_2fr_auto] sm:items-start">
                <Input aria-label={`Nome do tema proposto ${i + 1}`} value={t.nome} maxLength={40} onChange={(e) => editar(i, { nome: e.target.value })} />
                <div className="min-w-0 space-y-1">
                  <Input aria-label={`Descrição do tema proposto ${i + 1}`} value={t.descricao ?? ""} maxLength={200} onChange={(e) => editar(i, { descricao: e.target.value })} />
                  <Input
                    aria-label={`Palavras-chave do tema proposto ${i + 1}`}
                    value={(t.palavrasChave ?? []).join(", ")}
                    onChange={(e) => editar(i, { palavrasChave: palavras(e.target.value) })}
                  />
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label={`Tirar ${t.nome || `o tema ${i + 1}`} da proposta`}
                  onClick={() => setProposta((p) => (p ? { ...p, temas: p.temas.filter((_, j) => j !== i) } : p))}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={busy !== null || proposta.temas.length === 0} aria-busy={busy === "salvar"} onClick={() => void salvar()}>
              {busy === "salvar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar temas
            </Button>
            <Button type="button" variant="ghost" disabled={busy !== null} onClick={() => setProposta(null)}>
              Descartar proposta
            </Button>
          </div>
        </>
      )}
      {erro !== null && <ApiErrorAlert error={erro} />}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
// Classificação dos posts

const classLabels: Record<string, string> = {
  tema_id: "Tema",
  secundarios: "Secundários",
  estilo_gancho: "Estilo do gancho",
  origem: "Origem",
  reclassificar: "Reclassificar",
};

function Classificacoes({
  perfilId,
  contaId,
  contasCount,
  temas,
  dono,
  onMudou,
}: {
  perfilId: string;
  contaId?: string;
  contasCount: number;
  temas: AprendizadoTema[];
  dono: boolean;
  onMudou: () => Promise<unknown>;
}) {
  const [temaId, setTemaId] = useState("");
  const [pendentes, setPendentes] = useState(false);
  const [limit, setLimit] = useState(50);
  const [editando, setEditando] = useState<string | null>(null);
  const [historico, setHistorico] = useState<AprendizadoClassificacao | null>(null);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const filtros = {
    ...(contaId ? { contaId } : {}),
    ...(temaId ? { temaId } : {}),
    ...(pendentes ? { pendentes: true } : {}),
    limit,
  };
  const lista = useClassificacoes(perfilId, filtros);
  const d = lista.data;
  const nomeTema = (id: string | null | undefined) => (id ? (temas.find((t) => t.id === id)?.nome ?? "tema arquivado") : "Sem tema");

  async function classificarPendentes() {
    setBusy(true);
    setErro(null);
    try {
      const out = await api.aprendizado.classificarPendentes(perfilId);
      toast.success(
        `${formatNumero(out.pendentes)} ${out.pendentes === 1 ? "post pendente" : "posts pendentes"}: o agendador classifica na próxima volta (restam ${formatNumero(out.restantesHoje)} hoje).`,
      );
      await onMudou();
    } catch (err) {
      if (err instanceof ApiError && err.code === "sem_taxonomia") toast.info("Salve os temas do perfil antes de classificar.");
      else setErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <HeaderCard
      title="Classificação dos posts"
      tone="dark"
      description={
        d
          ? `${formatNumero(d.pendentes)} aguardando classificação · usadas hoje ${formatNumero(d.limiteHoje.usadas)} / ${formatNumero(d.limiteHoje.limite)}`
          : "Carregando…"
      }
      actions={
        dono && (
          <Button type="button" size="sm" variant="secondary" disabled={busy || temas.length === 0} aria-busy={busy} onClick={() => void classificarPendentes()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Tags aria-hidden="true" />}
            Classificar pendentes
          </Button>
        )
      }
    >
      <div className="flex flex-col gap-4 pb-2">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Tema" className="w-full sm:w-56">
            {({ id }) => (
              <NativeSelect id={id} value={temaId} onChange={(e) => setTemaId(e.target.value)}>
                <option value="">Todos os temas</option>
                {temas.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.nome}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={pendentes} onChange={(e) => setPendentes(e.target.checked)} />
            Só pendentes
          </label>
        </div>
        <p className="text-xs text-muted-foreground">
          A IA classifica os posts com 24 h ou mais, até {d ? formatNumero(d.limiteHoje.limite) : "50"} por dia neste perfil; o resto fica para o dia seguinte. Correção do dono nunca é
          sobrescrita.{contasCount > 1 && !contaId ? " Mostrando todas as contas do perfil." : ""}
        </p>
        {erro !== null && <ApiErrorAlert error={erro} />}
        {lista.isError ? (
          <ApiErrorAlert error={lista.error} />
        ) : lista.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : d!.items.length === 0 ? (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
            {pendentes ? "Nenhum post aguardando classificação." : "Nenhum post classificado com estes filtros."}
          </p>
        ) : (
          <ul className="divide-y" aria-label="Classificações">
            {d!.items.map((c) => (
              <li key={c.videoId} className="flex flex-col gap-2 py-3" aria-label={`Post ${c.post?.tituloCurto || "sem legenda"}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm">
                      <Link to={linkVideo(c.videoId)} className="font-medium break-words underline-offset-2 hover:underline">
                        {c.post?.tituloCurto || "(sem legenda)"}
                      </Link>
                      <span className="text-xs text-muted-foreground">{c.post?.rotuloConta}</span>
                    </p>
                    <p className="flex flex-wrap items-center gap-1.5 text-sm" data-tema={c.temaNome ?? "Sem tema"}>
                      <Badge>{c.temaNome ?? nomeTema(c.temaId)}</Badge>
                      {c.secundarios.map((s) => (
                        <Badge key={s} variant="outline">
                          {nomeTema(s)}
                        </Badge>
                      ))}
                      {c.estiloGancho && <span className="text-xs text-muted-foreground">gancho: {estiloGanchoLabel[c.estiloGancho as EstiloGancho] ?? c.estiloGancho}</span>}
                      {c.origem ? (
                        <Badge variant={c.origem === "dono" ? "secondary" : "outline"}>{c.origem === "dono" ? "corrigida pelo dono" : "classificada pela IA"}</Badge>
                      ) : (
                        <Badge variant="outline">aguardando classificação</Badge>
                      )}
                      {c.evidenciaParcial && (
                        <Badge variant="outline" title="Vídeo sem corte do SociMan: a IA leu só a legenda e as hashtags.">
                          evidência parcial
                        </Badge>
                      )}
                      {c.reclassificar && <Badge variant="outline">reclassificar</Badge>}
                    </p>
                    {c.justificativa && <p className="text-xs text-muted-foreground">{c.justificativa}</p>}
                    {c.sugestaoTema && <p className="text-xs">A IA sugeriu um tema novo: &quot;{c.sugestaoTema}&quot;</p>}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {c.version > 0 && (
                      <Button type="button" size="sm" variant="ghost" onClick={() => setHistorico(c)} aria-label={`Histórico da classificação de ${c.post?.tituloCurto || "post"}`}>
                        <History aria-hidden="true" />
                        Histórico
                      </Button>
                    )}
                    {dono && editando !== c.videoId && (
                      <Button type="button" size="sm" variant="outline" onClick={() => setEditando(c.videoId)} aria-label={`Corrigir ${c.post?.tituloCurto || "post"}`}>
                        <Pencil aria-hidden="true" />
                        Corrigir
                      </Button>
                    )}
                  </div>
                </div>
                {dono && editando === c.videoId && (
                  <ClassificacaoEditor
                    classificacao={c}
                    temas={temas}
                    onCancelar={() => setEditando(null)}
                    onSalvo={async () => {
                      setEditando(null);
                      await onMudou();
                    }}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
        {d?.nextCursor && (
          <div>
            <Button type="button" variant="outline" size="sm" onClick={() => setLimit((l) => l + 50)} disabled={lista.isFetching}>
              Carregar mais
            </Button>
          </div>
        )}
      </div>
      {historico && <HistoricoClassificacao c={historico} nomeTema={nomeTema} onFechar={() => setHistorico(null)} onMudou={onMudou} />}
    </HeaderCard>
  );
}

function HistoricoClassificacao({
  c,
  nomeTema,
  onFechar,
  onMudou,
}: {
  c: AprendizadoClassificacao;
  nomeTema: (id: string | null | undefined) => string;
  onFechar: () => void;
  onMudou: () => Promise<unknown>;
}) {
  const versions = useClassificacaoVersions(c.videoId);
  return (
    <HistoricoDialog
      aberto
      onFechar={onFechar}
      titulo="Histórico da classificação"
      descricao={`${c.post?.tituloCurto || "Post sem legenda"} · taxonomia v${c.taxonomiaVersao}`}
      versions={versions.data?.items}
      carregando={versions.isPending}
      erro={versions.error}
      labels={classLabels}
      formatValue={(campo, v) => {
        if (campo === "tema_id") return nomeTema(v as string | null);
        if (campo === "secundarios") return Array.isArray(v) && v.length ? v.map((s) => nomeTema(String(s))).join(", ") : "—";
        if (campo === "estilo_gancho") return v ? (estiloGanchoLabel[v as EstiloGancho] ?? String(v)) : "—";
        if (campo === "origem") return v === "dono" ? "dono" : "IA";
        return formatarValor(v);
      }}
      onRevert={async (toVersion) => {
        await api.aprendizado.classificacoes.revert(c.videoId, c.version, toVersion);
        await Promise.all([onMudou(), versions.refetch()]);
      }}
    />
  );
}
