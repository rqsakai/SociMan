import { z } from "zod";

// Validação de formulário é regra de UI (research.md R7): o servidor continua
// sendo a autoridade. Os limites de senha vêm de GET /api/config (useAppConfig);
// os defaults abaixo são os mesmos do backend, usados enquanto a config carrega.
export const PASSWORD_MIN_LENGTH_DEFAULT = 12;
export const PASSWORD_MAX_LENGTH_DEFAULT = 128;

export const emailField = z.string().trim().toLowerCase().pipe(z.email("E-mail inválido"));

export function passwordField(
  minLength: number = PASSWORD_MIN_LENGTH_DEFAULT,
  maxLength: number = PASSWORD_MAX_LENGTH_DEFAULT,
) {
  return z
    .string()
    .min(minLength, `A senha precisa ter pelo menos ${minLength} caracteres`)
    .max(maxLength, `A senha pode ter no máximo ${maxLength} caracteres`);
}

type PasswordLimits = { passwordMinLength?: number; passwordMaxLength?: number };

// Nova senha + confirmação; o erro de divergência aparece no campo de confirmação.
function newPasswordFields({ passwordMinLength, passwordMaxLength }: PasswordLimits) {
  return {
    newPassword: passwordField(passwordMinLength, passwordMaxLength),
    confirmPassword: z.string(),
  };
}

const confirmMatches = {
  check: (data: { newPassword: string; confirmPassword: string }) =>
    data.newPassword === data.confirmPassword,
  error: { message: "As senhas não conferem", path: ["confirmPassword"] },
};

// No login a senha só precisa estar preenchida: a política vale para senhas novas.
export const loginForm = z.object({
  email: emailField,
  password: z.string().min(1, "Informe a senha"),
});
export type LoginForm = z.infer<typeof loginForm>;

export const forgotForm = z.object({ email: emailField });
export type ForgotForm = z.infer<typeof forgotForm>;

export function resetForm(limits: PasswordLimits = {}) {
  return z
    .object(newPasswordFields(limits))
    .refine(confirmMatches.check, confirmMatches.error);
}
export type ResetForm = z.infer<ReturnType<typeof resetForm>>;

export function changePasswordForm(limits: PasswordLimits = {}) {
  return z
    .object({
      currentPassword: z.string().min(1, "Informe a senha atual"),
      ...newPasswordFields(limits),
    })
    .refine(confirmMatches.check, confirmMatches.error)
    .refine((data) => data.newPassword !== data.currentPassword, {
      message: "A nova senha precisa ser diferente da atual",
      path: ["newPassword"],
    });
}
export type ChangePasswordForm = z.infer<ReturnType<typeof changePasswordForm>>;

const nameField = z.string().trim().min(1, "Informe o nome").max(120, "O nome pode ter no máximo 120 caracteres");
const roleField = z.enum(["dono", "membro"]);

export function createUserForm({ passwordMinLength, passwordMaxLength }: PasswordLimits = {}) {
  return z.object({
    name: nameField,
    email: emailField,
    role: roleField,
    provisionalPassword: passwordField(passwordMinLength, passwordMaxLength),
  });
}
export type CreateUserForm = z.infer<ReturnType<typeof createUserForm>>;

export const editUserForm = z.object({ name: nameField, email: emailField, role: roleField });
export type EditUserForm = z.infer<typeof editUserForm>;

export function setPasswordForm({ passwordMinLength, passwordMaxLength }: PasswordLimits = {}) {
  return z.object({ provisionalPassword: passwordField(passwordMinLength, passwordMaxLength) });
}
export type SetPasswordForm = z.infer<ReturnType<typeof setPasswordForm>>;

// Perfis e contas (specs/003-contas-sociais): os mesmos limites do backend (data-model.md).
const perfilStatusField = z.enum(["em_preparacao", "ativo", "pausado"]);
const perfilDataFields = {
  name: z.string().trim().min(1, "Informe o nome").max(80, "O nome pode ter no máximo 80 caracteres"),
  niche: z.string().trim().max(200, "O nicho pode ter no máximo 200 caracteres"),
  bio: z.string().trim().max(2000, "A descrição pode ter no máximo 2000 caracteres"),
  language: z.string().regex(/^[a-z]{2,3}(-[A-Z]{2})?$/, "Idioma inválido"),
  status: perfilStatusField,
};

export const editPerfilForm = z.object(perfilDataFields);
export type EditPerfilForm = z.infer<typeof editPerfilForm>;

export const createPerfilForm = z.object({
  ...perfilDataFields,
  slug: z
    .string()
    .trim()
    .min(2, "O identificador precisa ter pelo menos 2 caracteres")
    .max(60, "O identificador pode ter no máximo 60 caracteres")
    .regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, "Use só minúsculas, números e hífen (ex.: a-taverna-nerd)"),
});
export type CreatePerfilForm = z.infer<typeof createPerfilForm>;

const contaStatusField = z.enum(["planejada", "ativa", "pausada", "encerrada"]);
const platformField = z.enum(["tiktok", "youtube", "instagram", "kwai", "facebook", "x", "outra"]);

// "@ ou link": um link (http/https) vira `url` e a API extrai o @; o resto vira `handle`.
export const contaForm = z
  .object({
    platform: platformField,
    platformName: z.string().trim().max(40, "O nome da plataforma pode ter no máximo 40 caracteres"),
    handleOrUrl: z.string().trim().min(1, "Informe o @ ou o link").max(500, "Texto longo demais"),
    status: contaStatusField,
    notes: z.string().trim().max(500, "A observação pode ter no máximo 500 caracteres"),
  })
  .refine((data) => data.platform !== "outra" || data.platformName.length > 0, {
    message: "Informe o nome da plataforma",
    path: ["platformName"],
  })
  .refine((data) => data.platform !== "outra" || isUrl(data.handleOrUrl), {
    message: "Em “Outra”, cole o link da conta",
    path: ["handleOrUrl"],
  });
export type ContaForm = z.infer<typeof contaForm>;

export function isUrl(value: string): boolean {
  return /^https?:\/\/\S+$/i.test(value.trim());
}
