/*
 * Exportar o dataset de métricas (spec 016, US5; R16). Só o dono.
 *
 * <ExportarDialog open onOpenChange perfilId? contaId? />
 *   Período das fotos (até 400 dias), perfil, conta, formato (CSV ou JSON Lines) e "incluir contas
 *   anônimas". O download é por fetch com o Bearer, salvo como Blob (sem link público): um ZIP com
 *   as fotos dos vídeos, os vídeos com as características do SociMan, as fotos da conta, o
 *   dicionário das colunas e um LEIAME.
 */
import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { addDays, localDateKey, parseDateKey } from "@/lib/tz";
import { FiltroContas } from "./FiltroContas";

const MAX_DIAS = 400;

function dias(de: string, ate: string): number {
  const a = parseDateKey(de);
  const b = parseDateKey(ate);
  return Math.round((Date.UTC(b.year, b.month - 1, b.day) - Date.UTC(a.year, a.month - 1, a.day)) / 86_400_000) + 1;
}

export function ExportarDialog({
  open,
  onOpenChange,
  perfilId: perfilInicial = "",
  contaId: contaInicial = "",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  perfilId?: string;
  contaId?: string;
}) {
  const hoje = localDateKey(new Date());
  const [de, setDe] = useState(addDays(hoje, -29));
  const [ate, setAte] = useState(hoje);
  const [filtro, setFiltro] = useState({ perfil: perfilInicial, conta: contaInicial });
  const [formato, setFormato] = useState<"csv" | "jsonl">("csv");
  const [incluirAnonimas, setIncluirAnonimas] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const n = de && ate ? dias(de, ate) : 0;
  const periodoErro = !de || !ate ? "Escolha o início e o fim" : n < 1 ? "O início é depois do fim" : n > MAX_DIAS ? `Escolha um período de até ${MAX_DIAS} dias` : undefined;

  async function exportar() {
    if (periodoErro) return;
    setError(null);
    setBusy(true);
    try {
      const { blob, filename } = await api.metricas.exportFile({
        formato,
        de,
        ate,
        ...(filtro.perfil ? { perfilId: filtro.perfil } : {}),
        ...(filtro.conta ? { contaId: filtro.conta } : {}),
        incluirAnonimas,
      });
      // <a download> com object URL: é download, não carga de recurso, então a CSP não interfere.
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      toast.success(`Métricas exportadas: ${filename}`);
      onOpenChange(false);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Exportar métricas</DialogTitle>
          <DialogDescription>
            Um ZIP com uma linha por foto de vídeo, os vídeos com as características do SociMan (gancho, canal-fonte, nota, horário…), as fotos da conta e o
            dicionário das colunas. Vídeos sem vínculo vêm com as colunas do SociMan vazias.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Período das fotos</legend>
            <div className="flex flex-wrap items-center gap-1.5">
              <Input type="date" aria-label="Exportar de" value={de} max={hoje} aria-invalid={Boolean(periodoErro)} onChange={(e) => setDe(e.target.value)} className="w-auto" />
              <span className="text-sm text-muted-foreground">a</span>
              <Input type="date" aria-label="Exportar até" value={ate} max={hoje} aria-invalid={Boolean(periodoErro)} onChange={(e) => setAte(e.target.value)} className="w-auto" />
            </div>
            {periodoErro ? (
              <p role="alert" className="text-xs text-destructive">
                {periodoErro}.
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">{n === 1 ? "1 dia" : `${n} dias`} (até {MAX_DIAS}).</p>
            )}
          </fieldset>
          <div className="flex flex-wrap items-end gap-3">
            <FiltroContas perfilId={filtro.perfil} contaId={filtro.conta} set={(p) => setFiltro((cur) => ({ perfil: "perfil" in p ? (p.perfil ?? "") : cur.perfil, conta: "conta" in p ? (p.conta ?? "") : cur.conta }))} />
          </div>
          <Field label="Formato">
            {({ id }) => (
              <NativeSelect id={id} value={formato} onChange={(e) => setFormato(e.target.value as "csv" | "jsonl")}>
                <option value="csv">CSV (abre na planilha)</option>
                <option value="jsonl">JSON Lines (um objeto por linha)</option>
              </NativeSelect>
            )}
          </Field>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={incluirAnonimas} onChange={(e) => setIncluirAnonimas(e.target.checked)} />
            <span>
              Incluir contas anônimas
              <span className="block text-xs text-muted-foreground">Séries de contas desconectadas, sem nada que as identifique.</span>
            </span>
          </label>
          {error !== null && <ApiErrorAlert error={error} />}
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" disabled={busy} onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="button" disabled={busy || Boolean(periodoErro)} aria-busy={busy} onClick={() => void exportar()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Download aria-hidden="true" />}
            Exportar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
