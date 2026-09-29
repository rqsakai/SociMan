import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, loginRequestSchema, type LoginRequest } from "@sociman/contract";
import { Lock, LogIn, Mail } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/layout";
import { Alert, Button, Field, Input } from "../components/ui";
import { login } from "../lib/authActions";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const passwordReset = Boolean((location.state as { passwordReset?: boolean } | null)?.passwordReset);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginRequest>({ resolver: zodResolver(loginRequestSchema) });

  async function onSubmit(data: LoginRequest) {
    setServerError(null);
    try {
      await login(data);
      navigate("/app", { replace: true });
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Não foi possível entrar. Tente de novo.");
    }
  }

  return (
    <AuthLayout title="Entrar">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {passwordReset && !serverError && (
          <Alert tone="success">Senha redefinida — entre com a nova senha.</Alert>
        )}
        {serverError && <Alert tone="error">{serverError}</Alert>}
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
              autoComplete="current-password"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("password")}
            />
          )}
        </Field>
        <Button type="submit" loading={isSubmitting}>
          {!isSubmitting && <LogIn className="size-4" aria-hidden="true" />}
          Entrar
        </Button>
      </form>
      <div className="mt-4 flex justify-between text-sm">
        <Link className="text-text underline hover:text-muted" to="/register">
          Criar conta
        </Link>
        <Link className="text-text underline hover:text-muted" to="/forgot-password">
          Esqueci a senha
        </Link>
      </div>
    </AuthLayout>
  );
}
