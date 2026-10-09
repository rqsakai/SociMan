import { Loader2, ShieldOff } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { PreviaRevogacao } from "@/lib/padrao";

const fmtBytes = (b: number) =>
  b >= 1024 * 1024 ? `${(b / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB` : `${Math.round(b / 1024).toLocaleString("pt-BR")} KB`;

function lista(itens: Record<string, unknown>[]): { id: string; nome: string }[] {
  return itens.flatMap((i) => (typeof i.id === "string" ? [{ id: i.id, nome: typeof i.titulo === "string" ? i.titulo : typeof i.name === "string" ? i.name : i.id }] : []));
}

// "Revogar consentimento" (spec 025, US3, T036; FR-033a, research R10): só o dono. A confirmação
// mostra o que será apagado (contagens e tamanho) e as cenas afetadas, pede "Entendi" e só então
// revoga. Sem `carregarPrevia` (voz), a confirmação descreve o efeito sem as contagens.
export function RevogarDialog({ carregarPrevia, onRevogar }: { carregarPrevia?: () => Promise<PreviaRevogacao>; onRevogar: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [previa, setPrevia] = useState<PreviaRevogacao | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [entendi, setEntendi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function abrir(o: boolean) {
    if (busy) return;
    setOpen(o);
    if (!o) return;
    setEntendi(false);
    setError(null);
    setPrevia(null);
    if (carregarPrevia) {
      setCarregando(true);
      try {
        setPrevia(await carregarPrevia());
      } catch (err) {
        setError(err);
      } finally {
        setCarregando(false);
      }
    }
  }

  async function revogar() {
    setBusy(true);
    setError(null);
    try {
      await onRevogar();
      setOpen(false);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const cenas = previa ? lista(previa.cenasAfetadas) : [];
  const avatares = previa?.avataresAfetados ? lista(previa.avataresAfetados) : [];

  return (
    <AlertDialog open={open} onOpenChange={(o) => void abrir(o)}>
      <AlertDialogTrigger asChild>
        <Button type="button" variant="outline" className="border-destructive/60 text-destructive">
          <ShieldOff aria-hidden="true" />
          Revogar consentimento
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Revogar o consentimento?</AlertDialogTitle>
          <AlertDialogDescription>
            Não tem volta: as imagens e áudios da pessoa são apagados do HD, as opções geradas a partir deles também, o item é arquivado e
            não pode mais ser restaurado. O histórico fica, com os dados pessoais redigidos.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {carregando && (
          <p aria-live="polite" className="text-sm text-muted-foreground">
            Calculando o que será apagado…
          </p>
        )}
        {previa && (
          <div className="space-y-2 text-sm" data-testid="previa-revogacao">
            <ul className="list-disc space-y-0.5 pl-5">
              <li>{previa.imagens} imagens</li>
              <li>{previa.audios} áudios</li>
              <li>{previa.candidatos} opções geradas</li>
              <li>{previa.geracoes} gerações</li>
              <li>{fmtBytes(previa.bytes)} no HD</li>
            </ul>
            {cenas.length > 0 && (
              <div>
                <p className="font-medium">Cenas afetadas (o avatar some delas):</p>
                <ul className="list-disc pl-5">
                  {cenas.map((c) => (
                    <li key={c.id}>
                      <Link to={`/app/cenas/${c.id}`} className="underline-offset-2 hover:underline">
                        {c.nome}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {avatares.length > 0 && <p>Avatares que usam esta voz: {avatares.map((a) => a.nome).join(", ")}.</p>}
          </div>
        )}
        <label className="flex items-start gap-2 text-sm">
          <Checkbox checked={entendi} onCheckedChange={(v) => setEntendi(v === true)} className="mt-0.5" />
          Entendi o que será apagado
        </label>
        {error !== null && <ApiErrorAlert error={error} />}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            disabled={!entendi || busy || carregando}
            onClick={(e) => {
              e.preventDefault();
              void revogar();
            }}
          >
            {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
            Revogar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
