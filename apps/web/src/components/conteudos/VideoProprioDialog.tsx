/*
 * "Enviar vídeo próprio" (spec 014, US5; Q4 = A): um vídeo já pronto (MP4, MOV ou WebM, de 1 s a
 * 10 min, até 2 GB, qualquer proporção) entra em Conteúdos como "Vídeo próprio", pronto para
 * aprovar e agendar. Vídeo que não é vertical entra com o aviso "não é vertical".
 * Envio por XHR, com a barra de progresso e "Cancelar envio".
 */
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { Input } from "@/components/ui/input";
import { invalidarConteudos } from "@/lib/conteudos";
import { formatBytes } from "@/lib/marca";
import { uploadVideoProprio } from "@/lib/marcaApi";
import { TITULO_MAX } from "@/lib/postagem";
import { usePerfisAtivos } from "@/lib/usePerfis";

const MAX_BYTES = 2 * 1024 ** 3;
const ACCEPTED = ["video/mp4", "video/quicktime", "video/webm"];

export function VideoProprioDialog({
  open,
  onOpenChange,
  perfilId: perfilFixo,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Na aba do perfil o perfil vem fixo; em Conteúdos, escolhe-se.
  perfilId?: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const perfis = usePerfisAtivos();
  const [perfilId, setPerfilId] = useState(perfilFixo ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!open) return;
    setPerfilId(perfilFixo ?? "");
    setFile(null);
    setTitulo("");
    setFileError(null);
    setError(null);
  }, [open, perfilFixo]);

  function pick(f: File | null) {
    setFileError(null);
    setFile(null);
    if (!f) return;
    if (!ACCEPTED.includes(f.type) && !/\.(mp4|mov|webm)$/i.test(f.name)) return setFileError("Não é um vídeo aceito (MP4, MOV ou WebM)");
    if (f.size > MAX_BYTES) return setFileError("Arquivo maior que 2 GB");
    setFile(f);
    if (!titulo) setTitulo(f.name.replace(/\.[^.]+$/, "").slice(0, TITULO_MAX));
  }

  async function enviar() {
    setError(null);
    if (!perfilId) return setError(new ApiError(400, "validation_error", "Escolha o perfil."));
    if (!file) return setFileError("Escolha o vídeo");
    const controller = new AbortController();
    abortRef.current = controller;
    setProgress(0);
    try {
      const { conteudo } = await uploadVideoProprio(perfilId, file, titulo, setProgress, controller.signal);
      if (conteudo.naoVertical) toast.warning("Vídeo enviado, mas não é vertical: confira antes de agendar.");
      else toast.success("Vídeo próprio pronto para aprovar e agendar.");
      await invalidarConteudos(queryClient);
      onOpenChange(false);
      void navigate(`/app/conteudos/${conteudo.id}`);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") toast.info("Envio cancelado; nada foi criado.");
      else if (err instanceof ApiError && err.status === 413) setFileError("Arquivo maior que 2 GB");
      else if (err instanceof ApiError && err.code === "invalid_video") setFileError(err.message);
      else setError(err instanceof TypeError ? new ApiError(0, "internal_error", "Falha de rede no envio. Tente de novo.") : err);
    } finally {
      abortRef.current = null;
      setProgress(null);
    }
  }

  const enviando = progress !== null;

  return (
    <Dialog open={open} onOpenChange={(o) => !enviando && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Enviar vídeo próprio</DialogTitle>
          <DialogDescription>Vídeo já pronto: MP4, MOV ou WebM, de 1 s a 10 min, até 2 GB. Entra em Conteúdos como pronto.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {!perfilFixo && (
            <Field label="Perfil">
              {({ id }) => (
                <NativeSelect id={id} value={perfilId} disabled={enviando} onChange={(e) => setPerfilId(e.target.value)}>
                  <option value="">Escolha o perfil…</option>
                  {perfis.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          )}
          <Field label="Vídeo" error={fileError ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <FileField
                id={id}
                accept={ACCEPTED.join(",")}
                disabled={enviando}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
            )}
          </Field>
          <Field label="Título" hint={`${titulo.length}/${TITULO_MAX}`}>
            {({ id, describedBy }) => (
              <Input id={id} value={titulo} maxLength={TITULO_MAX} disabled={enviando} aria-describedby={describedBy} onChange={(e) => setTitulo(e.target.value)} />
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
          {error !== null && <ApiErrorAlert error={error} />}
        </div>
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
          <Button type="button" disabled={enviando || !file || !perfilId} aria-busy={enviando} onClick={() => void enviar()}>
            {enviando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
            Enviar vídeo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
