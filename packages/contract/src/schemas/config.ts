import { z } from "zod";

// Config PÚBLICA do app: valores [config] do backend que o front precisa
// espelhar (política de senha, versão da política de consentimento) para não
// haver drift entre validação do browser e do servidor. Nada sensível pode
// entrar neste schema — ele é servido sem autenticação.
export const configResponseSchema = z.object({
  passwordMinLength: z.number().int().min(8),
  consentPolicyVersion: z.string(),
});
export type ConfigResponse = z.infer<typeof configResponseSchema>;
