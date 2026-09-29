import { CircleAlert, RefreshCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { errorText, isVersionConflict } from "../lib/perfis";

// Erro da API num <Alert> (spec 005, T010): a mensagem é a da API, sem reescrever. No conflito de
// versão, o botão "Recarregar" (quando há `onReload`) busca a versão atual do registro.
export function ApiErrorAlert({ error, onReload, className }: { error: unknown; onReload?: () => void; className?: string }) {
  const conflict = isVersionConflict(error);
  return (
    <Alert variant="destructive" className={className}>
      <CircleAlert aria-hidden="true" />
      <AlertTitle>{conflict ? "Conflito de versão" : "Não foi possível concluir"}</AlertTitle>
      <AlertDescription>
        <p>{errorText(error)}</p>
        {conflict && onReload && (
          <Button type="button" variant="outline" size="sm" className="mt-1" onClick={onReload}>
            <RefreshCw aria-hidden="true" />
            Recarregar
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
