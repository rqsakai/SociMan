/*
 * "Agendar" (spec 014, US3; R6, R14): o mesmo diálogo no detalhe do conteúdo, nas linhas da lista,
 * no corte pronto, na aba Cortes do perfil e no calendário.
 *
 * <AgendarDialog open onOpenChange conteudo={{ id, perfilId, titulo, situacao }} destinos contaId plannedAt onDone />
 *
 * - Conta (só as do perfil), data e hora (horário de Brasília), modo (os indisponíveis desabilitados
 *   com o motivo) e os textos com "Gerar com IA" (o Aplicar só preenche o formulário; o `ia` vai no
 *   corpo do agendamento).
 * - Dono diante de um destino não aprovado: "Aprovar e agendar" (a API aprova e agenda no mesmo
 *   passo). Membro diante de um não aprovado: "Pedir aprovação" (Q1 = A).
 * - Destino já agendado nesta conta: vira "Reagendar" (data, hora e modo; os textos ficam no painel).
 * - 409 `intervalo_conflito` (Q3): mostra os posts próximos e o intervalo mínimo da conta, com
 *   "Manter mesmo assim" (reenvia com `ignorarIntervalo: true`) e "Escolher outro horário".
 * - spec 015 (US2): "Criar rascunho no horário" com a conta conectada (só dono; o membro vê o modo
 *   desabilitado), aviso do sandbox e de "Publicação automática" desligada (fica pausado), avisos da
 *   rede depois de agendar e, num envio que falhou, "Reagendar" com a caixa "Conferi no app e o
 *   rascunho não chegou" quando a falha é incerta. "Publicar no horário" fica para a US3.
 */
import { ApiError, type Destino, type DestinoResumo, type IaAplicacao, type Modo, type OpcoesTikTok, type Origem, type Situacao } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CirclePause, Hand, Info, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { IaAssist } from "@/components/ia/IaAssist";
import { ConfirmoNaoChegou } from "@/components/publicacao/ConfirmoNaoChegou";
import { EnviarAgora } from "@/components/publicacao/EnviarAgora";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { invalidarConteudos, useEhDono, type PropostaOpenshorts } from "@/lib/conteudos";
import { padroesKey } from "@/lib/envios";
import type { IaAlvo, TextosPostagem } from "@/lib/ia";
import { contaPlatformText, perfilKey } from "@/lib/perfis";
import { conflitoIntervalo, modosKey, DESCRICAO_MAX, HASHTAGS_MAX, TITULO_MAX, LEGENDA_OBRIGATORIA, LEGENDA_TIKTOK_MAX, legendaTiktok, usaLegenda, type ConflitoIntervalo } from "@/lib/postagem";
import { LegendaFinal } from "@/components/publicacao/LegendaFinal";
import { TikTokPostForm } from "@/components/publicacao/TikTokPostForm";
import { AVISO_SANDBOX, problemasDaApi, ehAutomatico, enviosDesligadosTexto, enviosLigados, usePublicacaoConfig } from "@/lib/publicacao";
import { addDays, formatDateTime, fromLocalInput, localDateKey, toLocalInput } from "@/lib/tz";
import { HashtagsInput } from "./HashtagsInput";
import { ModoSelect } from "./ModoSelect";

// O que o diálogo precisa saber de cada destino existente do conteúdo (o resumo da lista basta;
// o destino completo do detalhe traz também os textos).
export type DestinoDoConteudo = Pick<DestinoResumo, "id" | "version" | "estado" | "conta" | "plannedAt" | "modo"> &
  Partial<Pick<Destino, "titulo" | "descricao" | "hashtags" | "archived" | "falhaIncerta" | "opcoesRede">>;

export interface AgendarConteudo {
  id: string;
  perfilId: string;
  titulo: string;
  situacao: Situacao;
  // T075: a proposta do OpenShorts preenche os textos vazios.
  proposta?: PropostaOpenshorts | null;
  // spec 015 (US3): para a prévia do vídeo na tela de "Publicar"
  origem?: Origem;
  posterUrl?: string | null;
}

const APROVADOS = ["aprovado", "agendado", "falhou"];
// Já saiu (ou está saindo) para a rede: nada a agendar nesta conta.
const FINAIS = ["postado", "rascunho_criado", "publicado"];

// Amanhã às 19h: o horário padrão quando não vem um do calendário.
const padraoInput = () => `${addDays(localDateKey(new Date()), 1)}T19:00`;

export function AgendarDialog({
  open,
  onOpenChange,
  conteudo,
  destinos = [],
  contaId: contaInicial,
  plannedAt: plannedInicial,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conteudo: AgendarConteudo;
  destinos?: DestinoDoConteudo[];
  contaId?: string | null;
  plannedAt?: string | null;
  onDone?: () => Promise<void> | void;
}) {
  const queryClient = useQueryClient();
  const dono = useEhDono();
  const perfil = useQuery({ queryKey: perfilKey(conteudo.perfilId), queryFn: () => api.perfis.get(conteudo.perfilId), enabled: open });
  const padroes = useQuery({ queryKey: padroesKey(conteudo.perfilId), queryFn: () => api.padroesCorte.get(conteudo.perfilId), enabled: open });
  const contas = (perfil.data?.contas ?? []).filter((c) => !c.archived);

  const [contaId, setContaId] = useState("");
  const [planned, setPlanned] = useState("");
  const [modo, setModo] = useState<Modo>("lembrete");
  const [textos, setTextos] = useState<TextosPostagem>({ titulo: "", descricao: "", hashtags: [] });
  const [textosIniciais, setTextosIniciais] = useState<TextosPostagem>(textos);
  const [ia, setIa] = useState<IaAplicacao[]>([]);
  const [dataErro, setDataErro] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [conflito, setConflito] = useState<{ intervaloMin: number; conflitos: ConflitoIntervalo[] } | null>(null);
  const [busy, setBusy] = useState<"agendar" | "pedir" | null>(null);
  const [naoChegou, setNaoChegou] = useState(false);
  const [opcoes, setOpcoes] = useState<OpcoesTikTok | null>(null);
  const config = usePublicacaoConfig();
  const dataRef = useRef<HTMLInputElement>(null);

  // Ao abrir: conta pedida, a padrão do perfil ou a primeira; horário pedido ou amanhã 19h.
  useEffect(() => {
    if (!open) return;
    setPlanned(plannedInicial ? toLocalInput(plannedInicial) : padraoInput());
    setDataErro(null);
    setError(null);
    setConflito(null);
    setIa([]);
    setNaoChegou(false);
  }, [open, plannedInicial]);
  useEffect(() => {
    if (!open || contas.length === 0) return;
    const padrao = padroes.data?.padroes.contaPadraoId;
    const escolhida = [contaInicial, destinos.find((d) => !d.archived)?.conta.id, padrao].find((id) => id && contas.some((c) => c.id === id));
    setContaId(escolhida ?? contas[0]!.id);
  }, [open, perfil.data, padroes.data, contaInicial]); // eslint-disable-line react-hooks/exhaustive-deps

  const destino = destinos.find((d) => d.conta.id === contaId && !d.archived) ?? null;
  // Textos e modo do destino desta conta (ou vazios) ao trocar de conta.
  useEffect(() => {
    const t = { titulo: destino?.titulo ?? "", descricao: destino?.descricao ?? "", hashtags: destino?.hashtags ?? [] };
    setTextosIniciais(t);
    // Destino novo: o título do conteúdo já vem sugerido (e vai no corpo, porque difere do inicial).
    // T075: com a proposta do OpenShorts, título e descrição vazios vêm preenchidos com ela.
    const p = conteudo.proposta;
    const vazio = !destino || (destino.titulo === "" && !destino.descricao);
    if (p && vazio) {
      setTextos({
        ...t,
        titulo: (p.titulo || conteudo.titulo).slice(0, TITULO_MAX),
        descricao: (p.descricao ?? "").slice(0, DESCRICAO_MAX),
      });
    } else setTextos(destino ? t : { ...t, titulo: conteudo.titulo.slice(0, TITULO_MAX) });
    setModo(destino?.modo ?? "lembrete");
    if (destino?.plannedAt && !plannedInicial) setPlanned(toLocalInput(destino.plannedAt));
    setConflito(null);
    setError(null);
  }, [contaId, destino?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const conta = contas.find((c) => c.id === contaId);
  // spec 015 (T102): na TikTok não há título; a legenda (descrição + hashtags) é obrigatória. Com o
  // destino da lista (sem textos), quem confere é a API (400 `legenda_obrigatoria`).
  const tiktok = conta ? usaLegenda(conta.platform) : false;
  const textosConhecidos = !destino || destino.descricao !== undefined;
  const legenda = legendaTiktok(textos);
  const semLegenda = tiktok && textosConhecidos && !textos.descricao.trim();
  const legendaLonga = tiktok && legenda.length > LEGENDA_TIKTOK_MAX;
  const contaText = conta ? `${contaPlatformText(conta)} @${conta.handle}` : "";
  const reagendar = destino?.estado === "agendado" || destino?.estado === "falhou";
  const aprovado = destino ? APROVADOS.includes(destino.estado) : false;
  const postado = destino ? FINAIS.includes(destino.estado) : false;
  const enviando = destino?.estado === "enviando";
  const incerta = destino?.estado === "falhou" && Boolean(destino.falhaIncerta);
  const automatico = ehAutomatico(modo);
  // Reagendar um envio automático (agendado ou que falhou) é só do dono humano (a API recusa o membro).
  const soDono = !dono && Boolean(destino && reagendar && ehAutomatico(destino.modo));
  const cfg = config.data?.config;
  const pronto = conteudo.situacao === "pronto";
  const precisaPedir = !dono && !aprovado;
  const textosMudaram = JSON.stringify(textos) !== JSON.stringify(textosIniciais);

  async function concluir(msg: string) {
    toast.success(msg);
    await invalidarConteudos(queryClient, conteudo.id);
    await onDone?.();
    onOpenChange(false);
  }

  // Prévia do vídeo final na tela de "Publicar" (link de 1 h, só quando o modo está aberto).
  const videoKind = conteudo.origem === "video_proprio" ? ("conteudo_video" as const) : ("corte_marcado" as const);
  const video = useQuery({
    queryKey: ["conteudo-links", conteudo.id, videoKind],
    queryFn: () => api.midia.links([{ kind: videoKind, id: conteudo.id }]),
    enabled: open && modo === "publicar" && pronto,
    staleTime: 50 * 60_000,
  });
  const videoUrl = video.data?.items[0]?.url ?? null;
  const publicar = modo === "publicar";

  async function agendar(ignorarIntervalo = false) {
    setError(null);
    setDataErro(null);
    const plannedAt = fromLocalInput(planned);
    if (!plannedAt) return setDataErro("Escolha a data e a hora");
    if (new Date(plannedAt).getTime() < Date.now() - 60_000) return setDataErro("Escolha um horário no futuro");
    if (!contaId) return setError(new ApiError(400, "validation_error", "Escolha a conta de destino."));
    setBusy("agendar");
    try {
      if (reagendar && destino) {
        const r = await api.agendamentos.update(destino.id, {
          version: destino.version,
          plannedAt,
          modo,
          ...(ignorarIntervalo ? { ignorarIntervalo } : {}),
          ...(incerta ? { confirmoQueNaoChegou: naoChegou } : {}),
          ...(publicar && opcoes ? { opcoes } : {}),
        });
        avisarRede(r.destino.avisosRede);
        await concluir(`Reagendado para ${formatDateTime(plannedAt)}.`);
      } else {
        const r = await api.agendamentos.create({
          conteudoId: conteudo.id,
          contaId,
          plannedAt,
          modo,
          ...(destino ? { destinoVersion: destino.version } : {}),
          ...(textosMudaram || ia.length > 0 ? { textos } : {}),
          ...(ia.length > 0 ? { ia } : {}),
          ...(ignorarIntervalo ? { ignorarIntervalo } : {}),
          ...(publicar && opcoes ? { opcoes } : {}),
        });
        avisarRede(r.destino.avisosRede);
        await concluir(`${aprovado ? "Agendado" : "Aprovado e agendado"} para ${formatDateTime(plannedAt)} em ${contaText}.`);
      }
    } catch (err) {
      const c = conflitoIntervalo(err);
      if (c) setConflito(c);
      else if (err instanceof ApiError && err.code === "planned_in_past") setDataErro(err.message);
      else if (err instanceof ApiError && err.code === "modo_indisponivel") {
        setError(err);
        void queryClient.invalidateQueries({ queryKey: modosKey(contaId) });
      }
      else setError(err);
    } finally {
      setBusy(null);
    }
  }

  // Duração, tamanho ou proporção fora das regras da rede: agenda assim mesmo e avisa (spec 015).
  function avisarRede(avisos: string[] | undefined) {
    for (const a of avisos ?? []) toast.warning(a, { duration: 10_000 });
  }

  // "Enviar rascunho agora" (T100): usa o destino desta conta (criado aqui se ainda não existe), gravando antes
  // os textos editados no diálogo.
  async function destinoParaEnviar(): Promise<{ id: string; version: number }> {
    const t = textosMudaram || ia.length > 0 ? { ...textos, ...(ia.length > 0 ? { ia } : {}) } : {};
    if (!destino) return (await api.conteudos.addDestino(conteudo.id, { contaId, ...t })).destino;
    if (Object.keys(t).length > 0) return (await api.destinos.update(destino.id, { version: destino.version, ...t })).destino;
    return destino;
  }

  async function pedir() {
    setError(null);
    setBusy("pedir");
    try {
      if (destino) {
        await api.destinos.pedirAprovacao(destino.id, { version: destino.version });
      } else {
        const r = await api.destinos.lotePedirAprovacao({ contaId, conteudoIds: [conteudo.id] });
        const falha = r.falhas[0];
        if (falha) throw new ApiError(409, "conflict", falha.message);
      }
      await concluir(`Aprovação pedida para ${contaText}. Os donos foram avisados.`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  const iaAlvo: IaAlvo = destino ? { entityType: "postagem", entityId: destino.id } : { entityType: "conteudo", entityId: conteudo.id, contaId };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{reagendar ? "Reagendar" : "Agendar"}</DialogTitle>
          <DialogDescription className="line-clamp-2">{conteudo.titulo || "Conteúdo sem título"}</DialogDescription>
        </DialogHeader>

        {!pronto && (
          <Alert>
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>Ainda não está pronto</AlertTitle>
            <AlertDescription>Aplique a marca antes de agendar; os textos já podem ser preparados no painel.</AlertDescription>
          </Alert>
        )}

        <div className="space-y-4">
          <Field label="Conta de destino">
            {({ id }) => (
              <NativeSelect id={id} value={contaId} onChange={(e) => setContaId(e.target.value)}>
                {contas.length === 0 && <option value="">{perfil.isPending ? "Carregando…" : "Nenhuma conta ativa no perfil"}</option>}
                {contas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {contaPlatformText(c)} @{c.handle}
                    {c.status === "pausada" || c.status === "encerrada" ? ` (${c.status})` : ""}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>

          {postado ? (
            <p className="text-sm text-muted-foreground">Este conteúdo já foi postado nesta conta.</p>
          ) : enviando ? (
            <p className="text-sm text-muted-foreground">O vídeo está sendo enviado para esta conta agora. Espere o envio terminar.</p>
          ) : soDono ? (
            <p className="text-sm text-muted-foreground">Só um dono reagenda um envio automático.</p>
          ) : precisaPedir ? (
            <Alert>
              <Hand aria-hidden="true" />
              <AlertTitle>{destino?.estado === "aprovacao_pedida" ? "Aprovação já pedida" : "Precisa de aprovação"}</AlertTitle>
              <AlertDescription>
                {destino?.estado === "aprovacao_pedida"
                  ? "Um dono ainda vai aprovar este conteúdo para esta conta. Depois, você agenda."
                  : "Só um dono aprova. Peça a aprovação; os donos recebem o aviso no sino."}
              </AlertDescription>
            </Alert>
          ) : (
            <>
              <Field label="Data e hora (horário de Brasília)" error={dataErro ?? undefined}>
                {({ id, describedBy, invalid }) => (
                  <Input
                    ref={dataRef}
                    id={id}
                    type="datetime-local"
                    step={300}
                    value={planned}
                    aria-invalid={invalid}
                    aria-describedby={describedBy}
                    onChange={(e) => {
                      setPlanned(e.target.value);
                      setConflito(null);
                    }}
                    className="w-auto"
                  />
                )}
              </Field>
              <ModoSelect contaId={contaId || null} value={modo} onChange={setModo} dono={dono} />
              {/* spec 015 (US3): a tela obrigatória da TikTok, consultada ao escolher "Publicar" */}
              {modo === "publicar" && contaId && (
                <TikTokPostForm
                  key={`${contaId}-${destino?.id ?? "novo"}`}
                  contaId={contaId}
                  videoUrl={videoUrl}
                  posterUrl={conteudo.posterUrl}
                  legenda={legenda}
                  inicial={destino?.opcoesRede}
                  onChange={setOpcoes}
                />
              )}
              {automatico && cfg && cfg.situacaoApp === "sandbox" && conta?.platform === "tiktok" && (
                <Alert>
                  <Info aria-hidden="true" />
                  <AlertTitle>App da TikTok em sandbox</AlertTitle>
                  <AlertDescription>{AVISO_SANDBOX}</AlertDescription>
                </Alert>
              )}
              {automatico && cfg && !enviosLigados(cfg) && (
                <Alert>
                  <CirclePause aria-hidden="true" />
                  <AlertTitle>Publicação automática desligada: vai ficar pausado</AlertTitle>
                  <AlertDescription>{enviosDesligadosTexto(cfg)} No horário, o envio fica "Pausado" até os envios serem ligados.</AlertDescription>
                </Alert>
              )}
              {incerta && <ConfirmoNaoChegou checked={naoChegou} onChange={setNaoChegou} />}
              {!reagendar && (
                <fieldset className="space-y-3 rounded-lg border p-3">
                  <legend className="px-1 text-sm font-medium">Textos</legend>
                  {destino && destino.titulo === undefined && (
                    <p className="text-xs text-muted-foreground">Os textos já salvos nesta conta continuam; preencha só para trocar.</p>
                  )}
                  <IaAssist<TextosPostagem>
                    tipo="postagem.textos"
                    perfilId={conteudo.perfilId}
                    alvo={iaAlvo}
                    value={textos}
                    onSave={async (v, aplicacoes) => {
                      setTextos({ titulo: v.titulo, descricao: v.descricao, hashtags: v.hashtags });
                      setIa(aplicacoes);
                    }}
                    campo={tiktok ? "Legenda e hashtags" : "Título, descrição e hashtags"}
                    botaoLabel="Gerar com IA"
                    sessaoKey={`ia:postagem.textos:agendar:${conteudo.id}:${contaId}`}
                  >
                    {(botao) => <div className="flex justify-end">{botao}</div>}
                  </IaAssist>
                  {!tiktok && (
                  <Field label="Título" hint={`${textos.titulo.length}/${TITULO_MAX}`}>
                    {({ id, describedBy }) => (
                      <Input id={id} value={textos.titulo} maxLength={TITULO_MAX} aria-describedby={describedBy} onChange={(e) => setTextos((t) => ({ ...t, titulo: e.target.value }))} />
                    )}
                  </Field>
                  )}
                  <Field
                    label={tiktok ? "Legenda *" : "Descrição"}
                    hint={tiktok ? `Obrigatória na TikTok (não há título). ${textos.descricao.length}/${DESCRICAO_MAX}` : `${textos.descricao.length}/${DESCRICAO_MAX}`}
                  >
                    {({ id, describedBy }) => (
                      <Textarea
                        id={id}
                        rows={3}
                        value={textos.descricao}
                        maxLength={DESCRICAO_MAX}
                        aria-required={tiktok || undefined}
                        aria-describedby={describedBy}
                        onChange={(e) => setTextos((t) => ({ ...t, descricao: e.target.value }))}
                      />
                    )}
                  </Field>
                  <Field label="Hashtags" hint={`${textos.hashtags.length}/${HASHTAGS_MAX}`}>
                    {({ id, describedBy }) => (
                      <HashtagsInput id={id} describedBy={describedBy} value={textos.hashtags} onChange={(hashtags) => setTextos((t) => ({ ...t, hashtags }))} />
                    )}
                  </Field>
                  {tiktok && <LegendaFinal legenda={legenda} />}
                </fieldset>
              )}
              {(semLegenda || legendaLonga) && (
                <p role="note" className="text-sm text-destructive">
                  {legendaLonga ? `A legenda final passa de ${LEGENDA_TIKTOK_MAX.toLocaleString("pt-BR")} caracteres.` : `${LEGENDA_OBRIGATORIA}.`}
                </p>
              )}
            </>
          )}

          {conflito && (
            <Alert variant="destructive" role="alert">
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>Perto de outro post em {contaText}</AlertTitle>
              <AlertDescription>
                <p>Há outro post perto deste horário; o intervalo mínimo é {conflito.intervaloMin} min.</p>
                <ul className="list-disc pl-5">
                  {conflito.conflitos.map((c) => (
                    <li key={c.destinoId}>
                      {formatDateTime(c.plannedAt)}: {c.titulo || "Sem título"}
                    </li>
                  ))}
                </ul>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => void agendar(true)}>
                    Manter mesmo assim
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setConflito(null);
                      dataRef.current?.focus();
                    }}
                  >
                    Escolher outro horário
                  </Button>
                </div>
              </AlertDescription>
            </Alert>
          )}
          {error !== null && <ApiErrorAlert error={error} />}
          {problemasDaApi(error).length > 0 && (
            <ul className="list-disc pl-5 text-sm text-destructive" aria-label="Regras da TikTok">
              {problemasDaApi(error).map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          {!postado &&
            !enviando &&
            !soDono &&
            (precisaPedir ? (
              destino?.estado !== "aprovacao_pedida" && (
                <Button type="button" disabled={busy !== null || !contaId || !pronto} aria-busy={busy === "pedir"} onClick={() => void pedir()}>
                  {busy === "pedir" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Hand aria-hidden="true" />}
                  Pedir aprovação
                </Button>
              )
            ) : (
              <>
              {conta && (
                <EnviarAgora
                  contaId={conta.id}
                  handle={conta.handle}
                  conteudoId={conteudo.id}
                  falhaIncerta={incerta}
                  {...(publicar ? { modo: "publicar" as const, opcoes } : {})}
                  disabled={busy !== null || !pronto || semLegenda || legendaLonga || (publicar && !opcoes)}
                  destino={destinoParaEnviar}
                  onDone={async () => {
                    await onDone?.();
                    onOpenChange(false);
                  }}
                  size="default"
                />
              )}
              <Button type="button" disabled={busy !== null || !contaId || !pronto || conflito !== null || (incerta && !naoChegou) || (publicar && !opcoes) || semLegenda || legendaLonga} aria-busy={busy === "agendar"} onClick={() => void agendar()}>
                {busy === "agendar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CalendarClock aria-hidden="true" />}
                {reagendar ? "Reagendar" : aprovado ? "Agendar" : "Aprovar e agendar"}
              </Button>
              </>
            ))}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

