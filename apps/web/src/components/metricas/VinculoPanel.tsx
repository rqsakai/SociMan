/*
 * Vínculo do destino com o post na TikTok (spec 016, US3; R9 a R12).
 *
 * <VinculoPanel destino vinculo onChanged />
 *   - estado: "Ligado ao post" (com o link e como foi ligado: pelo envio, pela lista de vídeos, pelo
 *     link ou escolhido), "Procurando o post", "Escolha o post", "Sem post ligado", "Post
 *     indisponível";
 *   - candidatos com a diferença de duração, a legenda e a distância da âncora (entrega do rascunho
 *     ou o clique em "Postado"); "Este é o post" liga em 1 clique. Num lembrete ainda não postado,
 *     a escolha também marca o destino como postado;
 *   - "Ligar a um post" (colar o link completo) e "Desfazer vínculo" (AlertDialog).
 * Ligar, escolher, colar e desfazer são só do dono humano; o membro vê o estado.
 */
import type { Destino } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Link2, Loader2, Unlink } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { invalidarConteudos, useEhDono } from "@/lib/conteudos";
import {
  formatCompacto,
  formatDistancia,
  formatDuracaoS,
  invalidarMetricas,
  legendaCompatLabel,
  vinculoEstadoLabel,
  vinculoEstadoTone,
  vinculoMetodoLabel,
  type Candidato,
  type Vinculo,
} from "@/lib/metricas";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";

const ancoraTexto = (v: Vinculo) => (v.ancora === "entrega" ? "da entrega do rascunho" : v.ancora === "postado" ? "do clique em \"Postado\"" : "do horário planejado");

export function VinculoPanel({ destino, vinculo, onChanged }: { destino: Destino; vinculo: Vinculo; onChanged: () => Promise<void> }) {
  const queryClient = useQueryClient();
  const dono = useEhDono();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [colarAberto, setColarAberto] = useState(false);
  const [link, setLink] = useState("");
  const [linkErro, setLinkErro] = useState<string | undefined>();

  // Lembrete antes do clique: escolher o post também marca o destino como postado (R12).
  const marcaPostado = destino.modo === "lembrete" && (destino.estado === "aprovado" || destino.estado === "agendado");
  const ligado = vinculo.estado === "vinculado" || vinculo.estado === "indisponivel";

  async function run(kind: string, fn: () => Promise<unknown>, msg: string) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      toast.success(msg);
      await Promise.all([invalidarMetricas(queryClient, { destinoId: destino.id, contaId: destino.conta.id }), invalidarConteudos(queryClient)]);
      await onChanged();
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(null);
    }
  }

  const escolher = (c: Candidato) =>
    run(`escolher:${c.video.id}`, () => api.destinos.vincular(destino.id, { version: destino.version, videoId: c.video.id }), marcaPostado ? "Post ligado; o destino foi marcado como postado." : "Post ligado.");

  async function colar(e: FormEvent) {
    e.preventDefault();
    const url = link.trim();
    if (!/^https?:\/\/\S+$/i.test(url)) return setLinkErro("Cole o link completo do post (tiktok.com/@conta/video/…)");
    setLinkErro(undefined);
    if (await run("colar", () => api.destinos.vincular(destino.id, { version: destino.version, link: url }), "Post ligado pelo link.")) {
      setLink("");
      setColarAberto(false);
    }
  }

  return (
    <section aria-label="Post na TikTok" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={vinculoEstadoTone[vinculo.estado]}>{vinculoEstadoLabel[vinculo.estado]}</Badge>
        {ligado && vinculo.metodo && (
          <span className="text-sm text-muted-foreground">
            {vinculoMetodoLabel[vinculo.metodo]}
            {vinculo.vinculadoPor ? ` por ${vinculo.vinculadoPor.name}` : " (automático)"}
            {vinculo.vinculadoEm ? ` em ${formatDateTime(vinculo.vinculadoEm)}` : ""}
          </span>
        )}
        {ligado && vinculo.video?.url && (
          <a href={vinculo.video.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-sm underline">
            <ExternalLink className="size-3.5" aria-hidden="true" />
            ver post na TikTok
          </a>
        )}
      </div>

      {vinculo.estado === "indisponivel" && vinculo.video?.indisponivelDesde && (
        <p className="text-sm text-muted-foreground">
          O post deixou de ser público (ou foi apagado) em {formatDateTime(vinculo.video.indisponivelDesde)}. As fotos anteriores continuam guardadas.
        </p>
      )}
      {vinculo.estado === "buscando" && vinculo.busca && (
        <p className="text-sm text-muted-foreground">
          O SociMan consulta a TikTok desde a entrega do rascunho ({formatDateTime(vinculo.busca.entregueEm)}) até {formatDateTime(vinculo.busca.ate)}
          {vinculo.busca.consultas > 0 ? `; ${vinculo.busca.consultas} ${vinculo.busca.consultas === 1 ? "consulta feita" : "consultas feitas"}` : ""}. Publique o rascunho no app e o
          post aparece aqui sozinho.
        </p>
      )}
      {vinculo.estado === "sem_vinculo" && !vinculo.podeVincular && vinculo.motivo && <p className="text-sm text-muted-foreground">{vinculo.motivo}</p>}
      {vinculo.bloqueado && !ligado && (
        <p className="text-xs text-muted-foreground">Um vínculo deste destino já foi desfeito: o SociMan não liga mais sozinho. Escolha o post ou cole o link.</p>
      )}

      {!ligado && vinculo.candidatos.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            {marcaPostado ? "Posts recentes da conta que podem ser este" : vinculo.estado === "a_confirmar" ? "Mais de um post combina. Qual é este?" : "Posts que podem ser este"}
          </p>
          <ul className="space-y-2" aria-label="Posts candidatos">
            {vinculo.candidatos.map((c) => (
              <li key={c.video.id} className="flex flex-wrap items-start gap-3 rounded-lg border p-2.5">
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="line-clamp-2 text-sm">{c.video.legenda || <span className="text-muted-foreground">Sem legenda</span>}</p>
                  <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
                    <span>publicado em {formatDateTime(c.video.publicadoEm)}</span>
                    {c.minutosDaAncora !== null && <span>{`${formatDistancia(c.minutosDaAncora)} ${ancoraTexto(vinculo)}`}</span>}
                    <span>
                      {formatDuracaoS(c.video.duracaoS)}
                      {c.duracaoDiferencaS === 0 ? " (mesma duração)" : ` (${c.duracaoDiferencaS > 0 ? "+" : ""}${c.duracaoDiferencaS.toLocaleString("pt-BR")} s)`}
                    </span>
                    <span className={cn(c.legenda === "incompativel" && "text-destructive")}>{legendaCompatLabel[c.legenda]}</span>
                    {c.video.ultima?.views !== null && c.video.ultima?.views !== undefined && <span>{formatCompacto(c.video.ultima.views)} views</span>}
                  </p>
                  {c.video.url && (
                    <a href={c.video.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs underline">
                      <ExternalLink className="size-3" aria-hidden="true" />
                      abrir na TikTok
                    </a>
                  )}
                </div>
                {dono && vinculo.podeVincular && (
                  <Button type="button" size="sm" disabled={busy !== null} aria-busy={busy === `escolher:${c.video.id}`} onClick={() => void escolher(c)}>
                    {busy === `escolher:${c.video.id}` ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
                    Este é o post
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {marcaPostado && dono && <p className="text-xs text-muted-foreground">Escolher o post também marca este destino como postado.</p>}
        </div>
      )}

      {!ligado && vinculo.candidatos.length === 0 && vinculo.estado === "sem_vinculo" && vinculo.podeVincular && (
        <p className="text-sm text-muted-foreground">
          {marcaPostado
            ? "Nenhum post recente da conta combina com este vídeo. Depois de postar, use \"Postado\" ou cole o link."
            : "Nenhum post da conta combina ainda. Se já postou, cole o link."}
        </p>
      )}

      {error !== null && <ApiErrorAlert error={error} onReload={() => void onChanged()} />}

      {dono && (
        <div className="flex flex-wrap gap-2">
          {!ligado && vinculo.podeVincular && !colarAberto && (
            <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => setColarAberto(true)}>
              <Link2 aria-hidden="true" />
              Ligar a um post
            </Button>
          )}
          {ligado && (
            <ConfirmButton
              label="Desfazer vínculo"
              icon={Unlink}
              size="sm"
              variant="ghost"
              busy={busy === "desfazer"}
              disabled={busy !== null}
              title="Desfazer o vínculo com este post?"
              description={
                destino.estado === "publicado"
                  ? "O post deixa de estar ligado a este destino e o SociMan não o liga mais sozinho. Se foi o vínculo que marcou \"publicado\", o destino volta a \"rascunho criado\". As fotos do post continuam guardadas."
                  : "O post deixa de estar ligado a este destino e o SociMan não o liga mais sozinho. O estado do destino não muda, e as fotos do post continuam guardadas."
              }
              onConfirm={() => void run("desfazer", () => api.destinos.desfazerVinculo(destino.id, destino.version), "Vínculo desfeito.")}
            />
          )}
        </div>
      )}

      {dono && colarAberto && !ligado && (
        <form onSubmit={(e) => void colar(e)} className="space-y-2 rounded-lg border bg-muted/30 p-3" aria-label="Ligar pelo link do post">
          <Field label="Link do post" error={linkErro} hint={`Copie o endereço completo no app ou no navegador (tiktok.com/@${destino.conta.handle.replace(/^@/, "")}/video/…).`}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} type="url" value={link} autoFocus aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setLink(e.target.value)} />
            )}
          </Field>
          {marcaPostado && <p className="text-xs text-muted-foreground">Ligar pelo link também marca este destino como postado.</p>}
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy !== null || !link.trim()} aria-busy={busy === "colar"}>
              {busy === "colar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Link2 aria-hidden="true" />}
              Ligar
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setColarAberto(false)}>
              Cancelar
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
