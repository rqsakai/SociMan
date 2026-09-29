import { consentCategoriesSchema, type ConsentCategories } from "@sociman/contract";
import { z } from "zod";
import { api } from "./api";

// Fallback da versão da política quando o GET /api/config ainda não respondeu
// (a fonte da verdade é CONSENT_POLICY_VERSION do backend, via useAppConfig).
export const FALLBACK_POLICY_VERSION: string =
  import.meta.env.VITE_CONSENT_POLICY_VERSION ?? "2026-08";

const STORAGE_KEY = "sociman-consent";

const storedConsentSchema = z.object({
  categories: consentCategoriesSchema,
  policyVersion: z.string(),
  anonId: z.string(),
});
export type StoredConsent = z.infer<typeof storedConsentSchema>;

// Única escrita em localStorage do app — preferência de consentimento, nada
// sensível. Tokens NUNCA passam por aqui.
export function getStoredConsent(
  policyVersion: string = FALLBACK_POLICY_VERSION,
): StoredConsent | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = storedConsentSchema.parse(JSON.parse(raw));
    // política mudou → pedir consentimento de novo
    if (parsed.policyVersion !== policyVersion) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function saveConsent(
  categories: ConsentCategories,
  policyVersion: string = FALLBACK_POLICY_VERSION,
): Promise<void> {
  const anonId = getStoredConsent(policyVersion)?.anonId ?? crypto.randomUUID();
  const stored: StoredConsent = { categories, policyVersion, anonId };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  // Auditoria no backend; falha de rede não bloqueia o uso do app.
  await api.consent.record({ categories, policyVersion, anonId }).catch(() => {});
}
