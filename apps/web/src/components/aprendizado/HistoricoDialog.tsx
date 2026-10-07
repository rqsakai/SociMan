/*
 * Histórico de um registro do aprendizado num diálogo (spec 023, princípio VII): temas,
 * classificações e preferências. A reversão aparece só para o dono (VersionHistory).
 */
import type { EntityVersion } from "@sociman/contract";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { VersionHistory } from "@/components/VersionHistory";

export function HistoricoDialog({
  titulo,
  descricao,
  aberto,
  onFechar,
  versions,
  carregando,
  erro,
  labels,
  formatValue,
  onRevert,
  onReload,
}: {
  titulo: string;
  descricao?: string;
  aberto: boolean;
  onFechar: () => void;
  versions: EntityVersion[] | undefined;
  carregando: boolean;
  erro: unknown;
  labels: Record<string, string>;
  formatValue: (field: string, value: unknown) => string;
  onRevert?: (toVersion: number) => Promise<void>;
  onReload?: () => Promise<void>;
}) {
  return (
    <Dialog open={aberto} onOpenChange={(o) => !o && onFechar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          {descricao && <DialogDescription>{descricao}</DialogDescription>}
        </DialogHeader>
        {erro ? (
          <ApiErrorAlert error={erro} />
        ) : carregando || !versions ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <VersionHistory versions={versions} labels={labels} formatValue={formatValue} onRevert={onRevert} onReload={onReload} />
        )}
      </DialogContent>
    </Dialog>
  );
}

// Valor de snapshot genérico: listas viram "a, b", booleanos "sim/não", vazio "—".
export function formatarValor(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map(String).join(", ") : "—";
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
