import { ApiError, type Perfil } from "@sociman/contract";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, HardDrive, Loader2, Upload, X } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { HeaderCard } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { CorteStatusBadge, ProgressBar } from "../../../components/marca/CorteStatusBadge";
import { armazenamentoKey, cortesKey, formatBytes, type Armazenamento, type Corte } from "../../../lib/marca";
import { api } from "../../../lib/api";
import { uploadCorte } from "../../../lib/marcaApi";

const MAX_BYTES = 500 * 1024 * 1024;
const ACCEPTED = ["video/mp4", "video/quicktime", "video/webm"];
const PAGE = 50;
const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

const col = dataTableColumns<Corte>();
const columns = col.columns([
  col.accessor("createdAt", {
    header: "Data",
    enableGlobalFilter: false,
    cell: (c) => <time dateTime={c.getValue()}>{dateFormat.format(new Date(c.getValue()))}</time>,
    meta: { className: "whitespace-nowrap" },
  }),
  col.accessor("hookText", {
    header: "Gancho",
    cell: (c) => (
      <Link to={`/app/cortes/${c.row.original.id}`} className="line-clamp-2 font-semibold hover:underline">
        {c.getValue()}
      </Link>
    ),
  }),
  col.accessor((c) => c.createdBy?.name ?? "—", {
    id: "autor",
    header: "Autor",
    meta: { className: "hidden md:table-cell", headerClassName: "hidden md:table-cell" },
  }),
  col.accessor("kitVersion", {
    header: "Kit",
    cell: (c) => (c.getValue() === 0 ? "padrão" : `v${c.getValue()}`),
    meta: { className: "hidden sm:table-cell", headerClassName: "hidden sm:table-cell" },
  }),
  col.accessor("status", {
    header: "Status",
    cell: (c) => <CorteStatusBadge corte={c.row.original} />,
  }),
]);

const busyStatus = (c: Corte) => c.status === "na_fila" || c.status === "processando";

// Aba Cortes do perfil (US4, T027): uso do HD de dados, envio (arquivo + gancho, com barra de
// progresso) e a lista dos envios (data, autor, gancho, versão do kit, status). A lista se
// atualiza a cada 2 s enquanto houver corte na fila ou processando.
export function CortesTab({ perfil }: { perfil: Perfil }) {
  const storage = useQuery({ queryKey: armazenamentoKey, queryFn: () => api.armazenamento(), refetchInterval: 30_000 });
  const cortes = useInfiniteQuery({
    queryKey: cortesKey(perfil.id),
    queryFn: ({ pageParam }) => api.cortes.list(perfil.id, { limit: PAGE, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => (last.items.length === PAGE ? last.items[last.items.length - 1]?.createdAt : undefined),
    refetchInterval: (query) => (query.state.data?.pages.some((p) => p.items.some(busyStatus)) ? 2000 : false),
  });
  const rows = useMemo(() => cortes.data?.pages.flatMap((p) => p.items) ?? [], [cortes.data]);

  // flex + gap (e não space-y): o space-y zeraria o mt-6 do HeaderCard, e a faixa subiria sobre o
  // cartão de cima.
  return (
    <div className="flex flex-col gap-6">
      <StorageCard storage={storage.data} error={storage.error} />
      <CorteUpload perfil={perfil} storage={storage.data} />
      <HeaderCard title="Cortes enviados" description="Da mais recente para a mais antiga. Abra um corte para assistir e baixar.">
        {cortes.isError ? (
          <ApiErrorAlert error={cortes.error} />
        ) : (
          <DataTable
            label="Cortes"
            columns={columns}
            data={rows}
            loading={cortes.isPending}
            getRowId={(c) => c.id}
            initialSorting={[{ id: "createdAt", desc: true }]}
            emptyMessage="Nenhum corte enviado ainda."
            pagination={{
              hasMore: Boolean(cortes.hasNextPage),
              onLoadMore: () => void cortes.fetchNextPage(),
              loadingMore: cortes.isFetchingNextPage,
            }}
          />
        )}
      </HeaderCard>
    </div>
  );
}

const storageReason: Record<Armazenamento["reason"], string> = {
  ok: "",
  sem_sentinela: "O HD de dados não está disponível",
  pouco_espaco: "Pouco espaço no HD de dados",
};

function StorageCard({ storage, error }: { storage: Armazenamento | undefined; error: unknown }) {
  if (error) return <ApiErrorAlert error={error} />;
  if (!storage) return null;
  const used = storage.totalBytes !== null && storage.freeBytes !== null ? storage.totalBytes - storage.freeBytes : null;
  return (
    <div className="space-y-3">
      {!storage.available && (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{storageReason[storage.reason] || "O HD de dados não está disponível"}</AlertTitle>
          <AlertDescription>
            Envios de corte ficam desabilitados até o HD voltar
            {storage.reason === "pouco_espaco" ? ` (mínimo livre: ${formatBytes(storage.minFreeBytes)})` : ""}. Nada é apagado.
          </AlertDescription>
        </Alert>
      )}
      <section aria-label="HD de dados" className="flex flex-wrap items-center gap-4 rounded-xl bg-card p-4 shadow-card">
        <span className="tone-dark flex size-12 items-center justify-center rounded-lg" aria-hidden="true">
          <HardDrive className="size-6" />
        </span>
        <div className="min-w-48 flex-1 space-y-1.5">
          <p className="text-sm font-semibold">HD de dados</p>
          {used !== null && storage.totalBytes ? (
            <ProgressBar value={used / storage.totalBytes} label="Uso do HD de dados" />
          ) : (
            <p className="text-sm text-muted-foreground">Sem leitura do espaço.</p>
          )}
        </div>
        <dl className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">Livre</dt>
            <dd className="font-semibold">{formatBytes(storage.freeBytes)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Total</dt>
            <dd className="font-semibold">{formatBytes(storage.totalBytes)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Cortes</dt>
            <dd className="font-semibold">{formatBytes(storage.cortesBytes)}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

function CorteUpload({ perfil, storage }: { perfil: Perfil; storage: Armazenamento | undefined }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [hookText, setHookText] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [hookError, setHookError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState<number | null>(null);

  const unavailable = storage !== undefined && !storage.available;
  const disabled = unavailable || perfil.archived || progress !== null;

  function pick(f: File | null) {
    setFileError(null);
    setFile(null);
    if (!f) return;
    if (!ACCEPTED.includes(f.type) && !/\.(mp4|mov|webm)$/i.test(f.name)) return setFileError("Não é um vídeo aceito");
    if (f.size > MAX_BYTES) return setFileError("Arquivo maior que 500 MB");
    setFile(f);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const text = hookText.trim();
    const lines = text.split("\n").length;
    const hookProblem = !text ? "Escreva o texto do gancho" : text.length > 120 || lines > 3 ? "Gancho longo demais" : null;
    setHookError(hookProblem);
    if (!file) setFileError("Escolha o vídeo");
    if (!file || hookProblem) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setProgress(0);
    try {
      const { corte } = await uploadCorte(perfil.id, file, text, setProgress, controller.signal);
      toast.success("Corte na fila. Acompanhe o status na lista.");
      setFile(null);
      setHookText("");
      if (inputRef.current) inputRef.current.value = "";
      await queryClient.invalidateQueries({ queryKey: cortesKey(perfil.id) });
      void navigate(`/app/cortes/${corte.id}`);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") toast.info("Envio cancelado; nada entrou na fila.");
      else if (err instanceof ApiError && err.status === 413) setFileError("Arquivo maior que 500 MB");
      else if (err instanceof ApiError && err.code === "invalid_hook") setHookError(err.message);
      else if (err instanceof ApiError && err.code === "invalid_video") setFileError(err.message);
      else setError(err instanceof TypeError ? new ApiError(0, "internal_error", "Falha de rede no envio. Tente de novo.") : err);
    } finally {
      abortRef.current = null;
      setProgress(null);
    }
  }

  return (
    <HeaderCard
      title="Aplicar marca num corte"
      tone="info"
      description="Vídeo MP4, MOV ou WebM, até 500 MB e 3 minutos, já com legenda. O kit vigente no envio fica registrado."
    >
      <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Vídeo do corte" error={fileError ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <Input
                ref={inputRef}
                id={id}
                type="file"
                accept={ACCEPTED.join(",")}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
            )}
          </Field>
          <Field label="Texto do gancho" error={hookError ?? undefined} hint={`${hookText.trim().length}/120; até 3 linhas.`}>
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={3}
                maxLength={120}
                value={hookText}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setHookText(e.target.value)}
              />
            )}
          </Field>
        </div>
        {progress !== null && (
          <div className="space-y-1">
            <ProgressBar value={progress} label="Envio do vídeo" />
            <p className="text-xs text-muted-foreground" aria-live="polite">
              Enviando… {Math.round(progress * 100)}%{file ? ` de ${formatBytes(file.size)}` : ""}
            </p>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={disabled} aria-busy={progress !== null}>
            {progress !== null ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
            Enviar corte
          </Button>
          {progress !== null && (
            <Button type="button" variant="ghost" onClick={() => abortRef.current?.abort()}>
              <X aria-hidden="true" />
              Cancelar envio
            </Button>
          )}
          {unavailable && <p className="text-sm text-destructive">Envio desabilitado: {storageReason[storage.reason] || "HD indisponível"}.</p>}
          {perfil.archived && <p className="text-sm text-muted-foreground">Perfil arquivado: restaure para enviar cortes.</p>}
        </div>
        {error !== null && <ApiErrorAlert error={error} />}
      </form>
    </HeaderCard>
  );
}
