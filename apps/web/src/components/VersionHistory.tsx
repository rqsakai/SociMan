import type { EntityVersion } from "@sociman/contract";
import { History, Loader2, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "../lib/authStore";
import { ApiErrorAlert } from "./ApiErrorAlert";
import { iaDaVersao, IaSelo } from "./ia/IaSelo";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });

export const actionLabel: Record<EntityVersion["action"], string> = {
  created: "Criado",
  updated: "Alterado",
  archived: "Arquivado",
  restored: "Restaurado",
  reverted: "Revertido",
};

// Cor do ponto na linha do tempo, por ação.
const actionDot: Record<EntityVersion["action"], string> = {
  created: "tone-success",
  updated: "tone-primary",
  archived: "tone-dark",
  restored: "tone-info",
  reverted: "tone-warning",
};

const actorKindLabel: Record<string, string> = { "system:cli": "CLI", "system:agendador": "Agendador", mcp_client: "Cliente MCP", "system:publicacao": "Envio automático" };

function actorText(version: EntityVersion): string {
  return version.actor?.name ?? actorKindLabel[version.actorKind] ?? "—";
}

interface VersionHistoryProps {
  versions: EntityVersion[];
  // Rótulo de cada campo do snapshot; campos sem rótulo aparecem pelo nome técnico.
  labels: Record<string, string>;
  formatValue: (field: string, value: unknown) => string;
  // Sem `onRevert` não há botão de reversão. Com ele, o botão aparece só para o dono (princípio VII).
  onRevert?: (toVersion: number) => Promise<void>;
  // Recarrega o registro depois de um conflito de versão (botão "Recarregar" no aviso de erro).
  onReload?: () => Promise<void>;
}

// Histórico genérico de um registro versionado (FR-012) em linha do tempo: da versão mais
// recente para a mais antiga, com Campo | Antes | Depois só dos campos que mudaram.
// Reutilizável pelas próximas specs.
export function VersionHistory({ versions, labels, formatValue, onRevert, onReload }: VersionHistoryProps) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const [reverting, setReverting] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const current = versions[0]?.version;
  const canRevert = Boolean(onRevert) && isOwner;

  async function revert(toVersion: number) {
    if (!onRevert) return;
    setReverting(toVersion);
    setError(null);
    try {
      await onRevert(toVersion);
      toast.success(`Revertido para a versão ${toVersion}.`);
    } catch (err) {
      setError(err);
    } finally {
      setReverting(null);
    }
  }

  if (versions.length === 0) {
    return <p className="text-sm text-muted-foreground">Nenhuma alteração registrada.</p>;
  }

  return (
    <div className="space-y-4">
      {error !== null && (
        <ApiErrorAlert
          error={error}
          onReload={
            onReload &&
            (() => {
              setError(null);
              void onReload();
            })
          }
        />
      )}
      <ol className="relative space-y-6 border-l-2 border-border pl-6 sm:ml-2">
        {versions.map((v) => {
          const fromVersion = typeof v.details.from_version === "number" ? v.details.from_version : null;
          const ia = iaDaVersao(v.details);
          // "archived" também está no snapshot, mas a ação já diz isso; a tabela fica para os dados.
          const fields = v.changedFields.filter((f) => v.action === "updated" || v.action === "reverted" || f !== "archived");
          return (
            <li key={v.version} className="relative" aria-label={`Versão ${v.version}`}>
              <span
                className={cn("absolute top-1 -left-[2.0625rem] size-4 rounded-full ring-4 ring-card", actionDot[v.action])}
                aria-hidden="true"
              />
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <p className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-semibold">{actionLabel[v.action]}</span>
                  <span className="text-muted-foreground">versão {v.version}</span>
                  {fromVersion !== null && <span className="text-muted-foreground">(para a versão {fromVersion})</span>}
                  {v.version === current && <Badge variant="secondary">atual</Badge>}
                  {ia && <IaSelo chamadaId={ia[0]?.chamadaId} />}
                </p>
                <p className="text-xs text-muted-foreground">
                  {actorText(v)} · <time dateTime={v.occurredAt}>{dateFormat.format(new Date(v.occurredAt))}</time>
                </p>
              </div>

              {fields.length > 0 && (
                <div className="mt-2 overflow-x-auto rounded-lg border bg-card">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b bg-muted/50 text-xs text-muted-foreground uppercase">
                      <tr>
                        <th className="px-3 py-2 font-semibold">Campo</th>
                        <th className="px-3 py-2 font-semibold">Antes</th>
                        <th className="px-3 py-2 font-semibold">Depois</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.map((field) => (
                        <tr key={field} className="border-b align-top last:border-0">
                          <td className="px-3 py-2 font-medium whitespace-nowrap">{labels[field] ?? field}</td>
                          <td className="px-3 py-2 break-words whitespace-pre-wrap text-muted-foreground">
                            {v.before ? formatValue(field, v.before[field]) : "—"}
                          </td>
                          <td className="px-3 py-2 break-words whitespace-pre-wrap">{formatValue(field, v.after[field])}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {canRevert && v.version !== current && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-2"
                      disabled={reverting !== null}
                      aria-busy={reverting === v.version}
                    >
                      {reverting === v.version ? (
                        <Loader2 className="animate-spin" aria-hidden="true" />
                      ) : (
                        <Undo2 aria-hidden="true" />
                      )}
                      Reverter para esta versão
                    </Button>
                  </AlertDialogTrigger>
                  {/* role "dialog" em vez de "alertdialog": contrato de UI dos e2e (getByRole("dialog")) */}
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Reverter para a versão {v.version}?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Os valores voltam aos da versão {v.version}. A reversão entra no histórico como uma nova versão; nada é
                        apagado.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancelar</AlertDialogCancel>
                      <AlertDialogAction onClick={() => void revert(v.version)}>Reverter</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function HistoryHeading({ children }: { children: string }) {
  return (
    <h2 className="flex items-center gap-2 text-base leading-none font-semibold">
      <History className="size-5 text-muted-foreground" aria-hidden="true" />
      {children}
    </h2>
  );
}
