import { Archive, ArchiveRestore, Download, Loader2, Pencil, Save, Star } from "lucide-react";
import { useState, type FormEvent, type HTMLAttributes } from "react";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { api } from "../../lib/api";
import { absoluteUrl, checkerClass, type Asset, type AssetFile } from "../../lib/assets";
import { CopyButton } from "./CopyButton";
import { ReorderButtons } from "./ReorderButtons";

// Executa uma mutação do asset (com o erro e o recarregamento na página); true se deu certo.
export type RunAction = (action: () => Promise<unknown>, done: string) => Promise<boolean>;

// Nome de um arquivo nos rótulos: o rótulo da pose, o look da referência ou "Imagem N".
export function fileName(file: AssetFile, index: number): string {
  return file.label || file.look || `Imagem ${index + 1}`;
}

// Card de um arquivo do asset (US1, US4): imagem, rótulo/look/uso, "Principal", "Baixar
// original", "Copiar link", editar os metadados e arquivar/restaurar. Em listas ordenadas recebe
// os botões "mover ←/→" e as props de arrastar (HTML5 nativo) do item.
export function AssetFileCard({
  asset,
  file,
  index,
  run,
  reorder,
  dragProps,
  dragging,
}: {
  asset: Asset;
  file: AssetFile;
  index: number;
  run: RunAction;
  reorder?: { count: number; busy: boolean; onMove: (from: number, to: number) => void };
  dragProps?: HTMLAttributes<HTMLLIElement>;
  dragging?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const name = fileName(file, index);
  const primary = asset.primaryFileId === file.id;
  const multi = asset.tipo === "avatar" || asset.tipo === "cenario";
  const locked = asset.archived;

  return (
    <li
      {...dragProps}
      aria-label={`${file.role === "pose" ? "Pose" : "Imagem"} ${name}`}
      className={cn(
        "flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-card",
        file.archived && "opacity-70",
        dragging && "ring-2 ring-primary",
        dragProps?.draggable && "cursor-grab",
      )}
    >
      <div className={cn("relative aspect-square bg-muted", file.hasAlpha && cn(checkerClass, "p-2"))}>
        <img
          src={file.image.urls.medium}
          alt={name}
          loading="lazy"
          draggable={false}
          className={cn("size-full", file.hasAlpha ? "object-contain" : "object-cover")}
        />
        <div className="absolute top-2 left-2 flex flex-wrap gap-1">
          {primary && (
            <Badge>
              <Star aria-hidden="true" />
              Principal
            </Badge>
          )}
          {file.archived && <Badge className="bg-dark text-dark-foreground">Arquivado</Badge>}
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="min-w-0 text-sm">
          {file.label && <p className="font-semibold">{file.label}</p>}
          {file.look && <p className="font-semibold">{file.look}</p>}
          {file.quandoUsar && <p className="text-muted-foreground">Quando usar: {file.quandoUsar}</p>}
          {file.uso && <p className="text-muted-foreground">Uso: {file.uso}</p>}
          {file.notes && <p className="text-xs text-muted-foreground">{file.notes}</p>}
          <p className="text-xs text-muted-foreground">
            {file.image.width}×{file.image.height} px
          </p>
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-1">
          {reorder && !file.archived && (
            <ReorderButtons index={index} count={reorder.count} name={name} disabled={reorder.busy || locked} onMove={reorder.onMove} />
          )}
          <Button type="button" variant="ghost" size="sm" asChild>
            <a href={file.downloadUrl} download>
              <Download aria-hidden="true" />
              Baixar original
            </a>
          </Button>
          <CopyButton text={absoluteUrl(file.link)} label="Copiar link" variant="ghost" />
          {multi && !file.archived && !primary && !locked && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void run(() => api.assets.update(asset.id, { version: asset.version, primaryFileId: file.id }), "Imagem principal trocada.")}
            >
              <Star aria-hidden="true" />
              Marcar como principal
            </Button>
          )}
          {multi && !file.archived && !locked && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
              <Pencil aria-hidden="true" />
              Editar
            </Button>
          )}
          {multi && !locked && (
            <ConfirmButton
              size="sm"
              variant="ghost"
              label={file.archived ? "Restaurar" : "Arquivar"}
              icon={file.archived ? ArchiveRestore : Archive}
              title={file.archived ? `Restaurar ${name}?` : `Arquivar ${name}?`}
              description={
                file.archived
                  ? "A imagem volta ao fim da ordem."
                  : "A imagem sai do asset, mas continua guardada e pode ser restaurada. Se estiver em uso no kit, o arquivamento é recusado."
              }
              onConfirm={async () => {
                await run(
                  () =>
                    file.archived
                      ? api.assets.restoreFile(asset.id, file.id, asset.version)
                      : api.assets.archiveFile(asset.id, file.id, asset.version),
                  file.archived ? "Imagem restaurada." : "Imagem arquivada.",
                );
              }}
            />
          )}
        </div>
      </div>
      {editing && <EditFileDialog asset={asset} file={file} run={run} onClose={() => setEditing(false)} />}
    </li>
  );
}

function EditFileDialog({ asset, file, run, onClose }: { asset: Asset; file: AssetFile; run: RunAction; onClose: () => void }) {
  const [look, setLook] = useState(file.look ?? "");
  const [uso, setUso] = useState(file.uso ?? "");
  const [label, setLabel] = useState(file.label ?? "");
  const [quandoUsar, setQuandoUsar] = useState(file.quandoUsar ?? "");
  const [notes, setNotes] = useState(file.notes);
  const [labelError, setLabelError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const withLook = asset.tipo === "avatar" && file.role === "referencia";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (file.role === "pose" && !label.trim()) return setLabelError("Dê um rótulo à pose");
    setLabelError(null);
    // Só manda o que mudou, com a versão lida (controle otimista).
    const body: Parameters<typeof api.assets.updateFile>[2] = { version: asset.version };
    // O look tem de 1 a 60 caracteres: apagar o campo mantém o look atual.
    if (withLook && look.trim() && look.trim() !== (file.look ?? "")) body.look = look.trim();
    if (file.role === "referencia" && uso.trim() !== (file.uso ?? "")) body.uso = uso.trim();
    if (file.role === "pose" && label.trim() !== (file.label ?? "")) body.label = label.trim();
    if (file.role === "pose" && quandoUsar.trim() !== (file.quandoUsar ?? "")) body.quandoUsar = quandoUsar.trim();
    if (notes.trim() !== file.notes) body.notes = notes.trim();
    if (Object.keys(body).length === 1) return onClose();
    setBusy(true);
    // Fecha também no erro: a mensagem (ex.: 409 pose_label_in_use) aparece no alerta da página.
    await run(() => api.assets.updateFile(asset.id, file.id, body), "Imagem atualizada.");
    setBusy(false);
    onClose();
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={(e) => void submit(e)} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{file.role === "pose" ? "Editar pose" : "Editar referência"}</DialogTitle>
            <DialogDescription>A imagem não muda; só os dados dela no asset.</DialogDescription>
          </DialogHeader>
          {withLook && (
            <Field label="Look">
              {({ id }) => <Input id={id} value={look} maxLength={60} autoComplete="off" onChange={(e) => setLook(e.target.value)} />}
            </Field>
          )}
          {file.role === "referencia" && (
            <Field label="Uso">
              {({ id }) => <Input id={id} value={uso} maxLength={200} autoComplete="off" onChange={(e) => setUso(e.target.value)} />}
            </Field>
          )}
          {file.role === "pose" && (
            <>
              <Field label="Rótulo da pose" error={labelError ?? undefined}>
                {({ id, describedBy, invalid }) => (
                  <Input
                    id={id}
                    value={label}
                    maxLength={60}
                    autoComplete="off"
                    aria-invalid={invalid}
                    aria-describedby={describedBy}
                    onChange={(e) => setLabel(e.target.value)}
                  />
                )}
              </Field>
              <Field label="Quando usar">
                {({ id }) => <Input id={id} value={quandoUsar} maxLength={300} autoComplete="off" onChange={(e) => setQuandoUsar(e.target.value)} />}
              </Field>
            </>
          )}
          <Field label="Notas">
            {({ id }) => <Textarea id={id} rows={2} value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} />}
          </Field>
          <DialogFooter>
            <Button type="submit" disabled={busy} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
