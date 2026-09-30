/*
 * "Histórico do envio" de um destino automático (spec 015, FR-011; T057): quem aprovou, quem
 * agendou, a confirmação de um vencido e cada tentativa (início, fim, fase, identificador da
 * TikTok, partes, arquivo enviado e motivo), da mais nova para a mais antiga.
 */
import type { Destino } from "@sociman/contract";
import { Loader2 } from "lucide-react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { acaoTexto, disparoLabel, faseLabel, faseTone, formatBytes, useTentativas } from "@/lib/publicacao";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";

export function HistoricoEnvio({ destino }: { destino: Destino }) {
  const tentativas = useTentativas(destino.id);
  return (
    <section aria-label="Histórico do envio" className="space-y-3 rounded-lg border p-3 text-sm">
      <h3 className="font-semibold">Histórico do envio</h3>
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[auto_1fr]">
        <dt className="text-muted-foreground">Aprovação</dt>
        <dd>{destino.aprovacao ? `${destino.aprovacao.por.name} em ${formatDateTime(destino.aprovacao.em)}` : "—"}</dd>
        <dt className="text-muted-foreground">Agendamento</dt>
        <dd>
          {destino.agendadoPor ? destino.agendadoPor.name : "—"}
          {destino.agendadoEm ? ` em ${formatDateTime(destino.agendadoEm)}` : ""}
        </dd>
        {destino.envioConfirmado && (
          <>
            <dt className="text-muted-foreground">Envio confirmado</dt>
            <dd>
              {destino.envioConfirmado.por.name} em {formatDateTime(destino.envioConfirmado.em)}
            </dd>
          </>
        )}
      </dl>

      {tentativas.isPending && <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Carregando as tentativas" />}
      {tentativas.isError && <ApiErrorAlert error={tentativas.error} />}
      {tentativas.data &&
        (tentativas.data.items.length === 0 ? (
          <p className="text-muted-foreground">Nenhuma tentativa de envio ainda.</p>
        ) : (
          <ol aria-label="Tentativas" className="space-y-2">
            {tentativas.data.items.map((t) => (
              <li key={t.id} className="space-y-1 rounded-md bg-muted/40 p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Tentativa {t.numero}</span>
                  <Badge className={cn(faseTone[t.fase])}>{faseLabel[t.fase]}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {disparoLabel[t.disparo] ?? t.disparo}
                    {t.disparadoPor ? ` · ${t.disparadoPor.name}` : ""}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Início {formatDateTime(t.iniciadaEm)}
                  {t.concluidaEm ? ` · fim ${formatDateTime(t.concluidaEm)}` : ""}
                  {t.totalPartes > 0 ? ` · partes ${t.partesEnviadas}/${t.totalPartes}` : ""}
                  {` · arquivo ${formatBytes(t.video.bytes)}`}
                  {t.video.sha256 ? ` (${t.video.sha256.slice(0, 8)})` : ""}
                </p>
                {t.publishId && <p className="text-xs break-all text-muted-foreground">Identificador na TikTok: {t.publishId}</p>}
                {t.redePostId && <p className="text-xs break-all text-muted-foreground">Post: {t.redePostId}</p>}
                {t.motivo && (
                  <p className="text-xs">
                    {t.motivo}
                    {t.acao ? ` ${acaoTexto(t.acao)}` : ""}
                    {t.codigoRede ? <span className="text-muted-foreground"> (código {t.codigoRede})</span> : null}
                  </p>
                )}
              </li>
            ))}
          </ol>
        ))}
    </section>
  );
}
