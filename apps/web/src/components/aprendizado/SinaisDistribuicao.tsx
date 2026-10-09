/*
 * Sinais de distribuição e checklist do app (spec 023, US5; FR-048 a FR-050; R10). Os sinais são
 * calculados na leitura, cada um com o número que o sustenta, e somem sozinhos quando a condição
 * deixa de valer. Só as conferências do dono (o que ele viu no app da rede) ficam gravadas, com
 * histórico. Nada aqui cria tarefa, muda destino ou republica.
 */
import { CheckCircle2, CircleHelp, Loader2, Save, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  aprendizadoPath,
  resultadoConferenciaLabel,
  rotuloSinal,
  useInvalidarAprendizado,
  usePostDiagnostico,
  type AprendizadoConferencia,
  type AprendizadoItemChecklist,
  type AprendizadoSinal,
  type ResultadoConferencia,
} from "@/lib/aprendizado";
import { useEhDono } from "@/lib/conteudos";
import { formatNumero } from "@/lib/metricas";

const linkVideo = (id: string) => `/app/metricas/videos/${id}`;

export function SinaisDistribuicao({ sinais, comLinkPost = false }: { sinais: AprendizadoSinal[]; comLinkPost?: boolean }) {
  if (sinais.length === 0) return <p className="text-sm text-muted-foreground">Nenhum sinal de trava encontrado.</p>;
  return (
    <ul className="flex flex-col gap-2" aria-label="Sinais de distribuição">
      {sinais.map((s, i) => (
        <li key={`${s.tipo}:${s.alvoId}:${i}`} className="flex items-start gap-2 text-sm" data-sinal={s.tipo}>
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
          <span className="min-w-0">
            <span className="font-medium">{rotuloSinal(s)}</span>
            {s.numero !== null && <span className="tabular-nums text-muted-foreground"> ({formatNumero(s.numero)})</span>}: {s.texto}
            {comLinkPost && s.alvo === "post" && (
              <>
                {" "}
                <Link to={linkVideo(s.alvoId)} className="underline">
                  abrir o post
                </Link>
              </>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function ChecklistApp({ checklist }: { checklist: AprendizadoItemChecklist[] }) {
  return (
    <ol className="flex flex-col gap-2" aria-label="O que conferir no app">
      {checklist.map((c) => (
        <li key={c.item} className="text-sm" data-item={c.item}>
          <span className="font-medium">{c.titulo}</span>
          <span className="text-muted-foreground">: {c.texto}</span>
        </li>
      ))}
    </ol>
  );
}

const iconeResultado: Record<ResultadoConferencia, typeof CheckCircle2> = { ok: CheckCircle2, problema: TriangleAlert, nao_sei: CircleHelp };

function Conferencia({ videoId, item, atual, dono, onSalvo }: { videoId: string; item: AprendizadoItemChecklist; atual?: AprendizadoConferencia; dono: boolean; onSalvo: () => Promise<unknown> }) {
  const [resultado, setResultado] = useState<ResultadoConferencia | "">((atual?.resultado as ResultadoConferencia | undefined) ?? "");
  const [nota, setNota] = useState(atual?.nota ?? "");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const Icone = atual ? iconeResultado[atual.resultado as ResultadoConferencia] : null;
  const mudou = resultado !== (atual?.resultado ?? "") || nota !== (atual?.nota ?? "");

  async function salvar() {
    if (!resultado) return;
    setBusy(true);
    setErro(null);
    try {
      await api.aprendizado.conferencia(videoId, item.item, { version: atual?.version ?? 0, resultado, ...(nota.trim() ? { nota: nota.trim() } : {}) });
      toast.success(`Conferência registrada: ${item.titulo}.`);
      await onSalvo();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-col gap-2 py-3" aria-label={`Conferir: ${item.titulo}`} data-item={item.item} data-resultado={atual?.resultado ?? ""}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm">
          <span className="font-medium">{item.titulo}</span>
          <span className="block text-xs text-muted-foreground">{item.texto}</span>
        </p>
        {atual && Icone && (
          <Badge variant={atual.resultado === "problema" ? "destructive" : "secondary"}>
            <Icone aria-hidden="true" />
            {resultadoConferenciaLabel[atual.resultado as ResultadoConferencia]}
          </Badge>
        )}
      </div>
      {atual?.nota && !dono && <p className="text-xs text-muted-foreground">Nota: {atual.nota}</p>}
      {dono && (
        <div className="grid gap-2 sm:grid-cols-[14rem_1fr_auto] sm:items-end">
          <Field label="Resultado">
            {({ id }) => (
              <NativeSelect id={id} value={resultado} onChange={(e) => setResultado(e.target.value as ResultadoConferencia | "")}>
                <option value="">Não conferido</option>
                {(Object.keys(resultadoConferenciaLabel) as ResultadoConferencia[]).map((r) => (
                  <option key={r} value={r}>
                    {resultadoConferenciaLabel[r]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Nota (opcional)">
            {({ id }) => <Input id={id} maxLength={300} value={nota} onChange={(e) => setNota(e.target.value)} />}
          </Field>
          <Button type="button" size="sm" disabled={!resultado || !mudou || busy} aria-busy={busy} onClick={() => void salvar()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Registrar
          </Button>
        </div>
      )}
      {erro !== null && <ApiErrorAlert error={erro} onReload={() => void onSalvo()} />}
    </li>
  );
}

// Bloco do detalhe do vídeo (016): os sinais daquele post e as conferências do checklist. Só aparece
// para o post estagnado ou com sinal; a checklist vem da API (lista fixa em código).
export function DiagnosticoDoPost({ videoId, perfilId }: { videoId: string; perfilId?: string | null }) {
  const dono = useEhDono();
  const diag = usePostDiagnostico(videoId);
  const invalidar = useInvalidarAprendizado();

  if (diag.isError) return <ApiErrorAlert error={diag.error} />;
  if (diag.isPending) return <Skeleton className="h-32 w-full" />;
  const d = diag.data;
  if (!d.estagnado && d.sinais.length === 0 && d.conferencias.length === 0) return null;

  return (
    <section aria-label="Diagnóstico de distribuição" className="flex flex-col gap-4 rounded-xl bg-card p-4 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Diagnóstico de distribuição</h2>
        {d.estagnado && <Badge variant="outline">estagnado</Badge>}
      </div>
      <p className="text-sm text-muted-foreground">
        Um post que a rede não entregou não diz nada sobre o assunto. Confira os sinais e o app; as marcações ficam no histórico e não mudam nada no post.
      </p>
      <SinaisDistribuicao sinais={d.sinais} />
      <ul className="divide-y" aria-label="Checklist do app">
        {d.checklist.map((item) => (
          <Conferencia
            key={`${item.item}:${d.conferencias.find((c) => c.item === item.item)?.version ?? 0}`}
            videoId={videoId}
            item={item}
            atual={d.conferencias.find((c) => c.item === item.item)}
            dono={dono}
            onSalvo={async () => {
              await diag.refetch();
              if (perfilId) await invalidar(perfilId);
            }}
          />
        ))}
      </ul>
      {perfilId && (
        <Link to={aprendizadoPath(perfilId, "diagnostico")} className="text-sm underline">
          Ver o diagnóstico das contas
        </Link>
      )}
    </section>
  );
}
