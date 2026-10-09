/*
 * Seção "Desempenho" do destino (spec 016, US3 e US4), no DestinoPanel das contas TikTok.
 *
 * <DesempenhoDestino destino onChanged />
 *   Curva e marcos do post ligado (acima) e o <VinculoPanel> (estado, candidatos, colar link e
 *   desfazer). Aparece a partir de "aprovado" num lembrete (para escolher o post) e nos estados em
 *   que já pode haver post: postado, rascunho criado, publicado e falhou.
 */
import type { Destino, DestinoEstado } from "@sociman/contract";
import { ChartLine, Loader2 } from "lucide-react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { useDestinoMetricas } from "@/lib/metricas";
import { CurvaVideo } from "./CurvaVideo";
import { VinculoPanel } from "./VinculoPanel";

const COM_POST: DestinoEstado[] = ["postado", "rascunho_criado", "publicado", "falhou"];

export function temDesempenho(destino: Pick<Destino, "estado" | "modo" | "archived" | "conta">): boolean {
  if (destino.archived || destino.conta.platform !== "tiktok") return false;
  if (COM_POST.includes(destino.estado)) return true;
  return destino.modo === "lembrete" && (destino.estado === "aprovado" || destino.estado === "agendado");
}

export function DesempenhoDestino({ destino, onChanged }: { destino: Destino; onChanged: () => Promise<void> }) {
  const visivel = temDesempenho(destino);
  const metricas = useDestinoMetricas(destino.id, visivel);
  if (!visivel) return null;

  const video = metricas.data?.video ?? null;

  return (
    <section aria-labelledby={`desempenho-${destino.id}`} className="space-y-4 rounded-lg border p-3">
      <h3 id={`desempenho-${destino.id}`} className="flex items-center gap-2 font-semibold">
        <ChartLine className="size-4 text-muted-foreground" aria-hidden="true" />
        Desempenho
      </h3>
      {metricas.isPending ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Carregando as métricas…
        </p>
      ) : metricas.isError ? (
        <ApiErrorAlert error={metricas.error} />
      ) : (
        <>
          {video && <CurvaVideo video={video} />}
          <VinculoPanel destino={destino} vinculo={metricas.data.vinculo} onChanged={onChanged} />
        </>
      )}
    </section>
  );
}
