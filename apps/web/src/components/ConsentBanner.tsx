import { useEffect, useState } from "react";
import { getStoredConsent, saveConsent } from "../lib/consent";
import { useAppConfig } from "../lib/useAppConfig";
import { Button } from "./ui";

// Banner LGPD honesto (§7): o app é quase cookieless. O único cookie (refresh
// de sessão) é estritamente necessário — informado, sem opt-out. Categorias
// não essenciais (analytics) ficam DESLIGADAS até aceite explícito.
// A versão da política vem do backend (useAppConfig): quando ela muda, o
// consentimento antigo deixa de valer e o banner reaparece.
export function ConsentBanner() {
  const { consentPolicyVersion } = useAppConfig();
  const [decided, setDecided] = useState(() => getStoredConsent(consentPolicyVersion) !== null);
  const [managing, setManaging] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const [saving, setSaving] = useState(false);

  // reavalia quando a versão real da política chega do backend
  useEffect(() => {
    setDecided(getStoredConsent(consentPolicyVersion) !== null);
  }, [consentPolicyVersion]);

  if (decided) return null;

  async function decide(withAnalytics: boolean) {
    setSaving(true);
    await saveConsent({ essential: true, analytics: withAnalytics }, consentPolicyVersion);
    setDecided(true);
  }

  return (
    <aside
      role="region"
      aria-label="Preferências de privacidade"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-surface p-4 shadow-lg"
    >
      <div className="mx-auto max-w-2xl space-y-3 text-sm">
        <p>
          Usamos <strong>um único cookie</strong>, estritamente necessário, para manter sua sessão —
          ele não rastreia você e não tem opt-out. Análise de uso (analytics) é opcional e fica{" "}
          <strong>desligada</strong> até você aceitar.
        </p>

        {managing && (
          <div className="space-y-2 rounded-field border border-border p-3">
            <label className="flex items-center justify-between gap-2">
              <span>Cookie de sessão (estritamente necessário)</span>
              <input type="checkbox" checked disabled aria-label="Cookie de sessão, sempre ativo" />
            </label>
            <label className="flex items-center justify-between gap-2">
              <span>Analytics (opcional)</span>
              <input
                type="checkbox"
                checked={analytics}
                onChange={(e) => setAnalytics(e.target.checked)}
              />
            </label>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {managing ? (
            <Button className="!w-auto" loading={saving} onClick={() => decide(analytics)}>
              Salvar preferências
            </Button>
          ) : (
            <>
              <Button className="!w-auto" loading={saving} onClick={() => decide(true)}>
                Aceitar tudo
              </Button>
              <Button className="!w-auto" variant="ghost" loading={saving} onClick={() => decide(false)}>
                Só o essencial
              </Button>
              <Button className="!w-auto" variant="ghost" onClick={() => setManaging(true)}>
                Gerenciar preferências
              </Button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
