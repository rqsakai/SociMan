/*
 * Estado da coleta de métricas de uma conta (spec 016, US1; R1, R3), no ConexaoCard e na aba
 * Contas de /app/metricas.
 *
 * <ColetaStatus coleta onReconectar? busy? />
 *   - "Coletando métricas · última coleta há 12 min" (e a próxima, os vídeos e as fotos);
 *   - "Coleta pausada no servidor" (METRICAS_COLETA_HABILITADA=false: nada é apagado);
 *   - "Faltam permissões de métricas" com "Reconectar para liberar métricas" quando há
 *     `onReconectar` (só o dono recebe; o membro vê o aviso sem o botão);
 *   - o último erro, com a hora da próxima tentativa.
 */
import { TriangleAlert, ChartLine, Loader2, CirclePause, RefreshCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { escopoLabel, formatNumero, type EstadoColeta } from "@/lib/metricas";
import { formatAgo, formatDateTime, formatTime } from "@/lib/tz";

export function ColetaStatus({ coleta, onReconectar, busy }: { coleta: EstadoColeta | null | undefined; onReconectar?: () => void; busy?: boolean }) {
  if (!coleta || coleta.permissao === "sem_conexao") return null;

  if (coleta.permissao === "faltando") {
    const faltam = coleta.escoposFaltando.map((e) => escopoLabel[e] ?? e).join(", ");
    return (
      <Alert role="status">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Faltam permissões de métricas</AlertTitle>
        <AlertDescription>
          <p>
            Esta conexão foi feita sem as permissões de métricas{faltam ? ` (${faltam})` : ""}, então nada é coletado.{" "}
            {onReconectar ? "Reconecte com a mesma conta da TikTok para liberar." : "Só um dono reconecta a conta."}
          </p>
          {onReconectar && (
            <Button type="button" size="sm" className="mt-1" disabled={busy} aria-busy={busy} onClick={onReconectar}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
              Reconectar para liberar métricas
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  const numeros = `${formatNumero(coleta.videos)} ${coleta.videos === 1 ? "vídeo" : "vídeos"} · ${formatNumero(coleta.fotos)} ${coleta.fotos === 1 ? "foto" : "fotos"}`;

  return (
    <div className="space-y-2" role="status" aria-label="Coleta de métricas">
      {!coleta.habilitada ? (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <CirclePause className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            <strong className="font-medium text-foreground">Coleta pausada no servidor.</strong> As métricas guardadas continuam; a coleta volta quando
            METRICAS_COLETA_HABILITADA ficar true no .env.
          </span>
        </p>
      ) : (
        <p className="flex items-start gap-2 text-sm">
          <ChartLine className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
          <span>
            <strong className="font-medium">{coleta.coletando ? "Coletando métricas" : "Métricas liberadas"}</strong>
            {coleta.ultimaColetaEm ? (
              <span title={formatDateTime(coleta.ultimaColetaEm)}> · última coleta {formatAgo(coleta.ultimaColetaEm)}</span>
            ) : (
              <span className="text-muted-foreground"> · a primeira coleta sai em até 1 hora</span>
            )}
            {coleta.proximaColetaEm && <span className="text-muted-foreground"> · próxima às {formatTime(coleta.proximaColetaEm)}</span>}
            <span className="block text-xs text-muted-foreground">
              {numeros}
              {!coleta.varreduraConcluida && " · primeira varredura dos vídeos em andamento"}
            </span>
          </span>
        </p>
      )}
      {coleta.erro && (
        <p className="flex items-start gap-2 text-sm text-destructive" role="alert">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            A última coleta falhou em {formatDateTime(coleta.erro.em)}: {coleta.erro.motivo}
            {coleta.proximaColetaEm ? ` O SociMan tenta de novo às ${formatTime(coleta.proximaColetaEm)}.` : ""}
          </span>
        </p>
      )}
    </div>
  );
}
