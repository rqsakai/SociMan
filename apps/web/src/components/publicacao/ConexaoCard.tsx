/*
 * Conexão de uma conta TikTok com o app da agência (spec 015, US1; T037).
 *
 * <ConexaoCard conta perfilId />
 *   Estado (conectada / precisa reconectar / não conectada), @, apelido e foto (via /img), data e
 *   quem conectou, e os modos que a conta oferece (com o `aviso` ou o motivo). Conectar, Reconectar
 *   e Desconectar aparecem só para o dono: o membro vê só o estado. Conectar leva ao login oficial
 *   da TikTok (a volta é a página /app/conexoes/retorno).
 */
import type { Conta } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Link2, Link2Off, Loader2, RefreshCw, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { PlatformIcon } from "@/components/PlatformIcon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { invalidarConteudos, useEhDono } from "@/lib/conteudos";
import { modoDescricao, modoLabel, modosKey, MODOS } from "@/lib/postagem";
import { abrirEm, conexaoEstadoLabel, conexaoEstadoTone, conexaoKey, conexaoVersionsKey, iniciarConexao, useConexao } from "@/lib/publicacao";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";

export function ConexaoCard({ conta, perfilId }: { conta: Conta; perfilId: string }) {
  const queryClient = useQueryClient();
  const dono = useEhDono();
  const conexao = useConexao(conta.id);
  const [busy, setBusy] = useState<"conectar" | "desconectar" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const c = conexao.data?.conexao;
  const bloqueada = conta.archived || conta.status === "encerrada";

  async function conectar() {
    setError(null);
    setBusy("conectar");
    try {
      await iniciarConexao(conta.id, perfilId);
      // o navegador sai para a TikTok; o botão fica ocupado até lá
    } catch (err) {
      setError(err);
      setBusy(null);
    }
  }

  async function desconectar() {
    if (!c) return;
    setError(null);
    setBusy("desconectar");
    try {
      const r = await api.conexoes.desconectar(conta.id, c.version ?? 0);
      toast.success(
        r.agendamentosEmAtencao > 0
          ? `@${conta.handle} desconectada. ${r.agendamentosEmAtencao} agendamento(s) automático(s) ficaram em atenção.`
          : `@${conta.handle} desconectada.`,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: conexaoKey(conta.id) }),
        queryClient.invalidateQueries({ queryKey: conexaoVersionsKey(conta.id) }),
        queryClient.invalidateQueries({ queryKey: modosKey(conta.id) }),
        invalidarConteudos(queryClient),
      ]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  const outroEndereco = abrirEm(error);

  return (
    <section aria-label={`Conexão de @${conta.handle}`} className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-3">
        {c?.avatarUrl ? (
          <img src={c.avatarUrl} alt="" className="size-10 shrink-0 rounded-full bg-muted object-cover" />
        ) : (
          <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-muted">
            <PlatformIcon platform={conta.platform} className="size-5" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            {c?.displayName ?? `@${conta.handle}`}
            {c?.username && <span className="ml-1 text-sm font-normal text-muted-foreground">@{c.username}</span>}
          </p>
          {c?.estado === "conectada" && c.conectadoEm && (
            <p className="text-xs text-muted-foreground">
              Conectada em {formatDateTime(c.conectadoEm)}
              {c.conectadoPor ? ` por ${c.conectadoPor.name}` : ""}
            </p>
          )}
        </div>
        {conexao.isPending ? (
          <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Carregando a conexão" />
        ) : (
          c && <Badge className={conexaoEstadoTone[c.estado]}>{conexaoEstadoLabel[c.estado]}</Badge>
        )}
      </div>

      {conexao.isError && <ApiErrorAlert error={conexao.error} />}

      {c?.estado === "precisa_reconectar" && (
        <Alert variant="destructive">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>A autorização da TikTok não vale mais</AlertTitle>
          <AlertDescription>
            {c.motivo ?? "A TikTok revogou ou deixou expirar a autorização."} Os agendamentos automáticos desta conta ficam em atenção e nada é enviado até
            reconectar.
          </AlertDescription>
        </Alert>
      )}

      {c && c.estado !== "nao_conectada" && c.modos.length > 0 && (
        <ul aria-label={`Modos de @${conta.handle}`} className="space-y-1 text-xs">
          {MODOS.map((m) => {
            const i = c.modos.find((x) => x.modo === m);
            if (!i) return null;
            return (
              <li key={m} className={cn("flex flex-wrap gap-1", !i.disponivel && "text-muted-foreground")}>
                <span className="font-medium">{modoLabel[m]}:</span>
                <span>{i.disponivel ? modoDescricao[m] : (i.motivo ?? "Indisponível.")}</span>
                {i.disponivel && i.aviso && <span className="text-warning-foreground">({i.aviso})</span>}
              </li>
            );
          })}
        </ul>
      )}

      {c?.estado === "nao_conectada" && (
        <p className="text-sm text-muted-foreground">
          {dono
            ? "Conecte a conta para o SociMan criar o rascunho na TikTok no horário agendado."
            : "Só um dono conecta a conta à TikTok."}
        </p>
      )}

      {outroEndereco ? (
        <Alert>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Abra o SociMan em outro endereço</AlertTitle>
          <AlertDescription>
            <p>
              O login da TikTok só volta para{" "}
              <a href={outroEndereco} className="font-medium underline">
                {outroEndereco}
              </a>
              . Abra o SociMan por lá e conecte de novo.
            </p>
          </AlertDescription>
        </Alert>
      ) : (
        error !== null && <ApiErrorAlert error={error} onReload={() => void conexao.refetch()} />
      )}

      {dono && c && !bloqueada && (
        <div className="flex flex-wrap gap-2">
          {c.estado === "nao_conectada" && (
            <Button type="button" size="sm" disabled={busy !== null} aria-busy={busy === "conectar"} onClick={() => void conectar()}>
              {busy === "conectar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Link2 aria-hidden="true" />}
              Conectar
            </Button>
          )}
          {c.estado === "precisa_reconectar" && (
            <Button type="button" size="sm" disabled={busy !== null} aria-busy={busy === "conectar"} onClick={() => void conectar()}>
              {busy === "conectar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
              Reconectar
            </Button>
          )}
          {c.estado !== "nao_conectada" && (
            <ConfirmButton
              label="Desconectar"
              icon={Link2Off}
              size="sm"
              variant="ghost"
              busy={busy === "desconectar"}
              disabled={busy !== null}
              title={`Desconectar @${conta.handle} da TikTok?`}
              description="A autorização é apagada do SociMan. Os agendamentos automáticos desta conta (criar rascunho, publicar) ficam em atenção até você conectar de novo; os lembretes continuam."
              onConfirm={() => desconectar()}
            />
          )}
        </div>
      )}
    </section>
  );
}
