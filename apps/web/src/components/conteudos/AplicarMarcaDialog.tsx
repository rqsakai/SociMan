/*
 * "Aplicar marca num corte" (spec 024, US3; R11): o envio que morava na aba Cortes do perfil.
 * Perfil (pré-escolhido pelo filtro de Conteúdos ou pelo único perfil), o estado do HD de dados
 * (lido só com o diálogo aberto; HD indisponível bloqueia o envio), o vídeo e o texto do gancho.
 * Envio por XHR (`uploadCorte`), com barra de progresso e "Cancelar envio". Ao concluir, o corte
 * entra na fila e a tela vai para o detalhe dele.
 *
 * Props:
 *   open, onOpenChange      controle do diálogo
 *   perfilId?: string|null  perfil pré-escolhido (ex.: o filtro `perfil` da URL)
 */
import { ApiError } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, HardDrive, Loader2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { invalidarConteudos } from "@/lib/conteudos";
import { armazenamentoKey, cortesKey, formatBytes, type Armazenamento } from "@/lib/marca";
import { uploadCorte } from "@/lib/marcaApi";
import { usePerfisAtivos } from "@/lib/usePerfis";

const MAX_BYTES = 500 * 1024 * 1024;
const ACCEPTED = ["video/mp4", "video/quicktime", "video/webm"];

const storageReason: Record<Armazenamento["reason"], string> = {
  ok: "",
  sem_sentinela: "O HD de dados não está disponível",
  pouco_espaco: "Pouco espaço no HD de dados",
};

export function AplicarMarcaDialog({
  open,
  onOpenChange,
  perfilId: perfilInicial,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  perfilId?: string | null;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const perfis = usePerfisAtivos();
  const storage = useQuery({ queryKey: armazenamentoKey, queryFn: () => api.armazenamento(), enabled: open, refetchInterval: open ? 30_000 : false });
  const abortRef = useRef<AbortController | null>(null);
  const [perfilId, setPerfilId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [hookText, setHookText] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [hookError, setHookError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setHookText("");
    setFileError(null);
    setHookError(null);
    setError(null);
  }, [open]);

  // perfil pré-escolhido: o do filtro (se ativo) ou o único perfil
  const lista = perfis.data;
  useEffect(() => {
    if (!open || !lista) return;
    const doFiltro = perfilInicial && lista.some((p) => p.id === perfilInicial) ? perfilInicial : "";
    setPerfilId(doFiltro || (lista.length === 1 ? lista[0]!.id : ""));
  }, [open, perfilInicial, lista]);

  const unavailable = storage.data !== undefined && !storage.data.available;
  const enviando = progress !== null;
  const disabled = unavailable || enviando;

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
    if (!perfilId) return setError(new ApiError(400, "validation_error", "Escolha o perfil."));
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
      const { corte } = await uploadCorte(perfilId, file, text, setProgress, controller.signal);
      toast.success("Corte na fila. Acompanhe o status no detalhe.");
      await Promise.all([invalidarConteudos(queryClient), queryClient.invalidateQueries({ queryKey: cortesKey(perfilId) })]);
      onOpenChange(false);
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
    <Dialog open={open} onOpenChange={(o) => !enviando && onOpenChange(o)}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Aplicar marca num corte</DialogTitle>
          <DialogDescription>
            Vídeo MP4, MOV ou WebM, até 500 MB e 3 minutos, já com legenda. O kit vigente no envio fica registrado.
          </DialogDescription>
        </DialogHeader>
        <form id="aplicar-marca" onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
          <EstadoHd storage={storage.data} error={storage.error} />
          <Field label="Perfil">
            {({ id }) => (
              <NativeSelect id={id} value={perfilId} disabled={enviando} onChange={(e) => setPerfilId(e.target.value)}>
                <option value="">Escolha o perfil…</option>
                {lista?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Vídeo do corte" error={fileError ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <FileField
                id={id}
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
          {enviando && (
            <div className="space-y-1">
              <ProgressBar value={progress} label="Envio do vídeo" />
              <p className="text-xs text-muted-foreground" aria-live="polite">
                Enviando… {Math.round(progress * 100)}%{file ? ` de ${formatBytes(file.size)}` : ""}
              </p>
            </div>
          )}
          {unavailable && (
            <p className="text-sm text-destructive">Envio desabilitado: {storageReason[storage.data!.reason] || "HD indisponível"}.</p>
          )}
          {error !== null && <ApiErrorAlert error={error} />}
        </form>
        <DialogFooter>
          {enviando ? (
            <Button type="button" variant="ghost" onClick={() => abortRef.current?.abort()}>
              <X aria-hidden="true" />
              Cancelar envio
            </Button>
          ) : (
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
          )}
          <Button type="submit" form="aplicar-marca" disabled={disabled || !perfilId} aria-busy={enviando}>
            {enviando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
            Enviar corte
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Estado do HD de dados: alerta quando indisponível e o uso (livre, total, cortes).
function EstadoHd({ storage, error }: { storage: Armazenamento | undefined; error: unknown }) {
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
      <section aria-label="HD de dados" className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
        <HardDrive className="size-5 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-40 flex-1 space-y-1.5">
          <p className="text-sm font-semibold">HD de dados</p>
          {used !== null && storage.totalBytes ? (
            <ProgressBar value={used / storage.totalBytes} label="Uso do HD de dados" />
          ) : (
            <p className="text-sm text-muted-foreground">Sem leitura do espaço.</p>
          )}
        </div>
        <dl className="grid grid-cols-3 gap-3 text-sm">
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
