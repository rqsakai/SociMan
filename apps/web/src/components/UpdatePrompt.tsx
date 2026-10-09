import { RefreshCw } from "lucide-react";
import { useRegisterSW } from "virtual:pwa-register/react";
import { Button } from "@/components/ui/button";

const UPDATE_INTERVAL_MS = 60 * 60 * 1000;

// Aviso de versão nova (US3). Também é quem registra o service worker
// (injectRegister: null). Em dev o módulo virtual é um stub sem SW:
// needRefresh fica sempre false e nada é renderizado.
export function UpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_swUrl, registration) {
      if (!registration) return;
      // Sem rede, update() rejeita; a próxima checagem tenta de novo.
      const check = () => {
        if (navigator.onLine) registration.update().catch(() => {});
      };
      setInterval(check, UPDATE_INTERVAL_MS);
      window.addEventListener("focus", check);
    },
  });

  if (!needRefresh) return null;

  // "Atualizar": skipWaiting + reload. A sessão volta pelo cookie de refresh
  // no bootstrapSession da página recarregada.
  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-md flex-wrap items-center gap-3 rounded-xl border bg-card p-4 text-card-foreground shadow-lg"
    >
      <p className="flex flex-1 items-center gap-2 text-sm font-medium">
        <RefreshCw className="size-4 shrink-0 text-primary" aria-hidden="true" />
        Nova versão disponível
      </p>
      <div className="flex gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setNeedRefresh(false)}>
          Agora não
        </Button>
        <Button
          type="button"
          size="sm"
          variant="band" className="text-xs font-bold tracking-wide uppercase"
          onClick={() => void updateServiceWorker(true)}
        >
          Atualizar
        </Button>
      </div>
    </div>
  );
}
