import { ChevronDown, Loader2, Plus } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "../../lib/api";
import {
  checkImageFile,
  fileBaseName,
  fileRule,
  SINGLE_FILE_TIPOS,
  tipoLabel,
  uploadSingleAsset,
  type AssetTipo,
} from "../../lib/assets";
import { errorText } from "../../lib/perfis";

type NamedTipo = "avatar" | "cenario";

// "Novo asset" (FR-001): Avatar e Cenário pedem o nome e abrem o detalhe; Fundo, Sticker, Marca
// d'água e Imagem abrem o seletor de arquivos (vários de uma vez, um asset por arquivo).
export function NovoAssetMenu({
  perfilId,
  disabled,
  onCreated,
}: {
  perfilId: string;
  disabled?: boolean;
  onCreated: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [named, setNamed] = useState<NamedTipo | null>(null);
  const [fileTipo, setFileTipo] = useState<AssetTipo>("fundo");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [failures, setFailures] = useState<{ name: string; message: string }[]>([]);

  function pickFiles(tipo: AssetTipo) {
    setFileTipo(tipo);
    setFailures([]);
    // o accept depende do tipo; espera o re-render antes de abrir o seletor
    window.setTimeout(() => inputRef.current?.click(), 0);
  }

  async function uploadAll(files: File[]) {
    const tipo = fileTipo;
    const failed: { name: string; message: string }[] = [];
    setProgress({ done: 0, total: files.length });
    for (const [i, file] of files.entries()) {
      const problem = await checkImageFile(file, tipo);
      if (problem) {
        failed.push({ name: file.name, message: problem });
      } else {
        try {
          await uploadSingleAsset(perfilId, tipo, file, { name: fileBaseName(file.name) });
        } catch (err) {
          failed.push({ name: file.name, message: errorText(err) });
        }
      }
      setProgress({ done: i + 1, total: files.length });
    }
    setProgress(null);
    setFailures(failed);
    const ok = files.length - failed.length;
    if (ok > 0) {
      toast.success(ok === 1 ? `${tipoLabel[tipo]} enviado.` : `${ok} arquivos enviados como ${tipoLabel[tipo]}.`);
      await onCreated();
    }
  }

  const busy = progress !== null;
  return (
    <div className="space-y-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="secondary" size="sm" disabled={disabled || busy} aria-busy={busy}>
            {progress ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
            {progress ? `Enviando ${Math.min(progress.done + 1, progress.total)} de ${progress.total}…` : "Novo asset"}
            <ChevronDown aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setNamed("avatar")}>{tipoLabel.avatar}</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setNamed("cenario")}>{tipoLabel.cenario}</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Enviar arquivos</DropdownMenuLabel>
          {SINGLE_FILE_TIPOS.map((tipo) => (
            <DropdownMenuItem key={tipo} onSelect={() => pickFiles(tipo)}>
              {tipoLabel[tipo]}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={fileRule[fileTipo].accepted.join(",")}
        className="sr-only"
        aria-label={`Arquivos de ${tipoLabel[fileTipo]}`}
        tabIndex={-1}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) void uploadAll(files);
        }}
      />
      {failures.length > 0 && (
        <ul role="alert" className="space-y-0.5 rounded-md bg-card px-3 py-2 text-sm text-destructive shadow-card">
          {failures.map((f) => (
            <li key={f.name}>
              {f.name}: {f.message}
            </li>
          ))}
        </ul>
      )}
      <NovoAssetDialog
        perfilId={perfilId}
        tipo={named}
        onClose={() => setNamed(null)}
        onCreated={async (id) => {
          setNamed(null);
          await onCreated();
          navigate(`/app/assets/${id}`);
        }}
      />
    </div>
  );
}

function NovoAssetDialog({
  perfilId,
  tipo,
  onClose,
  onCreated,
}: {
  perfilId: string;
  tipo: NamedTipo | null;
  onClose: () => void;
  onCreated: (id: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!tipo) return;
    setError(null);
    const trimmed = name.trim();
    if (trimmed.length < 1 || trimmed.length > 80) return setNameError("Dê um nome de até 80 caracteres");
    setNameError(null);
    setBusy(true);
    try {
      const { asset } = await api.assets.create(perfilId, { tipo, name: trimmed });
      toast.success(`${tipoLabel[tipo]} "${asset.name}" criado.`);
      setName("");
      await onCreated(asset.id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={tipo !== null}
      onOpenChange={(open) => {
        if (!open) {
          setError(null);
          setNameError(null);
          onClose();
        }
      }}
    >
      <DialogContent>
        <form onSubmit={(e) => void submit(e)} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{tipo === "cenario" ? "Novo cenário" : "Novo avatar"}</DialogTitle>
            <DialogDescription>
              {tipo === "cenario"
                ? "Depois de criar, preencha o prompt do ambiente e envie as imagens de referência."
                : "Depois de criar, preencha a descrição para prompts e envie os looks e as poses."}
            </DialogDescription>
          </DialogHeader>
          <Field label="Nome" error={nameError ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                value={name}
                maxLength={80}
                autoComplete="off"
                autoFocus
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </Field>
          {error !== null && <ApiErrorAlert error={error} />}
          <DialogFooter>
            <Button type="submit" disabled={busy} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
              Criar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
