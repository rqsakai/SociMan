/*
 * "Enviar rascunho agora" (spec 015, emenda do dono; T100): envia o rascunho para a conta na próxima volta do
 * agendador, sem escolher horário. Só para o dono humano e só quando a conta oferece um modo
 * automático (hoje "Criar rascunho"). Confirma num AlertDialog; se a última falha foi incerta, exige
 * "Conferi no app e o rascunho não chegou"; avisa quando a publicação automática está desligada.
 *
 * <EnviarAgora contaId handle falhaIncerta? modo? opcoes? destino={() => Promise<{ id, version }>} onDone />
 *   `destino` devolve o destino a enviar (o AgendarDialog cria um quando a conta ainda não tem).
 *   `modo="publicar"` vira "Publicar agora": exige as `opcoes` da tela obrigatória da TikTok (as
 *   escolhidas no TikTokPostForm ou as salvas no destino agendado).
 */
import type { OpcoesTikTok } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { CirclePause, Loader2, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { invalidarConteudos, useEhDono } from "@/lib/conteudos";
import { useModos } from "@/lib/postagem";
import { enviosDesligadosTexto, enviosLigados, invalidarPublicacao, problemasDaApi, usePublicacaoConfig } from "@/lib/publicacao";
import { ConfirmoNaoChegou } from "./ConfirmoNaoChegou";

export function EnviarAgora({
  contaId,
  handle,
  conteudoId,
  falhaIncerta = false,
  modo = "criar_rascunho",
  opcoes = null,
  disabled,
  destino,
  onDone,
  size = "sm",
  variant = "outline",
}: {
  contaId: string;
  handle: string;
  conteudoId: string;
  falhaIncerta?: boolean;
  modo?: "criar_rascunho" | "publicar";
  opcoes?: OpcoesTikTok | null;
  disabled?: boolean;
  destino: () => Promise<{ id: string; version: number }>;
  onDone?: () => Promise<void> | void;
  size?: "sm" | "default";
  variant?: "outline" | "default";
}) {
  const queryClient = useQueryClient();
  const dono = useEhDono();
  const modos = useModos(contaId);
  const config = usePublicacaoConfig();
  const [open, setOpen] = useState(false);
  const [naoChegou, setNaoChegou] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const info = modos.data?.modos.find((m) => m.modo === modo);
  if (!dono || !info?.disponivel) return null;
  const cfg = config.data?.config;
  const arroba = `@${handle.replace(/^@/, "")}`;
  const publicar = modo === "publicar";
  const rotulo = publicar ? "Publicar agora" : "Enviar rascunho agora";
  const sandbox = cfg?.situacaoApp === "sandbox";

  async function enviar() {
    setError(null);
    setBusy(true);
    try {
      const d = await destino();
      const r = await api.destinos.enviarAgora(d.id, {
        version: d.version,
        modo,
        ...(publicar && opcoes ? { opcoes } : {}),
        ...(falhaIncerta ? { conferiNoApp: naoChegou } : {}),
      });
      for (const a of r.destino.avisosRede ?? []) toast.warning(a, { duration: 10_000 });
      // `aviso`: ex.: envios desligados, o destino fica pausado até ligar
      if (r.aviso) toast.warning(r.aviso, { duration: 10_000 });
      else toast.success(publicar ? `Publicando em ${arroba}.` : `Enviando o rascunho para ${arroba}.`);
      setOpen(false);
      setNaoChegou(false);
      await Promise.all([invalidarConteudos(queryClient, conteudoId), invalidarPublicacao(queryClient, d.id)]);
      await onDone?.();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        type="button"
        size={size}
        variant={variant}
        disabled={disabled || busy || (publicar && !opcoes)}
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        <Send aria-hidden="true" />
        {rotulo}
      </Button>
      <AlertDialog open={open} onOpenChange={(o) => !busy && setOpen(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{publicar ? `Publicar em ${arroba} agora?` : `Enviar o rascunho para ${arroba} agora?`}</AlertDialogTitle>
            <AlertDialogDescription>
              {publicar
                ? `O SociMan publica na próxima volta do agendador (em até 15 s), com as opções confirmadas; a TikTok leva alguns minutos para processar.${sandbox ? " Sandbox: sai só para você, com a conta privada." : ""}`
                : "O vídeo vai para a caixa de entrada da conta na próxima volta do agendador (em até 15 s). Você finaliza e publica no app."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {cfg && !enviosLigados(cfg) && (
            <Alert>
              <CirclePause aria-hidden="true" />
              <AlertTitle>Publicação automática desligada</AlertTitle>
              <AlertDescription>{enviosDesligadosTexto(cfg)} O envio fica "Pausado" até ligar.</AlertDescription>
            </Alert>
          )}
          {falhaIncerta && <ConfirmoNaoChegou checked={naoChegou} onChange={setNaoChegou} />}
          {error !== null && <ApiErrorAlert error={error} />}
          {problemasDaApi(error).length > 0 && (
            <ul className="list-disc pl-5 text-sm text-destructive" aria-label="Regras da TikTok">
              {problemasDaApi(error).map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancelar</AlertDialogCancel>
            <Button type="button" disabled={busy || (falhaIncerta && !naoChegou)} aria-busy={busy} onClick={() => void enviar()}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
              {rotulo}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
