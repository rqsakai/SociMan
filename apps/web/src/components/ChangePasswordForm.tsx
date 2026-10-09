import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, KeyRound, Loader2, Lock } from "lucide-react";
import { useMemo, useState, type ComponentProps } from "react";
import { useForm } from "react-hook-form";
import { api } from "../lib/api";
import { useAuth } from "../lib/authStore";
import { changePasswordForm, type ChangePasswordForm as FormData } from "../lib/forms";
import { useAppConfig } from "../lib/useAppConfig";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

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
      {serverError && (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>{serverError}</AlertDescription>
        </Alert>
      )}
      <Field label="Senha atual" error={errors.currentPassword?.message}>
        {({ id, describedBy, invalid }) => (
          <PasswordInput
            id={id}
            type="password"
            autoComplete="current-password"
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field("currentPassword")}
          />
        )}
      </Field>
      <Field label="Nova senha" error={errors.newPassword?.message}>
        {({ id, describedBy, invalid }) => (
          <PasswordInput
            id={id}
            type="password"
            autoComplete="new-password"
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field("newPassword")}
          />
        )}
      </Field>
      <Field label="Confirmar nova senha" error={errors.confirmPassword?.message}>
        {({ id, describedBy, invalid }) => (
          <PasswordInput
            id={id}
            type="password"
            autoComplete="new-password"
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field("confirmPassword")}
          />
        )}
      </Field>
      <Button type="submit" className="w-full" disabled={isSubmitting} aria-busy={isSubmitting}>
        {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <KeyRound aria-hidden="true" />}
        Trocar senha
      </Button>
    </form>
  );
}

// Campo de senha com o cadeado à esquerda.
function PasswordInput({ className, ...props }: ComponentProps<typeof Input>) {
  return (
    <div className="relative">
      <Lock className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
      <Input className={cn("pl-9", className)} {...props} />
    </div>
  );
}
