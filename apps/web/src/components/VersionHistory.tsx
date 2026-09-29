import type { EntityVersion } from "@sociman/contract";
import { History, Undo2 } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../lib/authStore";
import { errorText } from "../lib/perfis";
import { Alert, Button } from "./ui";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });

export const actionLabel: Record<EntityVersion["action"], string> = {
  created: "Criado",
  updated: "Alterado",
  archived: "Arquivado",
  restored: "Restaurado",
  reverted: "Revertido",
};

const actorKindLabel: Record<string, string> = { "system:cli": "CLI", mcp_client: "Cliente MCP" };

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
}

// Histórico genérico de um registro versionado (FR-012): da versão mais recente para a mais
// antiga, com Campo | Antes | Depois só dos campos que mudaram. Reutilizável pelas próximas specs.
export function VersionHistory({ versions, labels, formatValue, onRevert }: VersionHistoryProps) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const [confirming, setConfirming] = useState<number | null>(null);
  const [reverting, setReverting] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const current = versions[0]?.version;
  const canRevert = Boolean(onRevert) && isOwner;

  async function revert(toVersion: number) {
    if (!onRevert) return;
    setReverting(true);
    setFeedback(null);
    try {
      await onRevert(toVersion);
      setFeedback({ tone: "success", text: `Revertido para a versão ${toVersion}.` });
      setConfirming(null);
    } catch (err) {
      setFeedback({ tone: "error", text: errorText(err) });
    } finally {
      setReverting(false);
    }
  }

  if (versions.length === 0) {
    return <p className="text-sm text-muted">Nenhuma alteração registrada.</p>;
  }

  return (
    <div className="space-y-4">
      {feedback && <Alert tone={feedback.tone}>{feedback.text}</Alert>}
      <ol className="space-y-4">
        {versions.map((v) => {
          const fromVersion = typeof v.details.from_version === "number" ? v.details.from_version : null;
          // "archived" também está no snapshot, mas a ação já diz isso; a tabela fica para os dados.
          const fields = v.changedFields.filter((f) => v.action === "updated" || v.action === "reverted" || f !== "archived");
          return (
            <li key={v.version} className="rounded-panel border border-border p-4" aria-label={`Versão ${v.version}`}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm">
                  <span className="font-medium">Versão {v.version}</span>
                  {" · "}
                  <span className="font-medium">{actionLabel[v.action]}</span>
                  {fromVersion !== null && <span className="text-muted"> (para a versão {fromVersion})</span>}
                  {v.version === current && <span className="text-muted"> · atual</span>}
                </p>
                <p className="text-xs text-muted">
                  {actorText(v)} · <time dateTime={v.occurredAt}>{dateFormat.format(new Date(v.occurredAt))}</time>
                </p>
              </div>

              {fields.length > 0 && (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-border text-muted">
                      <tr>
                        <th className="py-1 pr-4 font-medium">Campo</th>
                        <th className="py-1 pr-4 font-medium">Antes</th>
                        <th className="py-1 font-medium">Depois</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.map((field) => (
                        <tr key={field} className="border-b border-border align-top last:border-0">
                          <td className="py-1 pr-4 whitespace-nowrap">{labels[field] ?? field}</td>
                          <td className="py-1 pr-4 break-words whitespace-pre-wrap text-muted">
                            {v.before ? formatValue(field, v.before[field]) : "—"}
                          </td>
                          <td className="py-1 break-words whitespace-pre-wrap">{formatValue(field, v.after[field])}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {canRevert && v.version !== current && (
                <div className="mt-3">
                  {confirming === v.version ? (
                    // Confirmação no próprio item, como diálogo não modal (sem window.confirm).
                    <div
                      role="dialog"
                      aria-label={`Reverter para a versão ${v.version}`}
                      className="flex flex-wrap items-center gap-2 rounded-field border border-border bg-bg p-3 text-sm"
                    >
                      <span>
                        Voltar aos valores da versão {v.version}? A reversão entra no histórico como uma nova versão; nada é
                        apagado.
                      </span>
                      <Button type="button" className="!w-auto" loading={reverting} onClick={() => void revert(v.version)}>
                        Reverter
                      </Button>
                      <Button type="button" variant="ghost" className="!w-auto" disabled={reverting} onClick={() => setConfirming(null)}>
                        Cancelar
                      </Button>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      variant="ghost"
                      className="!w-auto border border-border"
                      disabled={reverting}
                      onClick={() => {
                        setFeedback(null);
                        setConfirming(v.version);
                      }}
                    >
                      <Undo2 className="size-4" aria-hidden="true" />
                      Reverter para esta versão
                    </Button>
                  )}
                </div>
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
    <h2 className="mb-4 flex items-center gap-2 text-lg font-medium">
      <History className="size-5 text-muted" aria-hidden="true" />
      {children}
    </h2>
  );
}
