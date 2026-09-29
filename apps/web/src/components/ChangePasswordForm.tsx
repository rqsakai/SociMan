import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { api } from "../lib/api";
import { useAuth } from "../lib/authStore";
import { changePasswordForm, type ChangePasswordForm as FormData } from "../lib/forms";
import { useAppConfig } from "../lib/useAppConfig";
import { Alert, Button, Field, Input } from "./ui";

// Troca de senha com a senha atual: usada na troca obrigatória (/trocar-senha)
// e na voluntária (/app/conta). A resposta traz a sessão atualizada.
export function ChangePasswordForm({ onSuccess }: { onSuccess: () => void }) {
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const { passwordMinLength, passwordMaxLength } = useAppConfig();
  const resolver = useMemo(
    () => zodResolver(changePasswordForm({ passwordMinLength, passwordMaxLength })),
    [passwordMinLength, passwordMaxLength],
  );
  const {
    register: field,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver });

  async function onSubmit(data: FormData) {
    setServerError(null);
    try {
      const session = await api.auth.changePassword({
        currentPassword: data.currentPassword,
        newPassword: data.newPassword,
      });
      useAuth.getState().setSession(session.accessToken, session.user);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      reset();
      onSuccess();
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Não foi possível trocar a senha.");
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {serverError && <Alert tone="error">{serverError}</Alert>}
      <Field label="Senha atual" error={errors.currentPassword?.message}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="password"
            icon={Lock}
            autoComplete="current-password"
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field("currentPassword")}
          />
        )}
      </Field>
      <Field label="Nova senha" error={errors.newPassword?.message}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="password"
            icon={Lock}
            autoComplete="new-password"
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field("newPassword")}
          />
        )}
      </Field>
      <Field label="Confirmar nova senha" error={errors.confirmPassword?.message}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="password"
            icon={Lock}
            autoComplete="new-password"
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field("confirmPassword")}
          />
        )}
      </Field>
      <Button type="submit" loading={isSubmitting}>
        {!isSubmitting && <KeyRound className="size-4" aria-hidden="true" />}
        Trocar senha
      </Button>
    </form>
  );
}
