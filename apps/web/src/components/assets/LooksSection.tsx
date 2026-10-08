import { useState } from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { activeFiles, archivedFiles, type Asset, type AssetFile } from "../../lib/assets";
import { AssetFileCard, type RunAction } from "./AssetFileCard";
import { reorderFiles, useNativeDrag } from "./PosesGrid";
import { moveItem } from "./ReorderButtons";
import { EmptyState } from "@/components/shell";

const NO_LOOK = "Sem look";

// Referências do avatar agrupadas por look (US1, cenário 2), com o uso, "Marcar como principal" e
// a ordem (dentro do grupo, "mover ←/→" troca com a vizinha; a ordem gravada é a de todas as
// referências).
export function LooksSection({ asset, run }: { asset: Asset; run: RunAction }) {
  const [busy, setBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const files = activeFiles(asset, "referencia");
  const archived = archivedFiles(asset, "referencia");
  const ids = files.map((f) => f.id);

  // Grupos na ordem da primeira aparição de cada look.
  const groups = new Map<string, AssetFile[]>();
  for (const f of files) {
    const key = f.look?.trim() || NO_LOOK;
    groups.set(key, [...(groups.get(key) ?? []), f]);
  }

  async function moveById(fromId: string, toId: string) {
    const from = ids.indexOf(fromId);
    const to = ids.indexOf(toId);
    if (from < 0 || to < 0 || from === to) return;
    setBusy(true);
    await reorderFiles(run, asset, "referencia", moveItem(ids, from, to));
    setBusy(false);
  }

  const drag = useNativeDrag(!busy && !asset.archived && files.length > 1, (a, b) => void moveById(a, b));

  return (
    <div className="space-y-5">
      {files.length === 0 && <EmptyState titulo="Nenhuma imagem de referência ainda." className="py-4" />}
      {[...groups.entries()].map(([look, group]) => (
        <section key={look} aria-label={`Look ${look}`} className="space-y-2">
          <h3 className="text-sm font-semibold">
            {look} <span className="font-normal text-muted-foreground">({group.length})</span>
          </h3>
          <ol className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
            {group.map((file, i) => (
              <AssetFileCard
                key={file.id}
                asset={asset}
                file={file}
                index={i}
                run={run}
                reorder={{
                  count: group.length,
                  busy,
                  onMove: (a, b) => {
                    const target = group[b];
                    if (target) void moveById(group[a]?.id ?? "", target.id);
                  },
                }}
                dragProps={drag.props(file.id)}
                dragging={drag.dragId === file.id}
              />
            ))}
          </ol>
        </section>
      ))}
      {archived.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Switch id={`arq-${asset.id}-looks`} checked={showArchived} onCheckedChange={setShowArchived} />
            <Label htmlFor={`arq-${asset.id}-looks`}>Mostrar referências arquivadas ({archived.length})</Label>
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
