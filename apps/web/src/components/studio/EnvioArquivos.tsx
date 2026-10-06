/*
 * Envio dos arquivos do Studio (spec 020, US1/US2; só dono): o input aceita 1 ou 2 arquivos
 * (.zip ou .csv) e "Ler arquivos" pede a prévia. Nada é gravado aqui. A recusa da API aparece em
 * <ErroStudio>: a mensagem em pt-BR e, quando há, a lista de problemas por linha ("e mais N").
 */
import { ApiError } from "@sociman/contract";
import { CircleAlert, FileUp, Loader2 } from "lucide-react";
import { useId, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

interface Problema {
  arquivo?: string;
  linha?: number;
  coluna?: string;
  valor?: string;
  motivo?: string;
}

const textoDe = (v: unknown) => (typeof v === "string" && v ? v : null);

// Erro do envio: os códigos da 020 trazem detalhes úteis (problemas por linha, orientação,
// colunas encontradas); o resto cai no alerta padrão.
export function ErroStudio({ error }: { error: unknown }) {
  if (!(error instanceof ApiError) || !error.code.startsWith("studio_")) return <ApiErrorAlert error={error} />;
  const d = error.details;
  const problemas = Array.isArray(d.problemas) ? (d.problemas as Problema[]) : [];
  const total = typeof d.total === "number" ? d.total : problemas.length;
  const extra = [textoDe(d.orientacao), textoDe(d.motivo), textoDe(d.arquivo) && `Arquivo: ${d.arquivo as string}`].filter(Boolean) as string[];
  const encontradas = Array.isArray(d.encontradas) ? (d.encontradas as string[]) : null;
  return (
    <Alert variant="destructive" data-erro-studio={error.code}>
      <CircleAlert aria-hidden="true" />
      <AlertTitle>Arquivo recusado</AlertTitle>
      <AlertDescription>
        <p>{error.message}</p>
        {extra.map((t) => (
          <p key={t}>{t}</p>
        ))}
        {encontradas && <p>Colunas encontradas: {encontradas.join(", ") || "nenhuma"}.</p>}
        {problemas.length > 0 && (
          <ul className="mt-1 list-disc space-y-0.5 pl-5" aria-label="Problemas encontrados">
            {problemas.map((p, i) => (
              <li key={i} data-problema>
                {[p.arquivo, p.linha !== undefined && `linha ${p.linha}`, p.coluna && `coluna "${p.coluna}"`, p.valor !== undefined && p.valor !== null && `valor "${p.valor}"`]
                  .filter(Boolean)
                  .join(", ")}
                {p.motivo && `: ${p.motivo}`}
              </li>
            ))}
          </ul>
        )}
        {total > problemas.length && <p>e mais {total - problemas.length}.</p>}
      </AlertDescription>
    </Alert>
  );
}

export function EnvioArquivos({ lendo, erro, onLer }: { lendo: boolean; erro: unknown; onLer: (arquivos: File[]) => void }) {
  const id = useId();
  const [arquivos, setArquivos] = useState<File[]>([]);
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (arquivos.length) onLer(arquivos);
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor={id}>Arquivos do Studio</Label>
        <input
          id={id}
          type="file"
          multiple
          accept=".zip,.csv"
          aria-describedby={`${id}-dica`}
          className="block w-full max-w-full text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-background file:px-3 file:py-1.5 file:text-sm file:font-medium"
          onChange={(e) => setArquivos(Array.from(e.target.files ?? []))}
        />
        <p id={`${id}-dica`} className="text-xs text-muted-foreground">
          No TikTok Studio (computador): Analytics → Visão geral e Seguidores → Baixar dados. Envie o ZIP de cada seção (ou os CSVs de dentro), 1 ou 2 arquivos, até 5 MB.
          Os arquivos são lidos e descartados; nada é guardado.
        </p>
      </div>
      <Button type="submit" disabled={lendo || arquivos.length === 0} aria-busy={lendo}>
        {lendo ? <Loader2 className="animate-spin" aria-hidden="true" /> : <FileUp aria-hidden="true" />}
        Ler arquivos
      </Button>
      {erro ? <ErroStudio error={erro} /> : null}
    </form>
  );
}
