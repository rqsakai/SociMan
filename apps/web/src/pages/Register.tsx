import { zodResolver } from "@hookform/resolvers/zod";
import {
  ApiError,
  passwordSchema,
  registerRequestSchema,
  type RegisterRequest,
} from "@sociman/contract";
import { Lock, Mail, User, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/layout";
import { Alert, Button, Field, Input } from "../components/ui";
import { register as registerAction } from "../lib/authActions";
import { useAppConfig } from "../lib/useAppConfig";

export default function Register() {
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  // A política de senha vem do backend (useAppConfig) — o browser valida com o
  // MESMO mínimo que o servidor, mesmo quando PASSWORD_MIN_LENGTH foi alterado.
  const { passwordMinLength } = useAppConfig();
  const resolver = useMemo(
    () =>
      zodResolver(registerRequestSchema.extend({ password: passwordSchema(passwordMinLength) })),
    [passwordMinLength],
  );
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterRequest>({ resolver });

  async function onSubmit(data: RegisterRequest) {
    setServerError(null);
    try {
      await registerAction(data);
      navigate("/app", { replace: true });
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Não foi possível criar a conta.");
    }
  }

  return (
    <AuthLayout title="Criar conta">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {serverError && <Alert tone="error">{serverError}</Alert>}
        <Field label="Nome (opcional)" error={errors.name?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              icon={User}
              autoComplete="name"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("name", { setValueAs: (v: string) => (v === "" ? undefined : v) })}
            />
          )}
        </Field>
        <Field label="E-mail" error={errors.email?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="email"
              icon={Mail}
              autoComplete="email"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("email")}
            />
          )}
        </Field>
        <Field label="Senha" error={errors.password?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="password"
              icon={Lock}
              autoComplete="new-password"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("password")}
            />
          )}
        </Field>
        <Button type="submit" loading={isSubmitting}>
          {!isSubmitting && <UserPlus className="size-4" aria-hidden="true" />}
          Criar conta
        </Button>
      </form>
      <p className="mt-4 text-sm">
        Já tem conta?{" "}
        <Link className="text-text underline hover:text-muted" to="/login">
          Entrar
        </Link>
      </p>
    </AuthLayout>
  );
}
