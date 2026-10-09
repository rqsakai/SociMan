import { ChevronDown, Loader2, Plus } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PerfilBaseField } from "@/components/estudio/PerfilBaseField";
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
  TIPOS,
  uploadSingleAsset,
  type AssetTipo,
} from "../../lib/assets";
import { errorText } from "../../lib/perfis";

type NamedTipo = "avatar" | "cenario";
const ehNomeado = (t: AssetTipo): t is NamedTipo => t === "avatar" || t === "cenario";

// "Novo asset" (007 FR-001; 029 T025): Avatar e Cenário pedem o nome e o perfil base e abrem o
// detalhe; Fundo, Sticker, Marca d'água e Imagem abrem o seletor de arquivos (vários de uma vez, um
// asset por arquivo) e nascem com o `perfilId` dado (o filtro da lista; null = sem perfil). Com um
// tipo nomeado só (`tipos` = ["avatar"]), vira o botão "Novo avatar".
export function NovoAssetMenu({
  perfilId,
  tipos = TIPOS,
  disabled,
  onCreated,
}: {
  perfilId: string | null;
  tipos?: readonly AssetTipo[];
  disabled?: boolean;
  onCreated: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [named, setNamed] = useState<NamedTipo | null>(null);
  const [fileTipo, setFileTipo] = useState<AssetTipo>("fundo");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [failures, setFailures] = useState<{ name: string; message: string }[]>([]);
  const nomeados = tipos.filter(ehNomeado);
  const arquivos = SINGLE_FILE_TIPOS.filter((t) => tipos.includes(t));

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
  const unico = nomeados.length === 1 && arquivos.length === 0 ? nomeados[0]! : null;
  return (
    <div className="space-y-2">
      {unico ? (
        <Button type="button" variant="secondary" size="sm" disabled={disabled} onClick={() => setNamed(unico)}>
          <Plus aria-hidden="true" />
          {unico === "avatar" ? "Novo avatar" : "Novo cenário"}
        </Button>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="secondary" size="sm" disabled={disabled || busy} aria-busy={busy}>
              {progress ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
              {progress ? `Enviando ${Math.min(progress.done + 1, progress.total)} de ${progress.total}…` : "Novo asset"}
              <ChevronDown aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {nomeados.map((t) => (
              <DropdownMenuItem key={t} onSelect={() => setNamed(t)}>
                {tipoLabel[t]}
              </DropdownMenuItem>
            ))}
            {nomeados.length > 0 && arquivos.length > 0 && <DropdownMenuSeparator />}
            {arquivos.length > 0 && <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Enviar arquivos</DropdownMenuLabel>}
            {arquivos.map((tipo) => (
              <DropdownMenuItem key={tipo} onSelect={() => pickFiles(tipo)}>
                {tipoLabel[tipo]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
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

// Criar avatar ou cenário: o nome e o perfil base (o padrão vem de quem abre). Também usado pela
// criação no lugar da cena (029 FR-016), que fica na cena em vez de abrir o detalhe.
export function NovoAssetDialog({
  perfilId,
  tipo,
  onClose,
  onCreated,
}: {
  perfilId: string | null;
  tipo: NamedTipo | null;
  onClose: () => void;
  onCreated: (id: string) => Promise<void> | void;
}) {
  const [name, setName] = useState("");
  const [perfilBase, setPerfilBase] = useState<string | null>(perfilId);
  const [nameError, setNameError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [aberto, setAberto] = useState<NamedTipo | null>(null);
  // ao abrir, o perfil base volta ao padrão de quem abriu
  if (tipo !== aberto) {
    setAberto(tipo);
    if (tipo) setPerfilBase(perfilId);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!tipo) return;
    setError(null);
    const trimmed = name.trim();
    if (trimmed.length < 1 || trimmed.length > 80) return setNameError("Dê um nome de até 80 caracteres");
    setNameError(null);
    setBusy(true);
    try {
      const { asset } = await api.assets.criarAgencia({ tipo, name: trimmed, perfilId: perfilBase });
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
        if (!open && !busy) {
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
                ? "Depois de criar, preencha o prompt do ambiente e gere a cena padrão."
                : "Depois de criar, monte o kit padrão: rosto de origem, rosto frontal, rostos 3/4 e corpo-base."}
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
          <PerfilBaseField value={perfilBase} onChange={setPerfilBase} hint="O guia e as palavras proibidas deste perfil entram nas gerações." />
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
