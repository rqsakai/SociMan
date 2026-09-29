import { Loader2, RotateCw, WifiOff } from "lucide-react";
import { useState } from "react";
import { AuthShell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { bootstrapSession } from "../lib/authActions";

// Boot sem rede (US2): o shell abriu do precache, mas o refresh não alcançou o
// servidor. "Tentar de novo" refaz o boot; se der certo, o App troca de tela.
export function Offline() {
  const [retrying, setRetrying] = useState(false);

  async function onRetry() {
    setRetrying(true);
    try {
      await bootstrapSession();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <AuthShell title="Sem conexão com o SociMan" tone="dark">
      <div className="space-y-4">
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <WifiOff className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Verifique se você está na rede de casa e se o SociMan está ligado.
        </p>
        <Button
          type="button"
          className="tone-primary w-full text-xs font-bold tracking-wide uppercase"
          onClick={onRetry}
          disabled={retrying}
          aria-busy={retrying}
        >
          {retrying ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCw aria-hidden="true" />}
          Tentar de novo
        </Button>
      </div>
    </AuthShell>
  );
}
