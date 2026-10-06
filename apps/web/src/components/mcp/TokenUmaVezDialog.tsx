import { KeyRound, TriangleAlert } from "lucide-react";
import { CopyButton } from "@/components/assets/CopyButton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// Credencial de um cliente MCP, mostrada UMA vez (spec 009, FR-003): na criação e a cada rotação.
// O token só vive no estado de quem abriu o diálogo; `onClose` o descarta (nada vai para cache,
// URL ou armazenamento do navegador).
export function TokenUmaVezDialog({
  token,
  nome,
  rotacao = false,
  onClose,
}: {
  token: string | null;
  nome: string;
  rotacao?: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={token !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-5" aria-hidden="true" />
            {rotacao ? `Nova credencial de ${nome}` : `Credencial de ${nome}`}
          </DialogTitle>
          <DialogDescription>
            Cole esta credencial na configuração do agente (cabeçalho <code>Authorization: Bearer …</code>).
          </DialogDescription>
        </DialogHeader>
        <Alert>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Guarde agora, ela não será mostrada de novo</AlertTitle>
          <AlertDescription>
            {rotacao
              ? "A credencial antiga já parou de valer. Se perder esta, rotacione de novo."
              : "O SociMan guarda só uma impressão dela. Se perder, rotacione para gerar outra."}
          </AlertDescription>
        </Alert>
        {token !== null && (
          <div className="space-y-2">
            <label htmlFor="mcp-token" className="text-sm font-medium">
              Credencial
            </label>
            <input
              id="mcp-token"
              readOnly
              value={token}
              autoComplete="off"
              spellCheck={false}
              onFocus={(e) => e.currentTarget.select()}
              className="h-9 w-full min-w-0 rounded-md border border-input bg-muted/40 px-3 font-mono text-xs"
            />
            <CopyButton text={token} label="Copiar" copiedLabel="Credencial copiada" />
          </div>
        )}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Já guardei
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
