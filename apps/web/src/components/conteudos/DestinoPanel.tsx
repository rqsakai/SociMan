/*
 * Destinos de um conteúdo (spec 014; evolução do PostagemSection da 006). Usado no detalhe do
 * conteúdo e no detalhe do corte (o id é o mesmo, R1).
 *
 * <DestinosSection conteudo conta? onContaChange? onChanged />
 *   Uma aba por conta de destino (`conta`/`onContaChange` ligam a aba ao `?conta=` da URL),
 *   "Adicionar conta" (cria o destino pendente) e, em cada aba, o <DestinoPanel>.
 *
 * <DestinoPanel conteudo destino onChanged />
 *   - textos (título, descrição, hashtags) com o assistente de IA da 008; editar depois da
 *     aprovação não desfaz a aprovação (Q2 = A);
 *   - aprovação: "Pedir aprovação" (com nota), "Aprovar" e "Recusar" (com motivo) só para dono; a
 *     recusa fica visível; aviso "o vídeo mudou desde a aprovação";
 *   - agendamento: "Agendar"/"Aprovar e agendar", "Reagendar" e "Cancelar agendamento" (modo com o
 *     motivo dos indisponíveis, no AgendarDialog);
 *   - "Copiar", "Baixar vídeo", "Postado" (link opcional), "Tirar esta conta" e o histórico.
 * Nada é publicado (princípio I): no horário, o SociMan avisa no sino e o humano posta.
 * spec 015: nos modos automáticos, o <ExecucaoStatus> mostra o envio (enviando, rascunho criado,
 * falhou, pausado, vencido, aguardando vaga) com as ações do dono e o histórico do envio.
 */
import type { Conteudo, Destino } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArchiveRestore,
  CalendarClock,
  CalendarX,
  Check,
  ClipboardCopy,
  ClipboardPaste,
  Download,
  Hand,
  History,
  Loader2,
  Plus,
  Save,
  ThumbsUp,
  TriangleAlert,
  X,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { PlatformIcon } from "@/components/PlatformIcon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { VersionHistory } from "@/components/VersionHistory";
import { IaAssist } from "@/components/ia/IaAssist";
import { EnviarAgora } from "@/components/publicacao/EnviarAgora";
import { ExecucaoStatus } from "@/components/publicacao/ExecucaoStatus";
import { LegendaFinal } from "@/components/publicacao/LegendaFinal";
import { api } from "@/lib/api";
import { destinoVersionsKey, estadoEfetivoTone, invalidarConteudos, propostaDe, useEhDono } from "@/lib/conteudos";
import { comRebase, useFormRebase, type IaAlvo, type IaAplicacao, type TextosPostagem } from "@/lib/ia";
import { contaPlatformText, errorText, perfilKey } from "@/lib/perfis";
import {
  copyText,
  DESCRICAO_MAX,
  destinoEstadoLabel,
  destinoFieldLabel,
  HASHTAGS_MAX,
  HASHTAGS_MIN,
  modoLabel,
  MOTIVO_MAX,
  textoCompleto,
  TITULO_MAX,
  LEGENDA_OBRIGATORIA,
  LEGENDA_TIKTOK_MAX,
  legendaTiktok,
  usaLegenda,
  type DestinoEstado,
  type Modo,
} from "@/lib/postagem";
import { destinoFieldLabel015, ehAutomatico } from "@/lib/publicacao";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";
import { AgendarDialog } from "./AgendarDialog";
import { EstadoBadge } from "./EstadoBadge";
import { HashtagsInput } from "./HashtagsInput";
import { RecusarDialog } from "./RecusarDialog";

const contaText = (c: Pick<Destino["conta"], "platform" | "platformName" | "handle">) => `${contaPlatformText(c)} @${c.handle.replace(/^@/, "")}`;

export function DestinosSection({
  conteudo,
  conta,
  onContaChange,
  onChanged,
}: {
  conteudo: Conteudo;
  conta?: string | null;
  onContaChange?: (contaId: string) => void;
  onChanged: () => Promise<void>;
}) {
  const perfil = useQuery({ queryKey: perfilKey(conteudo.perfil.id), queryFn: () => api.perfis.get(conteudo.perfil.id) });
  const ativos = conteudo.destinos.filter((d) => !d.archived);
  const contasAtivas = (perfil.data?.contas ?? []).filter((c) => !c.archived);
  const livres = contasAtivas.filter((c) => !ativos.some((d) => d.conta.id === c.id));
  const [tabLocal, setTabLocal] = useState<string | null>(null);
  const pedida = conta ?? tabLocal;
  const current = ativos.some((d) => d.conta.id === pedida) ? pedida! : (ativos[0]?.conta.id ?? "");
  const setTab = (id: string) => (onContaChange ? onContaChange(id) : setTabLocal(id));
  const [addOpen, setAddOpen] = useState(false);
  const [adding, setAdding] = useState("");
  const [busyAdd, setBusyAdd] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function adicionar() {
    if (!adding) return;
    setBusyAdd(true);
    setError(null);
    try {
      await api.conteudos.addDestino(conteudo.id, { contaId: adding });
      setTab(adding);
      setAdding("");
      setAddOpen(false);
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusyAdd(false);
    }
  }

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Contas de destino</h2>
        </CardTitle>
        <CardDescription>
          Aprovação, textos e agendamento por conta. O SociMan não publica: na hora, ele avisa no sino e você posta.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!conteudo.archived && livres.length > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setAdding(livres[0]?.id ?? "");
              setError(null);
              setAddOpen(true);
            }}
          >
            <Plus aria-hidden="true" />
            Adicionar conta
          </Button>
        )}
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Adicionar conta</DialogTitle>
              <DialogDescription>A conta entra como destino pendente; depois, aprove (ou peça aprovação) e agende.</DialogDescription>
            </DialogHeader>
            <Field label="Conta">
              {({ id }) => (
                <NativeSelect id={id} value={adding} onChange={(e) => setAdding(e.target.value)}>
                  {livres.map((c) => (
                    <option key={c.id} value={c.id}>
                      {contaText(c)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            {error !== null && <ApiErrorAlert error={error} />}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setAddOpen(false)}>
                Cancelar
              </Button>
              <Button type="button" disabled={!adding || busyAdd} aria-busy={busyAdd} onClick={() => void adicionar()}>
                {busyAdd ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
                Adicionar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        {perfil.isSuccess && contasAtivas.length === 0 && ativos.length === 0 && (
          <p className="text-sm text-muted-foreground">Este perfil não tem contas ativas. Cadastre uma na aba Contas do perfil.</p>
        )}
        {ativos.length === 0 && contasAtivas.length > 0 && (
          <p className="text-sm text-muted-foreground">Sem conta de destino ainda. Adicione uma conta ou use "Agendar".</p>
        )}
        {ativos.length > 0 && (
          <Tabs value={current} onValueChange={setTab} className="gap-4">
            <TabsList aria-label="Contas de destino" className="max-w-full justify-start overflow-x-auto">
              {ativos.map((d) => (
                <TabsTrigger key={d.conta.id} value={d.conta.id} className="gap-1.5">
                  <PlatformIcon platform={d.conta.platform} className="size-3.5" />
                  {contaText(d.conta)}
                  <span className={cn("ml-1 size-2 rounded-full", estadoEfetivoTone[d.estadoEfetivo].split(" ")[0])} aria-hidden="true" />
                </TabsTrigger>
              ))}
            </TabsList>
            {ativos.map((d) => (
              <TabsContent key={d.conta.id} value={d.conta.id}>
                <DestinoPanel key={`${d.id}-${d.version}`} conteudo={conteudo} destino={d} onChanged={onChanged} />
              </TabsContent>
            ))}
          </Tabs>
        )}
      </CardContent>
    </Card>
  );
}

interface Rascunho {
  titulo: string;
  descricao: string;
  hashtags: string[];
}

const EDITAVEL: DestinoEstado[] = ["pendente", "aprovacao_pedida", "aprovado", "agendado"];

export function DestinoPanel({ conteudo, destino, onChanged }: { conteudo: Conteudo; destino: Destino; onChanged: () => Promise<void> }) {
  const queryClient = useQueryClient();
  const dono = useEhDono();
  const rebase = useFormRebase<Partial<Rascunho>>(`destino:${destino.id}`);
  const volta = rebase.retomado ?? {};
  const [titulo, setTitulo] = useState(volta.titulo ?? destino.titulo);
  const [descricao, setDescricao] = useState(volta.descricao ?? destino.descricao);
  const [hashtags, setHashtags] = useState<string[]>(volta.hashtags ?? destino.hashtags);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"salvar" | "aprovar" | "pedir" | "cancelar" | "postado" | "arquivar" | null>(null);
  const [postadoOpen, setPostadoOpen] = useState(false);
  const [postedUrl, setPostedUrl] = useState("");
  const [pedirOpen, setPedirOpen] = useState(false);
  const [nota, setNota] = useState("");
  const [recusarOpen, setRecusarOpen] = useState(false);
  const [agendarOpen, setAgendarOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const conta = destino.conta;
  const proposta = propostaDe(conteudo);
  const ct = contaText(conta);
  // spec 015 (US3, Q2): textos de um "Publicar" agendado só o dono edita (vale como nova confirmação).
  const publicarSoDono = destino.modo === "publicar" && destino.estado === "agendado" && !dono;
  const editavel = !publicarSoDono && !destino.archived && !conteudo.archived && EDITAVEL.includes(destino.estado);
  const pronto = conteudo.situacao === "pronto";
  const aprovado = destino.estado === "aprovado" || destino.estado === "agendado";
  // spec 015: reagendar e cancelar um envio automático são só do dono humano (a API recusa o membro).
  const autoSoDono = ehAutomatico(destino.modo) && !dono;
  const dirty = titulo !== destino.titulo || descricao !== destino.descricao || hashtags.join(" ") !== destino.hashtags.join(" ");

  async function done(msg?: string) {
    if (msg) toast.success(msg);
    await invalidarConteudos(queryClient, conteudo.id);
    await onChanged();
  }

  async function run(kind: NonNullable<typeof busy>, fn: () => Promise<unknown>, msg: string) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      await done(msg);
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(null);
    }
  }

  // Aplicar do painel da IA: salva só os campos da proposta, com o `ia` no corpo; os outros campos
  // sujos voltam por cima do destino novo (spec 008, R-9).
  async function salvarComIa(campos: Partial<TextosPostagem>, ia: IaAplicacao[]) {
    const atuais: Rascunho = { titulo, descricao, hashtags };
    const salvos: Rascunho = { titulo: destino.titulo, descricao: destino.descricao, hashtags: destino.hashtags };
    const sujos: Partial<Rascunho> = {};
    for (const k of ["titulo", "descricao", "hashtags"] as const) {
      if (!(k in campos) && JSON.stringify(atuais[k]) !== JSON.stringify(salvos[k])) Object.assign(sujos, { [k]: atuais[k] });
    }
    await comRebase(rebase, Object.keys(sujos).length > 0 ? sujos : null, async () => {
      await api.destinos.update(destino.id, { version: destino.version, ...campos, ia });
    });
    await done();
  }
  const alvo: IaAlvo = { entityType: "postagem", entityId: destino.id };
  const iaProps = {
    perfilId: conteudo.perfil.id,
    alvo,
    disabled: !editavel,
    onReload: () => void onChanged(),
  };
  const iaSessao = (tipo: string) => `ia:${tipo}:postagem:${conteudo.id}:${conta.id}`;

  async function salvar() {
    const errs: Record<string, string> = {};
    if (titulo.length > TITULO_MAX) errs.titulo = `Até ${TITULO_MAX} caracteres`;
    if (descricao.length > DESCRICAO_MAX) errs.descricao = `Até ${DESCRICAO_MAX} caracteres`;
    if (hashtags.length > HASHTAGS_MAX) errs.hashtags = `Até ${HASHTAGS_MAX} hashtags`;
    // já agendado na TikTok: a API recusa tirar a legenda (400 `legenda_obrigatoria`)
    if (tiktok && destino.estado === "agendado" && !descricao.trim()) errs.descricao = LEGENDA_OBRIGATORIA;
    if (tiktok && legendaTiktok({ descricao, hashtags }).length > LEGENDA_TIKTOK_MAX) errs.descricao = `A legenda final passa de ${LEGENDA_TIKTOK_MAX.toLocaleString("pt-BR")} caracteres`;
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;
    await run("salvar", () => api.destinos.update(destino.id, { version: destino.version, titulo, descricao, hashtags }), "Textos salvos.");
  }

  async function marcarPostado() {
    const url = postedUrl.trim();
    if (url && !/^https?:\/\/\S+$/i.test(url)) return setFieldErrors({ postedUrl: "Use um link http(s)" });
    if (await run("postado", () => api.destinos.postado(destino.id, { version: destino.version, ...(url ? { postedUrl: url } : {}) }), "Marcado como postado.")) {
      setPostadoOpen(false);
    }
  }

  async function pedir() {
    const n = nota.trim();
    if (await run("pedir", () => api.destinos.pedirAprovacao(destino.id, { version: destino.version, ...(n ? { nota: n } : {}) }), "Aprovação pedida. Os donos foram avisados.")) {
      setPedirOpen(false);
      setNota("");
    }
  }

  async function copy(what: string, text: string) {
    if (!text.trim()) return toast.info(`Nada para copiar em ${what}.`);
    if (await copyText(text)) toast.success(`${what[0]!.toUpperCase()}${what.slice(1)} copiado.`);
    else toast.error("Não foi possível copiar.");
  }

  async function baixar() {
    try {
      const kind = conteudo.origem === "video_proprio" ? ("conteudo_video" as const) : ("corte_marcado" as const);
      const { items } = await api.midia.links([{ kind, id: conteudo.id }]);
      const url = items[0]?.url;
      if (!url) return;
      const a = document.createElement("a");
      a.href = `${url}${url.includes("?") ? "&" : "?"}download=1`;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  // spec 015 (T102): na TikTok não há título; a descrição é a "Legenda" (obrigatória) e a legenda
  // final é descrição + linha em branco + hashtags.
  const tiktok = usaLegenda(conta.platform);
  const semLegenda = tiktok && !destino.descricao.trim();
  const legendaAtual = legendaTiktok({ descricao, hashtags });

  const tagHint =
    hashtags.length < HASHTAGS_MIN ? `${hashtags.length}/${HASHTAGS_MAX}: recomendadas de ${HASHTAGS_MIN} a ${HASHTAGS_MAX}` : `${hashtags.length}/${HASHTAGS_MAX}`;

  return (
    <div className="space-y-4" role="group" aria-label={`Destino ${ct}`}>
      {/* Estado, agenda e avisos */}
      <div className="flex flex-wrap items-center gap-2">
        <EstadoBadge estado={destino.estadoEfetivo} motivo={destino.motivoAtencao} />
        {destino.plannedAt && (
          <span className="text-sm text-muted-foreground">
            {modoLabel[destino.modo as Modo]} · {formatDateTime(destino.plannedAt)}
          </span>
        )}
        {destino.postedAt && <span className="text-sm text-muted-foreground">postado em {formatDateTime(destino.postedAt)}</span>}
        {destino.postedUrl && (
          <a href={destino.postedUrl} target="_blank" rel="noreferrer noopener" className="text-sm underline">
            ver post
          </a>
        )}
        {destino.aprovacao && (
          <span className="text-xs text-muted-foreground">
            aprovado por {destino.aprovacao.por.name} em {formatDateTime(destino.aprovacao.em)}
          </span>
        )}
      </div>

      {destino.videoMudou && (
        <Alert>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>O vídeo mudou desde a aprovação</AlertTitle>
          <AlertDescription>A aprovação continua valendo. Confira o vídeo antes de postar.</AlertDescription>
        </Alert>
      )}
      {destino.recusa && destino.estado === "pendente" && (
        <Alert variant="destructive">
          <X aria-hidden="true" />
          <AlertTitle>
            Recusado por {destino.recusa.por.name} em {formatDateTime(destino.recusa.em)}
          </AlertTitle>
          <AlertDescription className="whitespace-pre-wrap">{destino.recusa.motivo}</AlertDescription>
        </Alert>
      )}
      {destino.pedido && destino.estado === "aprovacao_pedida" && (
        <Alert>
          <Hand aria-hidden="true" />
          <AlertTitle>
            Aprovação pedida por {destino.pedido.por.name} em {formatDateTime(destino.pedido.em)}
          </AlertTitle>
          {destino.pedido.nota && <AlertDescription className="whitespace-pre-wrap">{destino.pedido.nota}</AlertDescription>}
        </Alert>
      )}

      {publicarSoDono && (
        <p className="text-sm text-muted-foreground">Os textos de uma publicação agendada só um dono muda: a mudança vale como nova confirmação do que vai para a rede.</p>
      )}
      <ExecucaoStatus conteudo={conteudo} destino={destino} onChanged={onChanged} onPostado={() => setPostadoOpen(true)} onReagendar={() => setAgendarOpen(true)} />

      {/* Aprovação e agendamento */}
      {editavel && (
        <div className="flex flex-wrap gap-2 rounded-lg border bg-muted/30 p-2" role="group" aria-label="Aprovação e agendamento">
          {!aprovado && dono && (
            <Button
              type="button"
              size="sm"
              disabled={busy !== null || !pronto}
              title={pronto ? undefined : "Aplique a marca antes de aprovar"}
              aria-busy={busy === "aprovar"}
              onClick={() => void run("aprovar", () => api.destinos.aprovar(destino.id, destino.version), `Aprovado para ${ct}.`)}
            >
              {busy === "aprovar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ThumbsUp aria-hidden="true" />}
              Aprovar
            </Button>
          )}
          {destino.estado === "pendente" && !dono && (
            <Button type="button" size="sm" disabled={busy !== null || !pronto} onClick={() => setPedirOpen(true)}>
              <Hand aria-hidden="true" />
              Pedir aprovação
            </Button>
          )}
          {dono && (destino.estado === "aprovacao_pedida" || destino.estado === "aprovado") && (
            <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => setRecusarOpen(true)}>
              <X aria-hidden="true" />
              Recusar
            </Button>
          )}
          {destino.estado === "agendado" ? (
            !autoSoDono && (
            <>
              <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => setAgendarOpen(true)}>
                <CalendarClock aria-hidden="true" />
                Reagendar
              </Button>
              <ConfirmButton
                label="Cancelar agendamento"
                icon={CalendarX}
                size="sm"
                variant="ghost"
                busy={busy === "cancelar"}
                title="Cancelar o agendamento?"
                description={`O conteúdo continua aprovado para ${ct}, sem data.`}
                onConfirm={() => void run("cancelar", () => api.agendamentos.cancelar(destino.id, destino.version), "Agendamento cancelado.")}
              />
            </>
            )
          ) : (
            (aprovado || dono) && (
              <Button
                type="button"
                size="sm"
                variant={aprovado ? "default" : "outline"}
                disabled={busy !== null || !pronto || semLegenda}
                title={semLegenda ? LEGENDA_OBRIGATORIA : undefined}
                onClick={() => setAgendarOpen(true)}
              >
                <CalendarClock aria-hidden="true" />
                {aprovado ? "Agendar" : "Aprovar e agendar"}
              </Button>
            )
          )}
          {/* spec 015 (T100): envia o rascunho na próxima volta, sem escolher horário (só dono) */}
          {/* já agendado em "Publicar": publica agora com o modo e as opções salvos */}
          <EnviarAgora
            contaId={conta.id}
            handle={conta.handle}
            conteudoId={conteudo.id}
            {...(destino.modo === "publicar" && destino.estado === "agendado" ? { modo: "publicar" as const, opcoes: destino.opcoesRede ?? null } : {})}
            disabled={busy !== null || !pronto || dirty || semLegenda}
            destino={async () => destino}
            onDone={onChanged}
          />
          {aprovado && (
            <Button type="button" size="sm" variant="outline" disabled={busy !== null || dirty} title={dirty ? "Salve os textos antes" : undefined} onClick={() => setPostadoOpen(true)}>
              <Check aria-hidden="true" />
              Postado
            </Button>
          )}
          {!pronto && <p className="self-center text-xs text-muted-foreground">Aplique a marca antes de aprovar ou agendar.</p>}
          {pronto && semLegenda && destino.estado !== "agendado" && (
            <p role="note" className="self-center text-xs text-destructive">
              {LEGENDA_OBRIGATORIA}.
            </p>
          )}
        </div>
      )}

      {/* Textos */}
      <IaAssist<TextosPostagem>
        tipo="postagem.textos"
        {...iaProps}
        value={{ titulo, descricao, hashtags }}
        onSave={(v, ia) => salvarComIa({ titulo: v.titulo, descricao: v.descricao, hashtags: v.hashtags }, ia)}
        campo="Título, descrição e hashtags"
        botaoLabel="Sugerir textos"
        sessaoKey={iaSessao("postagem.textos")}
      >
        {(botao) => (
          <div className="flex flex-wrap justify-end gap-2">
            {/* T075: textos vazios → "Usar proposta do OpenShorts" preenche o formulário (salvar é com "Salvar textos"). */}
            {proposta && editavel && (tiktok || !titulo.trim()) && !descricao.trim() && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setTitulo((proposta.titulo || conteudo.titulo).slice(0, TITULO_MAX));
                  setDescricao((proposta.descricao ?? "").slice(0, DESCRICAO_MAX));
                }}
              >
                <ClipboardPaste aria-hidden="true" />
                Usar proposta do OpenShorts
              </Button>
            )}
            {botao}
          </div>
        )}
      </IaAssist>
      {!tiktok && (
      <IaAssist tipo="postagem.titulo" {...iaProps} value={titulo} onSave={(titulo, ia) => salvarComIa({ titulo }, ia)} campo="Título" sessaoKey={iaSessao("postagem.titulo")}>
        {(botao) => (
          <Field label="Título" action={botao} error={fieldErrors.titulo} hint={`${titulo.length}/${TITULO_MAX}`}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} value={titulo} maxLength={TITULO_MAX} readOnly={!editavel} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setTitulo(e.target.value)} />
            )}
          </Field>
        )}
      </IaAssist>
      )}
      <IaAssist
        tipo="postagem.descricao"
        {...iaProps}
        value={descricao}
        onSave={(descricao, ia) => salvarComIa({ descricao }, ia)}
        campo="Descrição"
        sessaoKey={iaSessao("postagem.descricao")}
      >
        {(botao) => (
          <Field
            label={tiktok ? "Legenda *" : "Descrição"}
            action={botao}
            error={fieldErrors.descricao}
            hint={tiktok ? `Obrigatória na TikTok (não há título). ${descricao.length}/${DESCRICAO_MAX}` : `${descricao.length}/${DESCRICAO_MAX}`}
          >
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={5}
                value={descricao}
                maxLength={DESCRICAO_MAX}
                readOnly={!editavel}
                aria-required={tiktok || undefined}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setDescricao(e.target.value)}
              />
            )}
          </Field>
        )}
      </IaAssist>
      <IaAssist
        tipo="postagem.hashtags"
        {...iaProps}
        value={hashtags}
        onSave={(hashtags, ia) => salvarComIa({ hashtags }, ia)}
        campo="Hashtags"
        sessaoKey={iaSessao("postagem.hashtags")}
      >
        {(botao) => (
          <Field label="Hashtags" action={botao} error={fieldErrors.hashtags} hint={tagHint}>
            {({ id, describedBy, invalid }) => (
              <HashtagsInput id={id} value={hashtags} onChange={setHashtags} readOnly={!editavel} invalid={invalid} describedBy={describedBy} />
            )}
          </Field>
        )}
      </IaAssist>
      {tiktok && <LegendaFinal legenda={legendaAtual} />}

      {error !== null && <ApiErrorAlert error={error} onReload={() => void onChanged()} />}

      <div className="flex flex-wrap gap-2">
        {editavel && (
          <Button type="button" disabled={busy !== null || !dirty} aria-busy={busy === "salvar"} onClick={() => void salvar()}>
            {busy === "salvar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar textos
          </Button>
        )}
        {pronto && (
          <Button type="button" variant="outline" onClick={() => void baixar()}>
            <Download aria-hidden="true" />
            Baixar vídeo
          </Button>
        )}
        {!conteudo.archived && destino.estado !== "postado" && destino.estado !== "enviando" && (
          <ConfirmButton
            label={destino.archived ? "Restaurar esta conta" : "Tirar esta conta"}
            icon={destino.archived ? ArchiveRestore : Archive}
            variant="ghost"
            busy={busy === "arquivar"}
            title={destino.archived ? `Restaurar ${ct}?` : `Tirar ${ct} deste conteúdo?`}
            description={destino.archived ? "A conta volta como destino deste conteúdo." : "O destino é arquivado (sai do calendário e da lista); o histórico continua."}
            onConfirm={() =>
              void run(
                "arquivar",
                () => (destino.archived ? api.destinos.restore(destino.id, destino.version) : api.destinos.archive(destino.id, destino.version)),
                destino.archived ? "Conta restaurada." : "Conta tirada deste conteúdo.",
              )
            }
          />
        )}
      </div>

      <div className="flex flex-wrap gap-2 border-t pt-3" role="group" aria-label="Copiar textos">
        {tiktok ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => void copy("legenda", legendaAtual)}>
            <ClipboardCopy aria-hidden="true" />
            Copiar legenda
          </Button>
        ) : (
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("título", titulo)}>
          <ClipboardCopy aria-hidden="true" />
          Copiar título
        </Button>
        )}
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("descrição", descricao)}>
          <ClipboardCopy aria-hidden="true" />
          Copiar descrição
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("hashtags", hashtags.join(" "))}>
          <ClipboardCopy aria-hidden="true" />
          Copiar hashtags
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("texto", tiktok ? legendaAtual : textoCompleto({ titulo, descricao, hashtags }))}>
          <ClipboardCopy aria-hidden="true" />
          Copiar tudo
        </Button>
        <Button type="button" variant="ghost" size="sm" className="ml-auto" aria-expanded={showHistory} onClick={() => setShowHistory((s) => !s)}>
          <History aria-hidden="true" />
          {showHistory ? "Esconder histórico" : "Histórico desta conta"}
        </Button>
      </div>

      {showHistory && <DestinoHistorico destino={destino} onReverted={() => done()} />}

      <AgendarDialog
        open={agendarOpen}
        onOpenChange={setAgendarOpen}
        conteudo={{ id: conteudo.id, perfilId: conteudo.perfil.id, titulo: conteudo.titulo, situacao: conteudo.situacao, proposta, origem: conteudo.origem, posterUrl: conteudo.posterUrl }}
        destinos={conteudo.destinos}
        contaId={conta.id}
        onDone={onChanged}
      />
      <RecusarDialog destino={destino} contaText={ct} open={recusarOpen} onOpenChange={setRecusarOpen} onDone={() => done("Recusado; quem pediu foi avisado.")} />

      <Dialog open={pedirOpen} onOpenChange={setPedirOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Pedir aprovação para {ct}</DialogTitle>
            <DialogDescription>Os donos recebem o aviso no sino. A nota é opcional.</DialogDescription>
          </DialogHeader>
          <Field label="Nota para o dono (opcional)" hint={`${nota.length}/${MOTIVO_MAX}`}>
            {({ id, describedBy }) => (
              <Textarea id={id} rows={3} maxLength={MOTIVO_MAX} value={nota} aria-describedby={describedBy} onChange={(e) => setNota(e.target.value)} />
            )}
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setPedirOpen(false)}>
              Cancelar
            </Button>
            <Button type="button" disabled={busy !== null} aria-busy={busy === "pedir"} onClick={() => void pedir()}>
              {busy === "pedir" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Hand aria-hidden="true" />}
              Pedir aprovação
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={postadoOpen} onOpenChange={setPostadoOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Marcar como postado</DialogTitle>
            <DialogDescription>Confirme que você já postou este conteúdo em {ct}. O link do post é opcional.</DialogDescription>
          </DialogHeader>
          <Field label="Link do post (opcional)" error={fieldErrors.postedUrl}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} type="url" value={postedUrl} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setPostedUrl(e.target.value)} />
            )}
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setPostadoOpen(false)}>
              Cancelar
            </Button>
            <Button type="button" disabled={busy !== null} aria-busy={busy === "postado"} onClick={() => void marcarPostado()}>
              {busy === "postado" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
              Confirmar postado
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DestinoHistorico({ destino, onReverted }: { destino: Destino; onReverted: () => Promise<void> }) {
  const versions = useQuery({ queryKey: destinoVersionsKey(destino.id), queryFn: () => api.destinos.versions(destino.id) });
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return (
    <VersionHistory
      versions={versions.data.items}
      labels={{ ...destinoFieldLabel, ...destinoFieldLabel015 }}
      formatValue={(field, value) => {
        if (value === null || value === undefined || value === "") return "—";
        if (field === "estado" && typeof value === "string") return destinoEstadoLabel[value as DestinoEstado] ?? value;
        if (field === "modo" && typeof value === "string") return modoLabel[value as Modo] ?? value;
        if ((field === "planned_at" || field === "aprovado_em") && typeof value === "string") return formatDateTime(value);
        if (Array.isArray(value)) return value.join(" ") || "—";
        if (typeof value === "boolean") return value ? "Sim" : "Não";
        if (typeof value === "object") return JSON.stringify(value);
        return String(value);
      }}
      onRevert={
        destino.estado === "postado" || destino.estado === "enviando"
          ? undefined
          : async (toVersion) => {
              await api.destinos.revert(destino.id, destino.version, toVersion);
              await onReverted();
            }
      }
      onReload={onReverted}
    />
  );
}
