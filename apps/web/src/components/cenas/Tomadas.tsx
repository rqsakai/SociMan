/*
 * Tomadas da cena (spec 010, US3; Q2 = A): o vídeo gerado à mão no Flow (MP4, MOV ou WebM, de 1 a
 * 30 s, até 200 MB), várias tentativas e uma escolhida (a miniatura da cena). Cada tomada guarda o
 * prompt com que foi gerada. Só cena pronta ou usada recebe tomada (o prompt precisa estar congelado).
 * Nada é apagado: arquivar e restaurar.
 */
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Check, ChevronDown, Loader2, Save, Star, TriangleAlert, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  
  formatSegundos,
  invalidarCena,
  LIM,
  TOMADA_ACCEPTED,
  TOMADA_MAX_BYTES,
  uploadTomada,
  useTomadas,
  type Cena,
  type Tomada,
} from "@/lib/cenas";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/marca";
import { formatDateTime } from "@/lib/tz";

export function Tomadas({ cena }: { cena: Cena }) {
  const queryClient = useQueryClient();
  const [arquivadas, setArquivadas] = useState(false);
  const tomadas = useTomadas(cena.id, arquivadas);
  const aceita = (cena.status === "pronta" || cena.status === "usada") && !cena.arquivada;
  const refresh = () => invalidarCena(queryClient, cena.id, cena.perfilId);

  return (
    <Card className="gap-3 shadow-card" aria-labelledby="tomadas-cena">
      <CardHeader>
        <CardTitle>
          <h2 id="tomadas-cena">Tomadas ({cena.tomadas})</h2>
        </CardTitle>
        <CardDescription>O vídeo gerado no Flow: de 1 a 30 s, MP4, MOV ou WebM, até 200 MB.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {aceita ? (
          <EnviarTomada cenaId={cena.id} onEnviada={refresh} />
        ) : (
          <p className="rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
            {cena.arquivada
              ? "Cena arquivada: restaure para enviar tomadas."
              : 'Marque a cena como pronta antes de enviar tomadas: o prompt precisa estar congelado para a tomada guardar com qual prompt foi gerada.'}
          </p>
        )}
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={arquivadas} onCheckedChange={setArquivadas} aria-label="Mostrar tomadas arquivadas" />
          Mostrar arquivadas
        </label>
        {tomadas.isError && <ApiErrorAlert error={tomadas.error} />}
        {tomadas.isPending && <p className="text-sm text-muted-foreground">Carregando…</p>}
        {tomadas.data && tomadas.data.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma tomada.</p>}
        {tomadas.data && tomadas.data.length > 0 && (
          <ul aria-label="Tomadas" className="space-y-4">
            {tomadas.data.map((t, i) => (
              <li key={t.id}>
                <TomadaItem tomada={t} numero={tomadas.data.length - i} cena={cena} onChanged={refresh} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function EnviarTomada({ cenaId, onEnviada }: { cenaId: string; onEnviada: () => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function pick(f: File | null) {
    setFileError(null);
    setFile(null);
    if (!f) return;
    if (!TOMADA_ACCEPTED.includes(f.type) && !/\.(mp4|mov|webm)$/i.test(f.name)) return setFileError("Não é um vídeo aceito (MP4, MOV ou WebM)");
    if (f.size > TOMADA_MAX_BYTES) return setFileError("Arquivo maior que 200 MB");
    setFile(f);
  }

  async function enviar() {
    if (!file) return;
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    setProgress(0);
    try {
      const t = await uploadTomada(cenaId, file, setProgress, controller.signal);
      if (t.naoVertical) toast.warning("Tomada enviada, mas não é vertical (9:16).");
      else toast.success("Tomada enviada.");
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      await onEnviada();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") toast.info("Envio cancelado; nada foi gravado.");
      else if (err instanceof ApiError && err.status === 413) setFileError("Arquivo maior que 200 MB");
      else if (err instanceof ApiError && (err.code === "invalid_video" || err.status === 415)) setFileError(err.message);
      else setError(err instanceof TypeError ? new ApiError(0, "internal_error", "Falha de rede no envio. Tente de novo.") : err);
    } finally {
      abortRef.current = null;
      setProgress(null);
    }
  }

  const enviando = progress !== null;
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <Field label="Nova tomada" error={fileError ?? undefined}>
        {({ id, describedBy, invalid }) => (
          <Input
            ref={inputRef}
            id={id}
            type="file"
            accept={TOMADA_ACCEPTED.join(",")}
            disabled={enviando}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
        )}
      </Field>
      {enviando && (
        <div className="space-y-1">
          <ProgressBar value={progress} label="Envio da tomada" />
          <p className="text-xs text-muted-foreground" aria-live="polite">
            Enviando… {Math.round(progress * 100)}%{file ? ` de ${formatBytes(file.size)}` : ""}
          </p>
        </div>
      )}
      {error !== null && <ApiErrorAlert error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" disabled={enviando || !file} aria-busy={enviando} onClick={() => void enviar()}>
          {enviando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
          Enviar tomada
        </Button>
        {enviando && (
          <Button type="button" size="sm" variant="ghost" onClick={() => abortRef.current?.abort()}>
            <X aria-hidden="true" />
            Cancelar envio
          </Button>
        )}
      </div>
    </div>
  );
}

function TomadaItem({ tomada: t, numero, cena, onChanged }: { tomada: Tomada; numero: number; cena: Cena; onChanged: () => Promise<void> }) {
  const [nota, setNota] = useState(t.nota);
  const [busy, setBusy] = useState<"escolher" | "nota" | "arquivo" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const nome = `Tomada ${numero}`;

  async function run(kind: NonNullable<typeof busy>, fn: () => Promise<unknown>, msg: string) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      toast.success(msg);
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <article aria-label={nome} className="space-y-2 rounded-lg border p-3">
      <header className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{nome}</span>
        {t.escolhida && (
          <Badge className="bg-primary text-primary-foreground">
            <Star aria-hidden="true" />
            Escolhida
          </Badge>
        )}
        {t.naoVertical && (
          <Badge className="bg-warning text-warning-foreground">
            <TriangleAlert aria-hidden="true" />
            não é vertical
          </Badge>
        )}
        {t.arquivada && <Badge className="bg-dark text-dark-foreground">Arquivada</Badge>}
        <time dateTime={t.createdAt} className="ml-auto text-xs text-muted-foreground">
          {formatDateTime(t.createdAt)}
        </time>
      </header>
      <div className="grid gap-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
        {t.videoUrl ? (
          <video
            controls
            playsInline
            preload="metadata"
            src={t.videoUrl}
            poster={t.thumbUrl ?? undefined}
            aria-label={`Vídeo da ${nome.toLowerCase()}`}
            className="mx-auto max-h-72 w-full rounded-md bg-black"
          />
        ) : t.thumbUrl ? (
          <img src={t.thumbUrl} alt="" className="mx-auto max-h-72 rounded-md" />
        ) : null}
        <div className="min-w-0 space-y-2 text-sm">
          <p className="text-muted-foreground">
            {formatSegundos(t.duracaoMs)} · {t.largura}×{t.altura} · {formatBytes(t.bytes)}
          </p>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run("nota", () => api.cenas.tomadaUpdate(t.id, t.version, nota.trim()), "Nota salva.");
            }}
          >
            <Field label={`Nota da ${nome.toLowerCase()}`} className="min-w-0 flex-1">
              {({ id }) => <Input id={id} value={nota} maxLength={LIM.nota} disabled={t.arquivada} onChange={(e) => setNota(e.target.value)} />}
            </Field>
            {!t.arquivada && nota !== t.nota && (
              <Button type="submit" size="sm" variant="outline" disabled={busy !== null} aria-busy={busy === "nota"}>
                <Save aria-hidden="true" />
                Salvar nota
              </Button>
            )}
          </form>
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="-ml-2">
                <ChevronDown aria-hidden="true" />
                Prompt usado
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-2">
              <pre className="max-h-48 overflow-y-auto rounded-md border bg-muted/40 p-2 font-mono text-xs break-words whitespace-pre-wrap">{t.promptUsado}</pre>
              <pre className="rounded-md border bg-muted/40 p-2 font-mono text-xs break-words whitespace-pre-wrap">Negative: {t.negativeUsado}</pre>
            </CollapsibleContent>
          </Collapsible>
          <div className="flex flex-wrap gap-2" role="group" aria-label={`Ações da ${nome.toLowerCase()}`}>
            {!t.escolhida && !t.arquivada && !cena.arquivada && (
              <Button
                type="button"
                size="sm"
                disabled={busy !== null}
                aria-busy={busy === "escolher"}
                onClick={() => void run("escolher", () => api.cenas.escolher(cena.id, t.id, cena.version), "Tomada escolhida.")}
              >
                {busy === "escolher" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
                Escolher
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy !== null}
              aria-busy={busy === "arquivo"}
              onClick={() =>
                void run(
                  "arquivo",
                  () => (t.arquivada ? api.cenas.tomadaRestore(t.id, t.version) : api.cenas.tomadaArchive(t.id, t.version)),
                  t.arquivada ? "Tomada restaurada." : "Tomada arquivada.",
                )
              }
            >
              {t.arquivada ? <ArchiveRestore aria-hidden="true" /> : <Archive aria-hidden="true" />}
              {t.arquivada ? "Restaurar" : "Arquivar"}
            </Button>
          </div>
        </div>
      </div>
      {error !== null && <ApiErrorAlert error={error} onReload={() => void onChanged()} />}
    </article>
  );
}
