import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@sociman/contract";
import { Lock, LogIn, Mail, Send } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/layout";
import { Alert, Button, Field, Input } from "../components/ui";
import { api } from "../lib/api";
import { login } from "../lib/authActions";
import { loginForm, type LoginForm } from "../lib/forms";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { passwordReset?: boolean; from?: string } | null;
  const passwordReset = Boolean(state?.passwordReset);
  const [serverError, setServerError] = useState<string | null>(null);
  // E-mail do login recusado por falta de verificação (habilita o reenvio).
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null);
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({ resolver: zodResolver(loginForm) });

  async function onSubmit(data: LoginForm) {
    setServerError(null);
    setUnverifiedEmail(null);
    setResent(false);
    try {
      await login(data);
      navigate(state?.from ?? "/app", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "email_not_verified") {
        setUnverifiedEmail(data.email);
        setServerError("Confirme seu e-mail antes de entrar.");
      } else if (err instanceof ApiError && err.code === "invalid_credentials") {
        setServerError("E-mail ou senha incorretos");
      } else {
        setServerError(err instanceof ApiError ? err.message : "Não foi possível entrar. Tente de novo.");
      }
    }
  }

  async function onResend() {
    if (!unverifiedEmail) return;
    setResending(true);
    // A API sempre responde 200 (sem enumeração); o 429 também vira a mesma mensagem.
    await api.auth.resendVerification({ email: unverifiedEmail }).catch(() => {});
    setResending(false);
    setResent(true);
  }

  return (
    <AuthLayout title="Entrar">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {passwordReset && !serverError && (
          <Alert tone="success">Senha redefinida — entre com a nova senha.</Alert>
        )}
        {serverError && <Alert tone="error">{serverError}</Alert>}
        {unverifiedEmail &&
          (resent ? (
            <Alert tone="success">Se o e-mail estiver cadastrado, enviamos um novo link.</Alert>
          ) : (
            <Button type="button" variant="ghost" loading={resending} onClick={onResend}>
              {!resending && <Send className="size-4" aria-hidden="true" />}
              Reenviar link
            </Button>
          ))}
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
      <div className="mt-4 flex justify-end text-sm">
        <Link className="text-text underline hover:text-muted" to="/forgot-password">
          Esqueci a senha
        </Link>
      </div>
    </AuthLayout>
  );
}
