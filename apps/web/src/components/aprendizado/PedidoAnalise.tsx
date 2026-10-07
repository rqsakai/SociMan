/*
 * Pedido de análise da IA dos melhores posts (spec 023, US2; FR-030, FR-031; Clarification 1). Só
 * dono. Primeiro a estimativa (nenhuma chamada de IA): os N melhores e os comparáveis, quantos vídeos
 * não têm arquivo e o custo com e sem quadros. "Confirmar custo" cria o pedido; a trilha do agendador
 * executa e a lista acompanha (polling de 5 s).
 */
import { ApiError } from "@sociman/contract";
import { Calculator, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatUsd, medidaAprendizadoLabel, type AprendizadoEstimativa, type MedidaAprendizado } from "@/lib/aprendizado";
import { formatNumero } from "@/lib/metricas";

export function PedidoAnalise({
  perfilId,
  contaId,
  medida,
  bloqueado,
  onPedido,
}: {
  perfilId: string;
  contaId?: string;
  medida: MedidaAprendizado;
  bloqueado: boolean;
  onPedido: () => Promise<unknown>;
}) {
  const [n, setN] = useState(8);
  const [comQuadros, setComQuadros] = useState(false);
  const [estimativa, setEstimativa] = useState<AprendizadoEstimativa | null>(null);
  const [busy, setBusy] = useState<"estimar" | "pedir" | null>(null);
  const [erro, setErro] = useState<unknown>(null);
  const escopo = { ...(contaId ? { contaId } : {}), n, medida };

  async function estimar() {
    setBusy("estimar");
    setErro(null);
    try {
      setEstimativa(await api.aprendizado.analises.estimativa(perfilId, escopo));
    } catch (err) {
      if (err instanceof ApiError && err.code === "sem_posts") toast.info("Nenhum post entregue neste recorte para analisar.");
      else setErro(err);
    } finally {
      setBusy(null);
    }
  }

  async function pedir() {
    setBusy("pedir");
    setErro(null);
    try {
      await api.aprendizado.analises.create(perfilId, { ...escopo, comQuadros, confirmoCusto: true });
      toast.success("Análise pedida. O agendador executa em seguida; a lista atualiza sozinha.");
      setEstimativa(null);
      await onPedido();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(null);
    }
  }

  const custo = estimativa ? (comQuadros ? estimativa.custoComQuadrosUsd : estimativa.custoSemQuadrosUsd) : null;

  return (
    <section aria-label="Pedir análise da IA" className="flex flex-col gap-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Quantos melhores (1 a 15)" className="w-40">
          {({ id }) => (
            <Input
              id={id}
              type="number"
              min={1}
              max={15}
              value={n}
              onChange={(e) => {
                setN(Math.min(15, Math.max(1, Number(e.target.value) || 1)));
                setEstimativa(null);
              }}
            />
          )}
        </Field>
        <p className="pb-2 text-sm text-muted-foreground">
          {contaId ? "Desta conta" : "Do perfil"} · {medidaAprendizadoLabel[medida]}
        </p>
        <Button type="button" variant="outline" disabled={busy !== null || bloqueado} aria-busy={busy === "estimar"} onClick={() => void estimar()}>
          {busy === "estimar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Calculator aria-hidden="true" />}
          Estimar custo
        </Button>
      </div>
      {bloqueado && <p className="text-sm text-muted-foreground">Já há uma análise na fila ou em curso neste perfil; espere ela terminar.</p>}

      {estimativa && (
        <div className="flex flex-col gap-3" data-estimativa>
          <p className="text-sm">
            {formatNumero(estimativa.melhores.length)} melhores contra {formatNumero(estimativa.comparaveis.length)} comparáveis (piores que saíram do zero, mesma conta e período).
            {estimativa.semArquivo > 0 ? ` ${formatNumero(estimativa.semArquivo)} sem o arquivo do vídeo entram só com texto.` : ""}
          </p>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">Custo estimado</legend>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="quadros" className="size-4 accent-primary" checked={!comQuadros} onChange={() => setComQuadros(false)} />
              Só texto (transcrição, gancho, legenda, hashtags): <strong className="tabular-nums">{formatUsd(estimativa.custoSemQuadrosUsd)}</strong>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="quadros" className="size-4 accent-primary" checked={comQuadros} onChange={() => setComQuadros(true)} />
              Com 4 quadros por vídeo (abertura, 2 s, meio e fim): <strong className="tabular-nums">{formatUsd(estimativa.custoComQuadrosUsd)}</strong>
            </label>
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={busy !== null || bloqueado} aria-busy={busy === "pedir"} onClick={() => void pedir()}>
              {busy === "pedir" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
              Confirmar custo ({formatUsd(custo)})
            </Button>
            <Button type="button" variant="ghost" disabled={busy !== null} onClick={() => setEstimativa(null)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
      {erro !== null && <ApiErrorAlert error={erro} />}
    </section>
  );
}
