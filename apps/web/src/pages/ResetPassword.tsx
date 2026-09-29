import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, passwordSchema } from "@sociman/contract";
import { KeyRound, Lock } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { AuthLayout } from "../components/layout";
import { Alert, Button, Field, Input } from "../components/ui";
import { api } from "../lib/api";
import { useAppConfig } from "../lib/useAppConfig";

type FormData = { newPassword: string };

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  // mesmo mínimo de senha que o servidor (ver useAppConfig)
  const { passwordMinLength } = useAppConfig();
  const resolver = useMemo(
    () => zodResolver(z.object({ newPassword: passwordSchema(passwordMinLength) })),
    [passwordMinLength],
  );
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver });

  async function onSubmit(data: FormData) {
    setServerError(null);
    try {
      await api.auth.resetPassword({ token, newPassword: data.newPassword });
      navigate("/login", { replace: true, state: { passwordReset: true } });
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Não foi possível redefinir a senha.");
    }
  }

  if (!token) {
    return (
      <AuthLayout title="Redefinir senha">
        <Alert tone="error">Link inválido — peça um novo em “Esqueci a senha”.</Alert>
        <p className="mt-4 text-sm">
          <Link className="text-text underline hover:text-muted" to="/forgot-password">
            Pedir novo link
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Redefinir senha">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {serverError && <Alert tone="error">{serverError}</Alert>}
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
        <Button type="submit" loading={isSubmitting}>
          {!isSubmitting && <KeyRound className="size-4" aria-hidden="true" />}
          Redefinir senha
        </Button>
      </form>
    </AuthLayout>
  );
}
