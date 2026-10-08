/*
 * Campo de arquivo (spec 024, R12): o `input type=file` do navegador mostra "Choose file / No file
 * chosen" na língua da máquina; aqui o texto é sempre em pt-BR e dá para soltar o arquivo.
 *
 * <Field label="Vídeo">
 *   {({ id }) => <FileField id={id} accept="video/mp4,.mov" onChange={(e) => pick(e.target.files?.[0] ?? null)} />}
 * </Field>
 *
 * - o `input type=file` continua no DOM (escondido com `sr-only`): `id`, `name`, `accept`, `multiple`,
 *   `required`, `disabled`, `aria-*`, `onChange` e `ref` vão para ele, então o `getByLabel` e o
 *   `setInputFiles` dos e2e continuam funcionando;
 * - botão "Escolher arquivo" (ou `rotuloBotao`) e, ao lado, "Nenhum arquivo escolhido", o nome ou
 *   "N arquivos";
 * - soltar arquivos na área: passa pelo `accept` (sem `multiple`, só o primeiro) e dispara o mesmo
 *   `onChange` de quando se escolhe;
 * - quem zera o input pela `ref` (`ref.current.value = ""`) troca a `key` do FileField para o texto
 *   voltar a "Nenhum arquivo escolhido".
 */
import { Upload } from "lucide-react";
import { useId, useRef, useState, type ChangeEvent, type ComponentProps, type DragEvent, type Ref } from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

type Props = Omit<ComponentProps<"input">, "type" | "value" | "defaultValue"> & {
  rotuloBotao?: string;
};

// mesmo critério do `accept` do navegador: extensão (".mp4"), tipo exato ou "video/*"
function aceita(arquivo: File, accept: string | undefined): boolean {
  if (!accept) return true;
  const nome = arquivo.name.toLowerCase();
  const tipo = arquivo.type.toLowerCase();
  return accept
    .split(",")
    .map((a) => a.trim().toLowerCase())
    .filter(Boolean)
    .some((a) => (a.startsWith(".") ? nome.endsWith(a) : a.endsWith("/*") ? tipo.startsWith(a.slice(0, -1)) : tipo === a));
}

function resumo(arquivos: File[]): string {
  if (arquivos.length === 0) return "Nenhum arquivo escolhido";
  if (arquivos.length === 1) return arquivos[0]!.name;
  return `${arquivos.length} arquivos`;
}

function juntarRefs<T>(...refs: (Ref<T> | undefined)[]) {
  return (el: T | null) => {
    for (const r of refs) {
      if (typeof r === "function") r(el);
      else if (r) r.current = el;
    }
  };
}

export function FileField({ ref, className, onChange, rotuloBotao = "Escolher arquivo", disabled, ...rest }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [arrastando, setArrastando] = useState(false);
  const resumoId = useId();

  function aoMudar(e: ChangeEvent<HTMLInputElement>) {
    setArquivos(Array.from(e.target.files ?? []));
    onChange?.(e);
  }

  function aoSoltar(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setArrastando(false);
    const input = inputRef.current;
    if (disabled || !input) return;
    let soltos = Array.from(e.dataTransfer.files).filter((f) => aceita(f, rest.accept));
    if (!rest.multiple) soltos = soltos.slice(0, 1);
    if (soltos.length === 0) return;
    const dt = new DataTransfer();
    soltos.forEach((f) => dt.items.add(f));
    input.files = dt.files;
    // o mesmo evento de quando se escolhe: o onChange do React escuta o "change" nativo
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  return (
    <div
      className={cn(
        "flex min-w-0 flex-wrap items-center gap-3 rounded-md border border-dashed border-input px-3 py-2 transition-colors",
        arrastando && "border-primary bg-primary/5",
        disabled && "opacity-50",
        className,
      )}
      onDragOver={(e) => {
        if (disabled) return;
        e.preventDefault();
        setArrastando(true);
      }}
      onDragLeave={() => setArrastando(false)}
      onDrop={aoSoltar}
    >
      {/* fora do Tab: quem recebe o foco é o botão (o rótulo do Field continua abrindo o seletor) */}
      <input {...rest} ref={juntarRefs(inputRef, ref)} type="file" disabled={disabled} tabIndex={-1} className="sr-only" onChange={aoMudar} />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        aria-describedby={resumoId}
        onClick={() => inputRef.current?.click()}
      >
        <Upload aria-hidden="true" />
        {rotuloBotao}
      </Button>
      <span className={cn("min-w-0 truncate text-sm", arquivos.length === 0 && "text-muted-foreground")} id={resumoId} aria-live="polite">
        {resumo(arquivos)}
      </span>
      <span className="text-xs text-muted-foreground max-sm:hidden">ou solte aqui</span>
    </div>
  );
}
