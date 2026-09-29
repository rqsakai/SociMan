import { useQuery } from "@tanstack/react-query";
import type { ConfigResponse } from "@sociman/contract";
import { api } from "./api";
import { FALLBACK_POLICY_VERSION } from "./consent";

// Fallback = defaults do backend. O app NUNCA quebra sem o endpoint de config:
// enquanto carrega (ou se falhar), o front valida com os mesmos defaults que o
// servidor usa quando nada foi configurado.
export const fallbackAppConfig: ConfigResponse = {
  passwordMinLength: 8,
  consentPolicyVersion: FALLBACK_POLICY_VERSION,
};

// Config pública do app (GET /api/config) — fecha o drift entre a validação do
// browser e a do servidor quando [config] como PASSWORD_MIN_LENGTH mudam.
export function useAppConfig(): ConfigResponse {
  const { data } = useQuery({
    queryKey: ["app-config"],
    queryFn: () => api.config(),
    staleTime: Infinity,
    retry: 1,
  });
  return data ?? fallbackAppConfig;
}
