/*
 * /app/assistente-ia/regras/:tipo (spec 008, US2): as regras (system prompt) em vigor de um tipo de
 * campo, o padrão do SociMan para comparar e o histórico. O dono edita (≤ 8.000), volta ao padrão e
 * reverte; o membro só lê. A base fixa (formato, limites, segurança) não aparece nem é editável.
 */
import type { TipoCampo, TipoCampoId } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, RotateCcw, Save } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { usePageMeta } from "@/components/shell";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/authStore";
import { formatoLabel, iaTipoVersionsKey, iaTiposKey, idiomaLabel, REGRAS_MAX } from "../../lib/ia";
import { formatDateTime } from "../../lib/tz";

const regraKey = (tipo: string) => ["ia-tipo", tipo] as const;
const regraFieldLabel: Record<string, string> = { texto: "Regras", tipo_campo: "Tipo de campo" };

export default function RegraDetalhe() {
  const { tipo = "" } = useParams();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: regraKey(tipo), queryFn: () => api.ia.tipo(tipo as TipoCampoId) });
  const info = detail.data?.tipo;
  usePageMeta({ title: info?.rotulo ?? "Regras", breadcrumbs: [{ label: "Assistente de IA", to: "/app/assistente-ia" }] });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: regraKey(tipo) }),
      queryClient.invalidateQueries({ queryKey: iaTiposKey }),
      queryClient.invalidateQueries({ queryKey: iaTipoVersionsKey(tipo) }),
    ]);
  }

  return (
    <div className="space-y-6">
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to="/app/assistente-ia">
          <ArrowLeft aria-hidden="true" />
          Assistente de IA
        </Link>
      </Button>
      {detail.isPending && <Skeleton className="h-64 w-full rounded-xl" />}
      {detail.isError && <ApiErrorAlert error={detail.error} />}
      {info && (
        <>
          <RegraCard key={`${info.id}-${info.regras.version}`} info={info} onChanged={refresh} />
          <Historico info={info} onChanged={refresh} />
        </>
      )}
    </div>
  );
}

function RegraCard({ info, onChanged }: { info: TipoCampo; onChanged: () => Promise<void> }) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const { regras } = info;
  const [texto, setTexto] = useState(regras.texto);
  const [busy, setBusy] = useState<"salvar" | "padrao" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const over = texto.length > REGRAS_MAX;
  const vazio = texto.trim().length === 0;
  const dirty = texto !== regras.texto;

  async function salvar() {
    setError(null);
    setBusy("salvar");
    try {
      await api.ia.updateRegras(info.id, { version: regras.version, texto });
      toast.success("Regras salvas. As próximas gerações já usam o texto novo.");
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function voltarAoPadrao() {
    setError(null);
    setBusy("padrao");
    try {
      await api.ia.padrao(info.id, regras.version);
      toast.success("As regras voltaram ao padrão do SociMan.");
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h1 className="text-xl font-bold">{info.rotulo}</h1>
        </CardTitle>
        <CardDescription className="space-y-1">
          <span className="block">{info.onde}</span>
          <span className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline">{idiomaLabel[info.idioma]}</Badge>
            <Badge variant="outline">{formatoLabel[info.formato]}</Badge>
            {regras.personalizada ? <Badge className="bg-info text-info-foreground">Personalizada</Badge> : <Badge variant="secondary">Padrão</Badge>}
            {regras.updatedAt && (
              <span className="text-xs">
                {regras.updatedBy?.name ?? "—"} · {formatDateTime(regras.updatedAt)}
              </span>
            )}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {regras.padraoAtualizado && (
          <Alert>
            <AlertTitle>O padrão mudou desde a sua edição</AlertTitle>
            <AlertDescription>O SociMan trouxe regras padrão novas para este tipo. Compare abaixo e, se quiser, volte ao padrão.</AlertDescription>
          </Alert>
        )}
        {isOwner ? (
          <Field
            label="Regras em vigor"
            error={over ? `Até ${REGRAS_MAX.toLocaleString("pt-BR")} caracteres` : vazio ? "Escreva as regras ou volte ao padrão" : undefined}
            hint={
              <span className="flex flex-wrap justify-between gap-2">
                <span>Formato, limites do campo e segurança valem sempre e não entram aqui.</span>
                <span aria-live="polite" className={over ? "text-destructive" : undefined}>
                  {texto.length.toLocaleString("pt-BR")}/{REGRAS_MAX.toLocaleString("pt-BR")}
                </span>
              </span>
            }
          >
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={12}
                value={texto}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                className="font-mono text-sm"
                onChange={(e) => setTexto(e.target.value)}
              />
            )}
          </Field>
        ) : (
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Regras em vigor</p>
            <pre className="rounded-md border bg-muted/40 p-3 font-mono text-sm break-words whitespace-pre-wrap">{regras.texto}</pre>
            <p className="text-xs text-muted-foreground">Só o dono edita as regras.</p>
          </div>
        )}

        {error !== null && <ApiErrorAlert error={error} onReload={() => void onChanged()} />}

        {isOwner && (
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={busy !== null || !dirty || over || vazio} aria-busy={busy === "salvar"} onClick={() => void salvar()}>
              {busy === "salvar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar regras
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="outline" disabled={busy !== null || !regras.personalizada} aria-busy={busy === "padrao"}>
                  {busy === "padrao" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
                  Voltar ao padrão
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Voltar ao padrão?</AlertDialogTitle>
                  <AlertDialogDescription>
                    As regras de “{info.rotulo}” voltam ao texto que vem com o SociMan. A mudança entra no histórico e pode ser revertida.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction onClick={() => void voltarAoPadrao()}>Voltar ao padrão</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}

        {regras.personalizada && (
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">Padrão do SociMan (para comparar)</summary>
            <pre className="mt-2 font-mono text-sm break-words whitespace-pre-wrap text-muted-foreground">{regras.padrao}</pre>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function Historico({ info, onChanged }: { info: TipoCampo; onChanged: () => Promise<void> }) {
  const versions = useQuery({ queryKey: iaTipoVersionsKey(info.id), queryFn: () => api.ia.versions(info.id) });
  return (
    <Card className="shadow-card">
      <CardHeader>
        <HistoryHeading>Histórico das regras</HistoryHeading>
        <CardDescription>Da versão mais recente para a mais antiga. Reverter cria uma versão nova; nada é apagado.</CardDescription>
      </CardHeader>
      <CardContent>
        {versions.isPending && <p className="text-sm text-muted-foreground">Carregando…</p>}
        {versions.isError && <ApiErrorAlert error={versions.error} />}
        {versions.data && (
          <VersionHistory
            versions={versions.data.items}
            labels={regraFieldLabel}
            formatValue={(_field, value) => (value === null || value === undefined || value === "" ? "(padrão do SociMan)" : String(value))}
            onRevert={async (toVersion) => {
              await api.ia.revert(info.id, info.regras.version, toVersion);
              await onChanged();
            }}
            onReload={onChanged}
          />
        )}
      </CardContent>
    </Card>
  );
}
