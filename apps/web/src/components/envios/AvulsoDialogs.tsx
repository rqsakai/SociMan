/*
 * Envio avulso (spec 006, US2-5; FR-007): vídeo de outro lugar entra nos "Selecionados" do perfil.
 *
 * <ColarLinkDialog open onOpenChange perfilId onCreated />   link (YouTube ou outro) + título opcional
 * <EnviarArquivoDialog open onOpenChange perfilId onCreated /> arquivo de até 2 GB, 45 s a 3 h, com
 *                                                               barra de progresso e cancelar
 * Avulso sempre mostra o aviso de direito na hora de enviar para corte (princípio II).
 */
import { ApiError } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Loader2, ShieldAlert, Upload, X } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { ARQUIVO_ACEITO, MAX_ARQUIVO_BYTES, uploadEnvioArquivo, type Envio } from "@/lib/envios";
import { armazenamentoKey, formatBytes } from "@/lib/marca";
import { AVISO_DIREITO } from "./AvisoDireito";

function AvisoAvulso() {
  return (
    <Alert>
      <ShieldAlert aria-hidden="true" />
      <AlertTitle>{AVISO_DIREITO}</AlertTitle>
      <AlertDescription>Vídeo avulso não tem status de direito: o envio para corte pede sua confirmação e fica no histórico.</AlertDescription>
    </Alert>
  );
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  perfilId: string;
  onCreated?: (envio: Envio) => void;
}

export function ColarLinkDialog({ open, onOpenChange, perfilId, onCreated }: Props) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [titulo, setTitulo] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const u = url.trim();
    if (!/^https?:\/\/\S+$/i.test(u)) return setUrlError("Cole um link http(s)");
    setUrlError(null);
    setBusy(true);
    try {
      const { envio } = await api.envios.selecionar(perfilId, { url: u, titulo: titulo.trim() || undefined });
      toast.success("Vídeo avulso nos selecionados.");
      await queryClient.invalidateQueries({ queryKey: ["envios"] });
      setUrl("");
      setTitulo("");
      onOpenChange(false);
      onCreated?.(envio);
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_url") setUrlError(err.message);
      else if (err instanceof ApiError && (err.code === "already_selected" || err.code === "already_sent")) setUrlError(err.message);
      else setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Colar link</DialogTitle>
          <DialogDescription>Um vídeo do YouTube ou de outro lugar, fora dos canais-fonte.</DialogDescription>
        </DialogHeader>
        <form id="colar-link" onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
          <Field label="Link do vídeo" error={urlError ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} type="url" autoFocus value={url} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setUrl(e.target.value)} />
            )}
          </Field>
          <Field label="Título (opcional)">
            {({ id }) => <Input id={id} maxLength={200} value={titulo} onChange={(e) => setTitulo(e.target.value)} />}
          </Field>
          <AvisoAvulso />
          {error !== null && <ApiErrorAlert error={error} />}
        </form>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" form="colar-link" disabled={busy} aria-busy={busy}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Link2 aria-hidden="true" />}
            Adicionar aos selecionados
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EnviarArquivoDialog({ open, onOpenChange, perfilId, onCreated }: Props) {
  const queryClient = useQueryClient();
  const storage = useQuery({ queryKey: armazenamentoKey, queryFn: () => api.armazenamento(), enabled: open });
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const unavailable = storage.data !== undefined && !storage.data.available;

  function pick(f: File | null) {
    setFileError(null);
    setFile(null);
    if (!f) return;
    if (!ARQUIVO_ACEITO.includes(f.type) && !/\.(mp4|mov|webm|mkv)$/i.test(f.name)) return setFileError("Não é um vídeo aceito");
    if (f.size > MAX_ARQUIVO_BYTES) return setFileError("Arquivo maior que 2 GB");
    setFile(f);
    if (!titulo) setTitulo(f.name.replace(/\.[^.]+$/, "").slice(0, 200));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file) return setFileError("Escolha o vídeo");
    const controller = new AbortController();
    abortRef.current = controller;
    setProgress(0);
    try {
      const { envio } = await uploadEnvioArquivo(perfilId, file, titulo.trim() || file.name, setProgress, controller.signal);
      toast.success("Arquivo nos selecionados.");
      await queryClient.invalidateQueries({ queryKey: ["envios"] });
      setFile(null);
      setTitulo("");
      if (inputRef.current) inputRef.current.value = "";
      onOpenChange(false);
      onCreated?.(envio);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") toast.info("Envio cancelado.");
      else if (err instanceof ApiError && err.status === 413) setFileError("Arquivo maior que 2 GB");
      else if (err instanceof ApiError && err.code === "invalid_video") setFileError(err.message);
      else setError(err instanceof TypeError ? new ApiError(0, "internal_error", "Falha de rede no envio. Tente de novo.") : err);
    } finally {
      abortRef.current = null;
      setProgress(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => progress === null && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Enviar arquivo</DialogTitle>
          <DialogDescription>MP4, MOV, WebM ou MKV, até 2 GB, de 45 segundos a 3 horas. Fica guardado no HD de dados.</DialogDescription>
        </DialogHeader>
        <form id="enviar-arquivo" onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
          <Field label="Arquivo de vídeo" error={fileError ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <Input
                ref={inputRef}
                id={id}
                type="file"
                accept={ARQUIVO_ACEITO.join(",")}
                disabled={progress !== null || unavailable}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
            )}
          </Field>
          <Field label="Título">
            {({ id }) => <Input id={id} maxLength={200} value={titulo} disabled={progress !== null} onChange={(e) => setTitulo(e.target.value)} />}
          </Field>
          {progress !== null && (
            <div className="space-y-1">
              <ProgressBar value={progress} label="Envio do arquivo" />
              <p className="text-xs text-muted-foreground" aria-live="polite">
                Enviando… {Math.round(progress * 100)}%{file ? ` de ${formatBytes(file.size)}` : ""}
              </p>
            </div>
          )}
          {unavailable && <p className="text-sm text-destructive">O HD de dados não está disponível: o envio fica desabilitado.</p>}
          <AvisoAvulso />
          {error !== null && <ApiErrorAlert error={error} />}
        </form>
        <DialogFooter>
          {progress !== null ? (
            <Button type="button" variant="ghost" onClick={() => abortRef.current?.abort()}>
              <X aria-hidden="true" />
              Cancelar envio
            </Button>
          ) : (
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
          )}
          <Button type="submit" form="enviar-arquivo" disabled={progress !== null || unavailable} aria-busy={progress !== null}>
            {progress !== null ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
            Enviar arquivo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
