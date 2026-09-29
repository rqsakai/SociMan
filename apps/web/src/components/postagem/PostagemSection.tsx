/*
 * Seção "Postagem" do corte (spec 006, US5; T070). Uma aba por conta de destino (Q2 = A): cada
 * postagem tem título (até 100), descrição (até 2.000), hashtags (chips, 3 a 8 recomendadas), data e
 * hora planejadas e o estado (rascunho, agendado, postado à mão). Nada é publicado (princípio I).
 *
 * <PostagemSection corte contas postagens contaPadraoId onChanged />
 *   "Sugerir textos" / "Outra versão" (Claude; só preenche os campos, não salva), "Salvar",
 *   "Copiar título / descrição / hashtags / tudo", "Baixar vídeo" (corte com a marca),
 *   "Marcar como postado" (link opcional), "Cancelar postagem" (arquivar) e o histórico.
 */
import { ApiError, type Conta } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Check, ClipboardCopy, Download, History, Loader2, Plus, Save, Sparkles, X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { PlatformIcon } from "@/components/PlatformIcon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { VersionHistory } from "@/components/VersionHistory";
import { api } from "@/lib/api";
import { CLAUDE_AUSENTE_TEXTO, claudeAusente, integracoesQuery } from "@/lib/integracoes";
import type { Corte } from "@/lib/marca";
import { contaPlatformText, errorText } from "@/lib/perfis";
import {
  copyText,
  DESCRICAO_MAX,
  estadoLabel,
  estadoTone,
  HASHTAGS_MAX,
  HASHTAGS_MIN,
  normalizeHashtag,
  parseHashtags,
  postagemFieldLabel,
  postagemVersionsKey,
  textoCompleto,
  TITULO_MAX,
  type Postagem,
} from "@/lib/postagem";
import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/tz";
import { cn } from "@/lib/utils";

const contaText = (c: Pick<Conta, "platform" | "platformName" | "handle">) => `${contaPlatformText(c)} @${c.handle.replace(/^@/, "")}`;

export function PostagemSection({
  corte,
  contas,
  postagens,
  contaPadraoId,
  onChanged,
}: {
  corte: Corte;
  contas: Conta[];
  postagens: Postagem[];
  contaPadraoId?: string | null;
  onChanged: () => Promise<void>;
}) {
  const ativas = postagens.filter((p) => !p.archived);
  const contasAtivas = contas.filter((c) => !c.archived);
  // Abas: uma por postagem existente + as contas escolhidas agora (ainda sem postagem).
  const [novas, setNovas] = useState<string[]>(() => {
    const padrao = contaPadraoId && contasAtivas.some((c) => c.id === contaPadraoId) ? contaPadraoId : contasAtivas[0]?.id;
    return ativas.length === 0 && padrao ? [padrao] : [];
  });
  const contaIds = [...ativas.map((p) => p.conta.id), ...novas.filter((id) => !ativas.some((p) => p.conta.id === id))];
  const [tab, setTab] = useState(contaIds[0] ?? "");
  const current = contaIds.includes(tab) ? tab : (contaIds[0] ?? "");
  const livres = contasAtivas.filter((c) => !contaIds.includes(c.id));
  const [adding, setAdding] = useState("");

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Postagem</h2>
        </CardTitle>
        <CardDescription>
          Textos, data e hora para cada conta de destino. O SociMan não publica: na hora, ele avisa no sino e você posta.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {contasAtivas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Este perfil não tem contas ativas. Cadastre uma na aba Contas do perfil.</p>
        ) : (
          <Tabs value={current} onValueChange={setTab} className="gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <TabsList aria-label="Contas de destino" className="max-w-full justify-start overflow-x-auto">
                {contaIds.map((id) => {
                  const conta = contas.find((c) => c.id === id) ?? ativas.find((p) => p.conta.id === id)?.conta;
                  const post = ativas.find((p) => p.conta.id === id);
                  return (
                    <TabsTrigger key={id} value={id} className="gap-1.5">
                      {conta && <PlatformIcon platform={conta.platform} className="size-3.5" />}
                      {conta ? contaText(conta) : "Conta"}
                      {post && <span className={cn("ml-1 size-2 rounded-full", post.estado === "postado" ? "bg-success" : post.estado === "agendado" ? "bg-info" : "bg-muted-foreground/50")} aria-hidden="true" />}
                    </TabsTrigger>
                  );
                })}
              </TabsList>
              {livres.length > 0 && (
                <div className="flex items-center gap-1">
                  <NativeSelect aria-label="Adicionar conta de destino" value={adding} onChange={(e) => setAdding(e.target.value)} className="h-8 w-52 text-sm">
                    <option value="">Outra conta…</option>
                    {livres.map((c) => (
                      <option key={c.id} value={c.id}>
                        {contaText(c)}
                      </option>
                    ))}
                  </NativeSelect>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!adding}
                    onClick={() => {
                      setNovas((n) => [...n, adding]);
                      setTab(adding);
                      setAdding("");
                    }}
                  >
                    <Plus aria-hidden="true" />
                    Adicionar conta
                  </Button>
                </div>
              )}
            </div>
            {contaIds.map((id) => {
              const conta = contas.find((c) => c.id === id) ?? (ativas.find((p) => p.conta.id === id)?.conta as Conta | undefined);
              const post = ativas.find((p) => p.conta.id === id) ?? null;
              return (
                <TabsContent key={id} value={id}>
                  {conta && <PostagemEditor key={post ? `${post.id}-${post.version}` : `nova-${id}`} corte={corte} conta={conta} postagem={post} onChanged={onChanged} />}
                </TabsContent>
              );
            })}
          </Tabs>
        )}
      </CardContent>
    </Card>
  );
}

function PostagemEditor({
  corte,
  conta,
  postagem,
  onChanged,
}: {
  corte: Corte;
  conta: Pick<Conta, "id" | "platform" | "platformName" | "handle">;
  postagem: Postagem | null;
  onChanged: () => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const integracoes = useQuery(integracoesQuery);
  const semClaude = claudeAusente(integracoes.data);
  const [titulo, setTitulo] = useState(postagem?.titulo ?? "");
  const [descricao, setDescricao] = useState(postagem?.descricao ?? "");
  const [hashtags, setHashtags] = useState<string[]>(postagem?.hashtags ?? []);
  const [tagInput, setTagInput] = useState("");
  const [planned, setPlanned] = useState(toLocalInput(postagem?.plannedAt));
  const [sugestaoId, setSugestaoId] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"sugerir" | "salvar" | "postado" | "arquivar" | null>(null);
  const [postadoOpen, setPostadoOpen] = useState(false);
  const [postedUrl, setPostedUrl] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  const postado = postagem?.estado === "postado";
  const pronto = corte.status === "pronto";
  const dirty =
    !postagem ||
    titulo !== postagem.titulo ||
    descricao !== postagem.descricao ||
    hashtags.join(" ") !== postagem.hashtags.join(" ") ||
    planned !== toLocalInput(postagem.plannedAt);

  function addTags(text: string) {
    const tags = parseHashtags(text);
    if (tags.length === 0) return;
    setHashtags((cur) => [...cur, ...tags.filter((t) => !cur.includes(t))].slice(0, HASHTAGS_MAX));
    setTagInput("");
  }

  function onTagKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === "," || e.key === " ") {
      e.preventDefault();
      addTags(tagInput);
    } else if (e.key === "Backspace" && !tagInput && hashtags.length > 0) {
      setHashtags((cur) => cur.slice(0, -1));
    }
  }

  async function sugerir() {
    setError(null);
    setBusy("sugerir");
    try {
      const { sugestao } = await api.postagens.sugerir(corte.id, { contaId: conta.id, outraVersao: sugestaoId !== null || Boolean(titulo || descricao) });
      setTitulo(sugestao.titulo);
      setDescricao(sugestao.descricao);
      setHashtags(sugestao.hashtags.map((t) => normalizeHashtag(t) ?? t).slice(0, HASHTAGS_MAX));
      setSugestaoId(sugestao.id);
      toast.success("Sugestão nos campos. Revise e salve.", {
        description: sugestao.ajustes.length > 0 ? `Ajustes: ${sugestao.ajustes.join("; ")}` : undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["sugestoes", corte.id] });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (titulo.length > TITULO_MAX) errs.titulo = `Até ${TITULO_MAX} caracteres`;
    if (descricao.length > DESCRICAO_MAX) errs.descricao = `Até ${DESCRICAO_MAX} caracteres`;
    if (hashtags.length > HASHTAGS_MAX) errs.hashtags = `Até ${HASHTAGS_MAX} hashtags`;
    if (planned) {
      const iso = fromLocalInput(planned);
      if (!iso) errs.plannedAt = "Data e hora inválidas";
      else if (new Date(iso).getTime() < Date.now() - 60_000) errs.plannedAt = "Escolha um horário no futuro";
      else if (!pronto) errs.plannedAt = "Só dá para agendar depois que a marca estiver aplicada (corte pronto)";
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function salvar() {
    setError(null);
    if (!validate()) return;
    const plannedAt = planned ? fromLocalInput(planned) : null;
    setBusy("salvar");
    try {
      if (postagem) {
        await api.postagens.update(postagem.id, { version: postagem.version, titulo, descricao, hashtags, plannedAt });
      } else {
        await api.postagens.create(corte.id, {
          contaId: conta.id,
          titulo,
          descricao,
          hashtags,
          ...(plannedAt ? { plannedAt } : {}),
          ...(sugestaoId ? { sugestaoId } : {}),
        });
      }
      toast.success(plannedAt ? `Agendado para ${formatDateTime(plannedAt)}.` : "Postagem salva como rascunho.");
      await queryClient.invalidateQueries({ queryKey: ["calendario"] });
      await onChanged();
    } catch (err) {
      if (err instanceof ApiError && (err.code === "planned_in_past" || err.code === "corte_not_ready")) setFieldErrors({ plannedAt: err.message });
      else setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function marcarPostado() {
    if (!postagem) return;
    const url = postedUrl.trim();
    if (url && !/^https?:\/\/\S+$/i.test(url)) return setFieldErrors({ postedUrl: "Use um link http(s)" });
    setBusy("postado");
    try {
      await api.postagens.postado(postagem.id, { version: postagem.version, ...(url ? { postedUrl: url } : {}) });
      toast.success("Marcado como postado.");
      setPostadoOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["calendario"] });
      await onChanged();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  async function arquivar() {
    if (!postagem) return;
    setBusy("arquivar");
    try {
      await api.postagens.archive(postagem.id, postagem.version);
      toast.success("Postagem cancelada.");
      await queryClient.invalidateQueries({ queryKey: ["calendario"] });
      await onChanged();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  async function copy(what: string, text: string) {
    if (!text.trim()) return toast.info(`Nada para copiar em ${what}.`);
    if (await copyText(text)) toast.success(`${what[0]!.toUpperCase()}${what.slice(1)} copiado.`);
    else toast.error("Não foi possível copiar.");
  }

  async function baixar() {
    try {
      const { items } = await api.midia.links([{ kind: "corte_marcado", id: corte.id }]);
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

  const tagCountHint =
    hashtags.length < HASHTAGS_MIN ? `${hashtags.length}/${HASHTAGS_MAX}: recomendadas de ${HASHTAGS_MIN} a ${HASHTAGS_MAX}` : `${hashtags.length}/${HASHTAGS_MAX}`;

  return (
    <div className="space-y-4" aria-label={`Postagem em ${contaText(conta)}`} role="group">
      <div className="flex flex-wrap items-center gap-2">
        {postagem ? <Badge className={estadoTone[postagem.estado]}>{estadoLabel[postagem.estado]}</Badge> : <Badge variant="outline">Nova</Badge>}
        {postagem?.plannedAt && <span className="text-sm text-muted-foreground">para {formatDateTime(postagem.plannedAt)}</span>}
        {postagem?.postedAt && <span className="text-sm text-muted-foreground">postado em {formatDateTime(postagem.postedAt)}</span>}
        {postagem?.postedUrl && (
          <a href={postagem.postedUrl} target="_blank" rel="noreferrer noopener" className="text-sm underline">
            ver post
          </a>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={semClaude || postado || busy !== null}
            aria-busy={busy === "sugerir"}
            title={semClaude ? CLAUDE_AUSENTE_TEXTO : undefined}
            onClick={() => void sugerir()}
          >
            {busy === "sugerir" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
            {titulo || descricao || hashtags.length > 0 ? "Outra versão" : "Sugerir textos"}
          </Button>
        </div>
      </div>
      {semClaude && <p className="text-xs text-muted-foreground">{CLAUDE_AUSENTE_TEXTO}</p>}

      <Field label="Título" error={fieldErrors.titulo} hint={`${titulo.length}/${TITULO_MAX}`}>
        {({ id, describedBy, invalid }) => (
          <Input id={id} value={titulo} maxLength={TITULO_MAX} readOnly={postado} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setTitulo(e.target.value)} />
        )}
      </Field>
      <Field label="Descrição" error={fieldErrors.descricao} hint={`${descricao.length}/${DESCRICAO_MAX}`}>
        {({ id, describedBy, invalid }) => (
          <Textarea
            id={id}
            rows={5}
            value={descricao}
            maxLength={DESCRICAO_MAX}
            readOnly={postado}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setDescricao(e.target.value)}
          />
        )}
      </Field>
      <Field label="Hashtags" error={fieldErrors.hashtags} hint={tagCountHint}>
        {({ id, describedBy, invalid }) => (
          <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border px-2 py-1.5 focus-within:ring-[3px] focus-within:ring-ring/50">
            <ul aria-label="Hashtags escolhidas" className="contents">
              {hashtags.map((t) => (
                <li key={t}>
                  <Badge variant="secondary" className="gap-1 pr-1">
                    {t}
                    {!postado && (
                      <button type="button" aria-label={`Tirar ${t}`} className="rounded-full hover:bg-black/10" onClick={() => setHashtags((cur) => cur.filter((x) => x !== t))}>
                        <X className="size-3" aria-hidden="true" />
                      </button>
                    )}
                  </Badge>
                </li>
              ))}
            </ul>
            {!postado && hashtags.length < HASHTAGS_MAX && (
              <input
                id={id}
                value={tagInput}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                placeholder={hashtags.length === 0 ? "#achadinhos e Enter" : "+ hashtag"}
                className="min-w-24 flex-1 bg-transparent text-sm outline-none"
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={onTagKey}
                onBlur={() => addTags(tagInput)}
                onPaste={(e) => {
                  const text = e.clipboardData.getData("text");
                  if (/[\s,]/.test(text)) {
                    e.preventDefault();
                    addTags(text);
                  }
                }}
              />
            )}
          </div>
        )}
      </Field>
      <Field
        label="Data e hora (horário de Brasília)"
        error={fieldErrors.plannedAt}
        hint={pronto ? "Vazio: fica como rascunho. Na hora, o SociMan avisa no sino." : "Aplique a marca antes de agendar; os textos já podem ser preparados."}
      >
        {({ id, describedBy, invalid }) => (
          <div className="flex flex-wrap gap-2">
            <Input
              id={id}
              type="datetime-local"
              step={900}
              value={planned}
              readOnly={postado}
              disabled={!pronto && !planned}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setPlanned(e.target.value)}
              className="w-auto"
            />
            {planned && !postado && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setPlanned("")}>
                Tirar a data
              </Button>
            )}
          </div>
        )}
      </Field>

      {error !== null && <ApiErrorAlert error={error} onReload={() => void onChanged()} />}

      <div className="flex flex-wrap gap-2">
        {!postado && (
          <Button type="button" disabled={busy !== null || !dirty} aria-busy={busy === "salvar"} onClick={() => void salvar()}>
            {busy === "salvar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar
          </Button>
        )}
        {postagem && !postado && (
          <Button type="button" variant="outline" disabled={busy !== null || dirty} title={dirty ? "Salve antes" : undefined} onClick={() => setPostadoOpen(true)}>
            <Check aria-hidden="true" />
            Marcar como postado
          </Button>
        )}
        {pronto && (
          <Button type="button" variant="outline" onClick={() => void baixar()}>
            <Download aria-hidden="true" />
            Baixar vídeo
          </Button>
        )}
        {postagem && !postado && (
          <ConfirmButton
            label="Cancelar postagem"
            icon={Archive}
            variant="ghost"
            busy={busy === "arquivar"}
            title="Cancelar esta postagem?"
            description="A postagem é arquivada (sai do calendário) e o histórico continua."
            onConfirm={arquivar}
          />
        )}
      </div>

      <div className="flex flex-wrap gap-2 border-t pt-3" role="group" aria-label="Copiar textos">
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("título", titulo)}>
          <ClipboardCopy aria-hidden="true" />
          Copiar título
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("descrição", descricao)}>
          <ClipboardCopy aria-hidden="true" />
          Copiar descrição
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("hashtags", hashtags.join(" "))}>
          <ClipboardCopy aria-hidden="true" />
          Copiar hashtags
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => void copy("texto", textoCompleto({ titulo, descricao, hashtags }))}>
          <ClipboardCopy aria-hidden="true" />
          Copiar tudo
        </Button>
        {postagem && (
          <Button type="button" variant="ghost" size="sm" className="ml-auto" aria-expanded={showHistory} onClick={() => setShowHistory((s) => !s)}>
            <History aria-hidden="true" />
            {showHistory ? "Esconder histórico" : "Histórico"}
          </Button>
        )}
      </div>

      {postagem && showHistory && <PostagemHistorico postagem={postagem} onReverted={onChanged} />}

      <Dialog open={postadoOpen} onOpenChange={setPostadoOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Marcar como postado</DialogTitle>
            <DialogDescription>Confirme que você já postou este corte em {contaText(conta)}. O link do post é opcional.</DialogDescription>
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

function PostagemHistorico({ postagem, onReverted }: { postagem: Postagem; onReverted: () => Promise<void> }) {
  const versions = useQuery({ queryKey: postagemVersionsKey(postagem.id), queryFn: () => api.postagens.versions(postagem.id) });
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return (
    <VersionHistory
      versions={versions.data.items}
      labels={postagemFieldLabel}
      formatValue={(field, value) => {
        if (value === null || value === undefined || value === "") return "—";
        if (field === "estado" && typeof value === "string") return estadoLabel[value as Postagem["estado"]] ?? value;
        if (field === "planned_at" && typeof value === "string") return formatDateTime(value);
        if (Array.isArray(value)) return value.join(" ") || "—";
        if (typeof value === "boolean") return value ? "Sim" : "Não";
        return String(value);
      }}
      onRevert={
        postagem.estado === "postado"
          ? undefined
          : async (toVersion) => {
              await api.postagens.revert(postagem.id, postagem.version, toVersion);
              await onReverted();
            }
      }
      onReload={onReverted}
    />
  );
}
