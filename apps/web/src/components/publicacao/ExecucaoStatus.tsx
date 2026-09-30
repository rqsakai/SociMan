/*
 * Estado da execução de um destino automático (spec 015, US2 e US4; T057, T069; research R7, R11).
 *
 * <ExecucaoStatus conteudo destino onChanged onPostado onReagendar />
 *   - Agendado: quando o SociMan envia e o que acontece no horário;
 *   - Enviando: a fase da tentativa e o progresso das partes (a tela recarrega a cada 5 s);
 *   - Pausado: qual nível do interruptor está desligado;
 *   - Vencido: "Confirmar envio agora" (dono, com confirmação) ou "Reagendar";
 *   - Aguardando vaga: o motivo da TikTok e quando tenta de novo;
 *   - Rascunho criado: "Copiar textos" e "Marcar como postado";
 *   - Publicado: o link do post;
 *   - Falhou: o motivo em pt-BR e a ação; "Tentar de novo" (com "Conferi no app e o rascunho não
 *     chegou" quando a TikTok pode ter recebido), "Reagendar" e "Cancelar agendamento".
 * As ações de envio são só do dono humano; o membro vê o estado.
 */
import type { Conteudo, Destino } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CalendarX, Check, CircleAlert, CirclePause, Clock, ExternalLink, History, Inbox, Link2, Loader2, RotateCcw, Send, TriangleAlert } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { invalidarConteudos, useEhDono } from "@/lib/conteudos";
import { platformLabel } from "@/lib/perfis";
import {
  acaoTexto,
  ehAutomatico,
  enviosDesligadosTexto,
  execucaoAtiva,
  faseLabel,
  invalidarPublicacao,
  progressoPartes,
  usePublicacaoConfig,
} from "@/lib/publicacao";
import { formatDateTime } from "@/lib/tz";
import { ConfirmoNaoChegou } from "./ConfirmoNaoChegou";
import { CopiarTextos } from "./CopiarTextos";
import { EnviarAgora } from "./EnviarAgora";
import { HistoricoEnvio } from "./HistoricoEnvio";
import { OpcoesResumo } from "./OpcoesResumo";

const EXECUCAO = ["enviando", "rascunho_criado", "publicado", "falhou"];

export function ExecucaoStatus({
  conteudo,
  destino,
  onChanged,
  onPostado,
  onReagendar,
}: {
  conteudo: Conteudo;
  destino: Destino;
  onChanged: () => Promise<void>;
  onPostado: () => void;
  onReagendar: () => void;
}) {
  const queryClient = useQueryClient();
  const dono = useEhDono();
  const config = usePublicacaoConfig();
  const [busy, setBusy] = useState<"tentar" | "confirmar" | "cancelar" | "snapshot" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tentarOpen, setTentarOpen] = useState(false);
  const [naoChegou, setNaoChegou] = useState(false);
  const [showHistorico, setShowHistorico] = useState(false);

  const automatico = ehAutomatico(destino.modo);
  const ativo = execucaoAtiva(destino);

  // Enquanto a trilha envia, recarrega o destino a cada 5 s (a trilha anda a cada 15 s).
  useEffect(() => {
    if (!ativo) return;
    const id = window.setInterval(() => void onChanged(), 5_000);
    return () => window.clearInterval(id);
  }, [ativo, onChanged]);

  if (!automatico && !EXECUCAO.includes(destino.estado)) return null;
  if (destino.archived) return null;

  const rede = platformLabel[destino.conta.platform];
  const t = destino.ultimaTentativa ?? null;
  const pct = progressoPartes(t);
  const incerta = Boolean(destino.falhaIncerta);
  const avisos = destino.avisosRede ?? [];
  const cfg = config.data?.config;
  const ef = destino.estadoEfetivo;

  async function run(kind: NonNullable<typeof busy>, fn: () => Promise<unknown>, msg: string) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      toast.success(msg);
      await Promise.all([invalidarConteudos(queryClient, conteudo.id), invalidarPublicacao(queryClient, destino.id)]);
      await onChanged();
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function tentarDeNovo() {
    const ok = await run(
      "tentar",
      () => api.destinos.tentarDeNovo(destino.id, { version: destino.version, ...(incerta ? { confirmoQueNaoChegou: naoChegou } : {}) }),
      "Envio devolvido à fila. O SociMan tenta de novo em instantes.",
    );
    if (ok) {
      setTentarOpen(false);
      setNaoChegou(false);
    }
  }

  const reagendarBtn = dono && (
    <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={onReagendar}>
      <CalendarClock aria-hidden="true" />
      Reagendar
    </Button>
  );

  let corpo: ReactNode = null;

  if (ef === "pausado") {
    corpo = (
      <Alert>
        <CirclePause aria-hidden="true" />
        <AlertTitle>{destino.estado === "enviando" ? "Envio pausado no meio" : "Pausado: nada foi enviado"}</AlertTitle>
        <AlertDescription>
          <p>{cfg ? enviosDesligadosTexto(cfg) : "Os envios automáticos estão desligados."} Ao ligar, o envio segue sem duplicar.</p>
          {dono && (
            <Button asChild size="sm" variant="outline" className="mt-2">
              <Link to="/app/configuracoes/publicacao">Envios automáticos</Link>
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  } else if (ef === "vencido") {
    corpo = (
      <Alert>
        <Clock aria-hidden="true" />
        <AlertTitle>Vencido: passou do horário há mais de 1 hora</AlertTitle>
        <AlertDescription>
          <p>O SociMan não envia sozinho um agendamento tão atrasado. {dono ? "Confirme o envio agora ou escolha outro horário." : "Um dono confirma o envio ou reagenda."}</p>
          {dono && (
            <div className="mt-2 flex flex-wrap gap-2">
              <ConfirmButton
                label="Confirmar envio agora"
                icon={Send}
                size="sm"
                busy={busy === "confirmar"}
                disabled={busy !== null}
                title="Enviar agora?"
                description={`O vídeo sai para ${rede} @${destino.conta.handle} na próxima volta do agendador (em até 15 s), no modo ${destino.modo === "criar_rascunho" ? "criar rascunho" : destino.modo}.`}
                onConfirm={() => void run("confirmar", () => api.destinos.confirmarEnvio(destino.id, destino.version), "Envio confirmado. Sai na próxima volta.")}
              />
              {reagendarBtn}
            </div>
          )}
        </AlertDescription>
      </Alert>
    );
  } else if (ef === "aguardando_vaga") {
    corpo = (
      <Alert>
        <Clock aria-hidden="true" />
        <AlertTitle>Aguardando vaga na {rede}</AlertTitle>
        <AlertDescription>
          <p>{t?.motivo ?? `A ${rede} aceita até 5 rascunhos pendentes em 24 h por conta. O SociMan tenta de novo sozinho quando abrir vaga.`}</p>
          {dono && <div className="mt-2 flex flex-wrap gap-2">{reagendarBtn}</div>}
        </AlertDescription>
      </Alert>
    );
  } else if (destino.estado === "enviando") {
    corpo = (
      <Alert>
        <Loader2 className="animate-spin" aria-hidden="true" />
        <AlertTitle>Enviando para {rede}</AlertTitle>
        <AlertDescription className="w-full">
          <p>{t ? faseLabel[t.fase] : "Iniciando"}{t && t.totalPartes > 0 ? `: parte ${t.partesEnviadas} de ${t.totalPartes}` : ""}</p>
          {pct !== null && (
            <div
              role="progressbar"
              aria-label="Partes enviadas"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted"
            >
              <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
          )}
          <p className="mt-1 text-xs text-muted-foreground">Nada pode ser mudado neste destino até o envio terminar.</p>
        </AlertDescription>
      </Alert>
    );
  } else if (destino.estado === "rascunho_criado") {
    corpo = (
      <Alert>
        <Inbox aria-hidden="true" />
        <AlertTitle>Rascunho criado na caixa de entrada da {rede}</AlertTitle>
        <AlertDescription>
          <p>Abra o app da {rede} em @{destino.conta.handle}, cole os textos, escolha a privacidade e o produto do TikTok Shop e publique. Depois, marque como postado.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <CopiarTextos textos={destino} platform={destino.conta.platform} />
            <Button type="button" size="sm" variant="outline" onClick={onPostado}>
              <Check aria-hidden="true" />
              Marcar como postado
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    );
  } else if (destino.estado === "publicado") {
    corpo = (
      <Alert>
        <Check aria-hidden="true" />
        <AlertTitle>Publicado na {rede}</AlertTitle>
        <AlertDescription>
          {destino.redePostUrl ? (
            <a href={destino.redePostUrl} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 underline">
              Ver o post
              <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          ) : (
            <p>A {rede} ainda não informou o link do post (com "Só eu", ele fica visível só para a conta).</p>
          )}
        </AlertDescription>
      </Alert>
    );
  } else if (destino.estado === "falhou") {
    corpo = (
      <Alert variant="destructive" role="alert">
        {incerta ? <TriangleAlert aria-hidden="true" /> : <CircleAlert aria-hidden="true" />}
        <AlertTitle>{incerta ? `Falhou: a ${rede} pode ter recebido` : `Falhou o envio para ${rede}`}</AlertTitle>
        <AlertDescription>
          <p>{destino.falhaMotivo ?? t?.motivo ?? `A ${rede} recusou o envio.`}</p>
          {acaoTexto(t?.acao) && <p className="font-medium">{acaoTexto(t?.acao)}</p>}
          {incerta && <p>Confira a caixa de entrada no app antes de tentar de novo, para não criar dois rascunhos.</p>}
          {dono ? (
            <div className="mt-2 flex flex-wrap gap-2">
              <Button type="button" size="sm" disabled={busy !== null} onClick={() => setTentarOpen(true)}>
                <RotateCcw aria-hidden="true" />
                Tentar de novo
              </Button>
              <EnviarAgora
                contaId={destino.conta.id}
                handle={destino.conta.handle}
                conteudoId={conteudo.id}
                falhaIncerta={incerta}
                disabled={busy !== null}
                destino={async () => destino}
                onDone={onChanged}
              />
              {reagendarBtn}
              <ConfirmButton
                label="Cancelar agendamento"
                icon={CalendarX}
                size="sm"
                variant="ghost"
                busy={busy === "cancelar"}
                disabled={busy !== null}
                title="Cancelar o agendamento?"
                description="O conteúdo continua aprovado para esta conta, sem data."
                onConfirm={() => void run("cancelar", () => api.agendamentos.cancelar(destino.id, destino.version), "Agendamento cancelado.")}
              />
            </div>
          ) : (
            <p className="text-xs">Só um dono tenta de novo ou reagenda.</p>
          )}
        </AlertDescription>
      </Alert>
    );
  } else if (ef === "atencao") {
    corpo = (
      <Alert>
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>{destino.motivoAtencao ?? "Este envio automático precisa de atenção"}</AlertTitle>
        <AlertDescription>
          <p>Nada é enviado enquanto a conta não estiver conectada à {rede}.</p>
          <Button asChild size="sm" variant="outline" className="mt-2">
            <Link to={`/app/perfis/${conteudo.perfil.id}?aba=contas`}>
              <Link2 aria-hidden="true" />
              Ver a conexão da conta
            </Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  } else if (destino.estado === "agendado" && destino.plannedAt) {
    corpo = (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Send className="size-4" aria-hidden="true" />
        {destino.modo === "criar_rascunho"
          ? `Em ${formatDateTime(destino.plannedAt)}, o SociMan envia o vídeo para a caixa de entrada da ${rede} (@${destino.conta.handle}).`
          : `Em ${formatDateTime(destino.plannedAt)}, o SociMan envia para a ${rede} (@${destino.conta.handle}).`}
      </p>
    );
  }

  const temHistorico = automatico || EXECUCAO.includes(destino.estado);

  return (
    <div className="space-y-2" aria-label="Envio automático" role="group">
      {corpo}
      {/* US3: textos mudaram depois da confirmação; o que sai é o que o dono confirmou */}
      {destino.modo === "publicar" && destino.estado === "agendado" && destino.snapshotDesatualizado && (
        <Alert>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Os textos mudaram depois da confirmação</AlertTitle>
          <AlertDescription>
            <p>No horário, a {rede} recebe a legenda que foi confirmada ao agendar. {dono ? "Salve de novo para confirmar os textos atuais." : "Só um dono confirma os textos novos."}</p>
            {dono && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="mt-2"
                disabled={busy !== null}
                aria-busy={busy === "snapshot"}
                onClick={() =>
                  void run(
                    "snapshot",
                    () => api.destinos.update(destino.id, { version: destino.version, titulo: destino.titulo, descricao: destino.descricao, hashtags: destino.hashtags }),
                    "Textos confirmados para a publicação.",
                  )
                }
              >
                {busy === "snapshot" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
                Salvar de novo
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}
      {destino.modo === "publicar" && destino.opcoesRede && ["agendado", "enviando", "publicado", "falhou"].includes(destino.estado) && (
        <OpcoesResumo opcoes={destino.opcoesRede} />
      )}
      {avisos.length > 0 && destino.estado === "agendado" && (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-warning-foreground" aria-label={`Avisos da ${rede}`}>
          {avisos.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      {error !== null && <ApiErrorAlert error={error} onReload={() => void onChanged()} />}
      {temHistorico && (
        <Button type="button" variant="ghost" size="sm" aria-expanded={showHistorico} onClick={() => setShowHistorico((s) => !s)}>
          <History aria-hidden="true" />
          {showHistorico ? "Esconder histórico do envio" : "Histórico do envio"}
        </Button>
      )}
      {showHistorico && <HistoricoEnvio destino={destino} />}

      <Dialog open={tentarOpen} onOpenChange={(o) => busy === null && setTentarOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Tentar de novo?</DialogTitle>
            <DialogDescription>
              O envio volta à fila e sai para {rede} @{destino.conta.handle} na próxima volta do agendador.
            </DialogDescription>
          </DialogHeader>
          {incerta && <ConfirmoNaoChegou checked={naoChegou} onChange={setNaoChegou} />}
          {error !== null && <ApiErrorAlert error={error} />}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setTentarOpen(false)}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={busy !== null || (incerta && !naoChegou)}
              aria-busy={busy === "tentar"}
              onClick={() => void tentarDeNovo()}
            >
              {busy === "tentar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
              Tentar de novo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
