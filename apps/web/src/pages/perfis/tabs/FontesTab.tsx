import { ApiError, type Perfil } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Check, Loader2, Pencil, Upload, X } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { EmptyState, HeaderCard, Page } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileField } from "@/components/ui/file-field";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { fontStack, useKitFonts } from "../../../components/marca/useKitFonts";
import {
  fontesKey,
  formatBytes,
  kitFieldText,
  kitKey,
  normalizeKitField,
  SAMPLE_TEXT,
  type Fonte,
  type FontOption,
} from "../../../lib/marca";
import { api } from "../../../lib/api";

const MAX_BYTES = 10 * 1024 * 1024;

// Aba Fontes do perfil (US2, T016): as fontes padrão e as do perfil, cada uma com a amostra
// "Os achadinhos que você queria" na própria fonte; enviar (TTF/OTF até 10 MB, validado pelo
// conteúdo no servidor), renomear, arquivar (recusado se estiver em uso no kit) e restaurar.
// Nada é apagado.
export function FontesTab({ perfil }: { perfil: Perfil }) {
  const queryClient = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const fontes = useQuery({
    queryKey: fontesKey(perfil.id, showArchived),
    queryFn: () => api.fontes.list(perfil.id, showArchived),
  });
  const padrao = useQuery({ queryKey: ["fontes-padrao"], queryFn: () => api.fontes.padrao(), staleTime: Infinity });

  // URLs assinadas (1 h) para desenhar a amostra das fontes do perfil.
  const items = useMemo(() => fontes.data?.items ?? [], [fontes.data]);
  const links = useQuery({
    queryKey: ["fontes-links", perfil.id, items.map((f) => f.id).join(",")],
    queryFn: () => api.midia.links(items.map((f) => ({ kind: "fonte" as const, id: f.id }))),
    enabled: items.length > 0,
    staleTime: 30 * 60_000,
  });
  const options = useMemo<FontOption[]>(() => {
    const own = items.flatMap((f, i) => {
      const url = links.data?.items[i]?.url;
      return url ? [{ ref: `perfil:${f.id}`, name: f.name, family: f.family, url }] : [];
    });
    const std = (padrao.data?.items ?? []).map((p) => ({ ref: `padrao:${p.key}`, name: p.name, family: p.family, url: p.url }));
    return [...std, ...own];
  }, [items, links.data, padrao.data]);
  const ready = useKitFonts(options);

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["fontes", perfil.id] }),
      queryClient.invalidateQueries({ queryKey: kitKey(perfil.id) }),
    ]);
  }

  return (
    <Page>
      <UploadFont
        perfilId={perfil.id}
        onUploaded={async (fonte) => {
          toast.success(`Fonte "${fonte.name}" enviada.`);
          await refresh();
        }}
      />

      {error !== null && <FontErrorAlert error={error} onReload={() => void refresh().then(() => setError(null))} />}

      <HeaderCard
        title="Fontes do perfil"
        description="Aparecem nos seletores de fonte do kit junto com as padrão."
        actions={
          <div className="flex items-center gap-2">
            <Switch id="fontes-arquivadas" checked={showArchived} onCheckedChange={setShowArchived} />
            <Label htmlFor="fontes-arquivadas">Mostrar arquivadas</Label>
          </div>
        }
      >
        {fontes.isPending && <Skeleton className="h-24 w-full" />}
        {fontes.isError && <ApiErrorAlert error={fontes.error} />}
        {fontes.data && items.length === 0 && (
          <EmptyState titulo="Nenhuma fonte enviada." descricao={'Use "Enviar fonte" acima.'} className="py-4" />
        )}
        <ul className="divide-y" aria-label="Fontes do perfil">
          {items.map((fonte) => (
            <FontRow
              key={fonte.id}
              fonte={fonte}
              family={fontStack(`perfil:${fonte.id}`, ready)}
              onChanged={refresh}
              onError={setError}
              onStart={() => setError(null)}
            />
          ))}
        </ul>
      </HeaderCard>

      <HeaderCard title="Fontes padrão" description="Livres (OFL), sempre disponíveis no kit.">
        {padrao.isError && <ApiErrorAlert error={padrao.error} />}
        <ul className="divide-y" aria-label="Fontes padrão">
          {(padrao.data?.items ?? []).map((p) => (
            <li key={p.key} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3">
              <div className="w-56 shrink-0">
                <p className="font-semibold">{p.name}</p>
                <p className="text-xs text-muted-foreground">{p.family}</p>
              </div>
              <p className="min-w-0 flex-1 truncate text-2xl" style={{ fontFamily: fontStack(`padrao:${p.key}`, ready) }}>
                {SAMPLE_TEXT}
              </p>
            </li>
          ))}
        </ul>
      </HeaderCard>
    </Page>
  );
}

// 409 `font_in_use`: a mensagem da API mais os campos do kit que usam a fonte.
function FontErrorAlert({ error, onReload }: { error: unknown; onReload: () => void }) {
  const fields =
    error instanceof ApiError && error.code === "font_in_use" && Array.isArray(error.details.fields)
      ? (error.details.fields as unknown[]).filter((f): f is string => typeof f === "string")
      : [];
  return (
    <div className="space-y-1">
      <ApiErrorAlert error={error} onReload={onReload} />
      {fields.length > 0 && (
        <p className="text-sm text-destructive">Em uso em: {fields.map((f) => kitFieldText(normalizeKitField(f))).join(", ")}.</p>
      )}
    </div>
  );
}

function UploadFont({ perfilId, onUploaded }: { perfilId: string; onUploaded: (fonte: Fonte) => Promise<void> }) {
  const inputRef = useRef<HTMLInputElement>(null);
  // zerar o input pela ref exige trocar a key do FileField (o texto volta a "Nenhum arquivo escolhido")
  const [campoKey, setCampoKey] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function pick(f: File | null) {
    setFileError(null);
    setFile(null);
    if (!f) return;
    if (!/\.(ttf|otf)$/i.test(f.name)) return setFileError("Não é uma fonte TTF/OTF");
    if (f.size > MAX_BYTES) return setFileError("Arquivo maior que 10 MB");
    setFile(f);
    // Sugere o nome a partir do arquivo ("Pergaminho-Bold.ttf" → "Pergaminho Bold").
    if (!name.trim()) setName(f.name.replace(/\.(ttf|otf)$/i, "").replace(/[-_]+/g, " ").slice(0, 60));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const trimmed = name.trim();
    setNameError(trimmed.length < 1 || trimmed.length > 60 ? "Dê um nome de até 60 caracteres" : null);
    if (!file) setFileError("Escolha um arquivo TTF ou OTF");
    if (!file || trimmed.length < 1 || trimmed.length > 60) return;
    setBusy(true);
    try {
      const { fonte } = await api.fontes.upload(perfilId, file, trimmed);
      setFile(null);
      setName("");
      if (inputRef.current) inputRef.current.value = "";
      setCampoKey((k) => k + 1);
      await onUploaded(fonte);
    } catch (err) {
      if (err instanceof ApiError && err.status === 413) setFileError("Arquivo maior que 10 MB");
      else setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <HeaderCard title="Enviar fonte" description="TTF ou OTF, até 10 MB. O arquivo é conferido pelo conteúdo.">
      <form onSubmit={(e) => void submit(e)} className="grid items-start gap-4 sm:grid-cols-[1fr_1fr_auto]" noValidate>
        <Field label="Arquivo da fonte" error={fileError ?? undefined}>
          {({ id, describedBy, invalid }) => (
            <FileField
              key={campoKey}
              ref={inputRef}
              id={id}
              accept=".ttf,.otf,font/ttf,font/otf"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
          )}
        </Field>
        <Field label="Nome da fonte" error={nameError ?? undefined}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              value={name}
              maxLength={60}
              autoComplete="off"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" className="sm:mt-[1.375rem]" disabled={busy} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
          Enviar fonte
        </Button>
      </form>
      {error !== null && <ApiErrorAlert error={error} className="mt-4" />}
    </HeaderCard>
  );
}

function FontRow({
  fonte,
  family,
  onChanged,
  onError,
  onStart,
}: {
  fonte: Fonte;
  family: string;
  onChanged: () => Promise<void>;
  onError: (err: unknown) => void;
  onStart: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(fonte.name);
  const [busy, setBusy] = useState<"rename" | "archive" | null>(null);

  async function run(kind: "rename" | "archive", action: () => Promise<unknown>, done: string) {
    onStart();
    setBusy(kind);
    try {
      await action();
      toast.success(done);
      setEditing(false);
      await onChanged();
    } catch (err) {
      onError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3" aria-label={`Fonte ${fonte.name}`}>
      <div className="w-56 shrink-0">
        {editing ? (
          <form
            className="flex items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = name.trim();
              if (!trimmed || trimmed === fonte.name) return setEditing(false);
              void run("rename", () => api.fontes.rename(fonte.id, fonte.version, trimmed), "Fonte renomeada.");
            }}
          >
            <Input aria-label="Novo nome da fonte" value={name} maxLength={60} className="h-8" onChange={(e) => setName(e.target.value)} autoFocus />
            <Button type="submit" size="icon" variant="ghost" className="size-8" aria-label="Salvar nome" disabled={busy !== null}>
              {busy === "rename" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
            </Button>
            <Button type="button" size="icon" variant="ghost" className="size-8" aria-label="Cancelar" onClick={() => setEditing(false)}>
              <X aria-hidden="true" />
            </Button>
          </form>
        ) : (
          <p className="flex items-center gap-2 font-semibold">
            {fonte.name}
            {fonte.archived && <Badge className="bg-dark text-dark-foreground">Arquivada</Badge>}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {fonte.family} {fonte.style} · {fonte.format.toUpperCase()} · {formatBytes(fonte.bytes)}
        </p>
      </div>
      <p className="min-w-0 flex-1 truncate text-2xl" style={{ fontFamily: family }}>
        {SAMPLE_TEXT}
      </p>
      <div className="flex gap-2">
        {!editing && !fonte.archived && (
          <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
            <Pencil aria-hidden="true" />
            Renomear
          </Button>
        )}
        <ConfirmButton
          size="sm"
          label={fonte.archived ? "Restaurar" : "Arquivar"}
          icon={fonte.archived ? ArchiveRestore : Archive}
          busy={busy === "archive"}
          title={fonte.archived ? `Restaurar ${fonte.name}?` : `Arquivar ${fonte.name}?`}
          description={
            fonte.archived
              ? "A fonte volta para os seletores do kit."
              : "A fonte sai dos seletores do kit. O arquivo continua guardado e os cortes antigos não mudam."
          }
          onConfirm={() =>
            run(
              "archive",
              () => (fonte.archived ? api.fontes.restore(fonte.id, fonte.version) : api.fontes.archive(fonte.id, fonte.version)),
              fonte.archived ? "Fonte restaurada." : "Fonte arquivada.",
            )
          }
        />
      </div>
    </li>
  );
}
