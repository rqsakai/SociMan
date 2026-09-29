import type { AppConfig } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { PASSWORD_MAX_LENGTH_DEFAULT, PASSWORD_MIN_LENGTH_DEFAULT } from "./forms";

// Fallback = defaults do backend. O app NUNCA quebra sem o endpoint de config:
// enquanto carrega (ou se falhar), o front valida com os mesmos defaults que o
// servidor usa quando nada foi configurado.
export const fallbackAppConfig: AppConfig = {
  passwordMinLength: PASSWORD_MIN_LENGTH_DEFAULT,
  passwordMaxLength: PASSWORD_MAX_LENGTH_DEFAULT,
};

// Config pública do app (GET /api/config) — fecha o drift entre a validação do
// browser e a do servidor quando PASSWORD_MIN_LENGTH/PASSWORD_MAX_LENGTH mudam.
export function useAppConfig(): AppConfig {
  const { data } = useQuery({
    queryKey: ["app-config"],
    queryFn: () => api.config(),
    staleTime: Infinity,
    retry: 1,
  });
  return {
    passwordMinLength: data?.passwordMinLength ?? fallbackAppConfig.passwordMinLength,
    passwordMaxLength: data?.passwordMaxLength ?? fallbackAppConfig.passwordMaxLength,
  };
}
