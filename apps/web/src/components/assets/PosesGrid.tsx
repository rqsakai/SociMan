import { useState, type HTMLAttributes } from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api } from "../../lib/api";
import { activeFiles, archivedFiles, type Asset, type AssetFile, type FileRole } from "../../lib/assets";
import { AssetFileCard, type RunAction } from "./AssetFileCard";
import { moveItem } from "./ReorderButtons";

// Reordena os arquivos ativos de um papel: uma chamada PUT /ordem com a lista inteira (uma versão
// por reordenação).
export function reorderFiles(run: RunAction, asset: Asset, role: FileRole, ids: string[]) {
  return run(() => api.assets.reorder(asset.id, { version: asset.version, role, fileIds: ids }), "Ordem salva.");
}

// Arrastar e soltar com a API nativa do HTML5 (Q3 = A): atalho do desktop para os botões
// "mover ←/→". `onDrop(from, to)` recebe os ids do item arrastado e do item alvo.
export function useNativeDrag(enabled: boolean, onDrop: (fromId: string, toId: string) => void) {
  const [dragId, setDragId] = useState<string | null>(null);
  const props = (id: string): HTMLAttributes<HTMLLIElement> | undefined =>
    enabled
      ? {
          draggable: true,
          onDragStart: (e) => {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", id);
            setDragId(id);
          },
          onDragOver: (e) => {
            if (dragId && dragId !== id) {
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
            }
          },
          onDrop: (e) => {
            e.preventDefault();
            const from = dragId ?? e.dataTransfer.getData("text/plain");
            setDragId(null);
            if (from && from !== id) onDrop(from, id);
          },
          onDragEnd: () => setDragId(null),
        }
      : undefined;
  return { dragId, props };
}

// Grade ordenada de arquivos de um papel (poses do avatar, referências do cenário), com
// "mover ←/→", arrastar no desktop e os arquivados sob "Mostrar arquivadas".
export function PosesGrid({
  asset,
  role,
  run,
  empty,
  archivedLabel = "Mostrar arquivadas",
}: {
  asset: Asset;
  role: FileRole;
  run: RunAction;
  empty: string;
  archivedLabel?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const files = activeFiles(asset, role);
  const archived = archivedFiles(asset, role);
  const ids = files.map((f) => f.id);

  async function move(from: number, to: number) {
    if (to < 0 || to >= ids.length || from === to) return;
    setBusy(true);
    await reorderFiles(run, asset, role, moveItem(ids, from, to));
    setBusy(false);
  }

  const drag = useNativeDrag(!busy && !asset.archived && files.length > 1, (fromId, toId) =>
    void move(ids.indexOf(fromId), ids.indexOf(toId)),
  );

  return (
    <div className="space-y-3">
      {files.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ol className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4" aria-label={role === "pose" ? "Poses" : "Referências"}>
          {files.map((file: AssetFile, i) => (
            <AssetFileCard
              key={file.id}
              asset={asset}
              file={file}
              index={i}
              run={run}
              reorder={{ count: files.length, busy, onMove: (a, b) => void move(a, b) }}
              dragProps={drag.props(file.id)}
              dragging={drag.dragId === file.id}
            />
          ))}
        </ol>
      )}
      {archived.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Switch id={`arq-${asset.id}-${role}`} checked={showArchived} onCheckedChange={setShowArchived} />
            <Label htmlFor={`arq-${asset.id}-${role}`}>
              {archivedLabel} ({archived.length})
            </Label>
          </div>
          {showArchived && (
            <ul className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
              {archived.map((file, i) => (
                <AssetFileCard key={file.id} asset={asset} file={file} index={i} run={run} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
