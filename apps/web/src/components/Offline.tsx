import { RotateCw, WifiOff } from "lucide-react";
import { useState } from "react";
import { bootstrapSession } from "../lib/authActions";
import { AuthLayout } from "./layout";
import { Button } from "./ui";

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
    <AuthLayout title="Sem conexão com o SociMan">
      <div className="space-y-4">
        <p className="flex items-start gap-2 text-sm text-muted">
          <WifiOff className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Verifique se você está na rede de casa e se o SociMan está ligado.
        </p>
        <Button type="button" onClick={onRetry} loading={retrying}>
          {!retrying && <RotateCw className="size-4" aria-hidden="true" />}
          Tentar de novo
        </Button>
      </div>
    </AuthLayout>
  );
}
