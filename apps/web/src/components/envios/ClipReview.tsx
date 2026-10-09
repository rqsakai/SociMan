/*
 * Cartão de revisão de um clipe do OpenShorts (spec 006, US4; T059).
 *
 * <ClipReview corte videoUrl checked onCheck onChanged />
 *   player (link de mídia assinado da 004), trecho da fonte, gancho editável (só em "Em revisão",
 *   1 a 120 caracteres e até 3 linhas), título e pontuação do OpenShorts, status da marca,
 *   "Aplicar marca", "Arquivar"/"Restaurar" e o link para o corte.
 */
import { ApiError } from "@sociman/contract";
import { Archive, ArchiveRestore, ExternalLink, Loader2, Save, Stamp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatDuration, type Corte } from "@/lib/marca";
import { errorText } from "@/lib/perfis";
import { cn } from "@/lib/utils";
import { CorteStatusBadge } from "../marca/CorteStatusBadge";

// 754000 → "12:34" (posição no vídeo-fonte).
function trecho(c: Pick<Corte, "sourceStartMs" | "sourceEndMs">): string | null {
  if (c.sourceStartMs === null || c.sourceStartMs === undefined || c.sourceEndMs === null || c.sourceEndMs === undefined) return null;
  return `${formatDuration(c.sourceStartMs)}–${formatDuration(c.sourceEndMs)}`;
}

export function hookProblem(text: string): string | null {
  const t = text.trim();
  if (!t) return "Escreva o texto do gancho";
  if (t.length > 120 || t.split("\n").length > 3) return "Gancho longo demais (até 120 caracteres e 3 linhas)";
  return null;
}

export function ClipReview({
  corte,
  videoUrl,
  checked,
  onCheck,
  onChanged,
}: {
  corte: Corte;
  videoUrl: string | null;
  checked: boolean;
  onCheck: (checked: boolean) => void;
  onChanged: () => Promise<void>;
}) {
  const [hook, setHook] = useState(corte.hookText);
  const [hookError, setHookError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"hook" | "marca" | "archive" | null>(null);
  const revisao = corte.status === "revisao";
  const dirty = hook.trim() !== corte.hookText.trim();
  const label = corte.openshortsTitle || corte.hookText || `Clipe ${(corte.clipIndex ?? 0) + 1}`;

  async function run(kind: "hook" | "marca" | "archive", fn: () => Promise<unknown>, done: string) {
    setBusy(kind);
    try {
      await fn();
      toast.success(done);
      await onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_hook") setHookError(err.message);
      else toast.error(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  async function saveHook() {
    const problem = hookProblem(hook);
    setHookError(problem);
    if (problem) return;
    await run("hook", () => api.cortes.update(corte.id, { version: corte.version, hookText: hook.trim() }), "Gancho salvo.");
  }

  async function aplicar() {
    const problem = hookProblem(hook);
    setHookError(problem);
    if (problem) return;
    await run(
      "marca",
      async () => {
        let version = corte.version;
        if (dirty) version = (await api.cortes.update(corte.id, { version, hookText: hook.trim() })).corte.version;
        await api.cortes.aplicarMarca([{ corteId: corte.id, version }]);
      },
      "Marca na fila.",
    );
  }

  return (
    <article
      aria-label={`Clipe: ${label}`}
      className={cn("flex min-w-0 flex-col gap-3 rounded-xl bg-card p-3 shadow-card", corte.archived && "opacity-60", checked && "ring-2 ring-primary")}
    >
      <div className="flex items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            disabled={!revisao || corte.archived}
            checked={checked}
            onChange={(e) => onCheck(e.target.checked)}
            aria-label={`Marcar clipe ${(corte.clipIndex ?? 0) + 1}`}
          />
          Clipe {(corte.clipIndex ?? 0) + 1}
        </label>
        <div className="flex items-center gap-1.5">
          {corte.openshortsScore !== null && corte.openshortsScore !== undefined && (
            <Badge variant="outline" title="Pontuação do SociShorts">
              {Math.round(corte.openshortsScore)}
            </Badge>
          )}
          {corte.archived ? <Badge className="bg-dark text-dark-foreground">Arquivado</Badge> : <CorteStatusBadge corte={corte} />}
        </div>
      </div>

      {videoUrl ? (
        <video
          key={videoUrl}
          controls
          playsInline
          preload="metadata"
          src={videoUrl}
          poster={corte.posterUrl ?? undefined}
          aria-label={`Vídeo do clipe ${(corte.clipIndex ?? 0) + 1}`}
          className="mx-auto aspect-[9/16] max-h-[60vh] w-full rounded-lg bg-black object-contain"
        />
      ) : (
        <Skeleton className="aspect-[9/16] w-full rounded-lg" />
      )}

      <div className="space-y-1 text-sm">
        {corte.openshortsTitle && <p className="line-clamp-2 font-medium">{corte.openshortsTitle}</p>}
        <p className="text-xs text-muted-foreground">
          {trecho(corte) ? `Trecho ${trecho(corte)} da fonte · ` : ""}
          {formatDuration(corte.durationMs)}
          {corte.legenda === "sem_fala" ? " · sem fala" : ""}
        </p>
      </div>

      <div className="space-y-1">
        <label htmlFor={`hook-${corte.id}`} className="text-xs font-medium">
          Gancho
        </label>
        <Textarea
          id={`hook-${corte.id}`}
          rows={2}
          maxLength={120}
          value={hook}
          readOnly={!revisao || corte.archived}
          aria-invalid={Boolean(hookError)}
          onChange={(e) => {
            setHook(e.target.value);
            setHookError(null);
          }}
          className={cn(!revisao && "bg-muted")}
        />
        <p className={cn("text-xs", hookError ? "text-destructive" : "text-muted-foreground")} role={hookError ? "alert" : undefined}>
          {hookError ?? `${hook.trim().length}/120; até 3 linhas.`}
        </p>
      </div>

      <div className="mt-auto flex flex-wrap gap-2">
        {revisao && !corte.archived && (
          <>
            <Button type="button" size="sm" disabled={busy !== null} aria-busy={busy === "marca"} onClick={() => void aplicar()}>
              {busy === "marca" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Stamp aria-hidden="true" />}
              Aplicar marca
            </Button>
            {dirty && (
              <Button type="button" variant="outline" size="sm" disabled={busy !== null} aria-busy={busy === "hook"} onClick={() => void saveHook()}>
                {busy === "hook" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                Salvar gancho
              </Button>
            )}
          </>
        )}
        {corte.status !== "processando" && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy !== null}
            aria-busy={busy === "archive"}
            onClick={() =>
              void run(
                "archive",
                () => (corte.archived ? api.cortes.restore(corte.id, corte.version) : api.cortes.archive(corte.id, corte.version)),
                corte.archived ? "Clipe restaurado." : "Clipe arquivado.",
              )
            }
          >
            {corte.archived ? <ArchiveRestore aria-hidden="true" /> : <Archive aria-hidden="true" />}
            {corte.archived ? "Restaurar" : "Arquivar"}
          </Button>
        )}
        <Button variant="ghost" size="sm" asChild>
          <Link to={`/app/cortes/${corte.id}`}>
            <ExternalLink aria-hidden="true" />
            Abrir
          </Link>
        </Button>
      </div>
    </article>
  );
}
