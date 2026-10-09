import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@sociman/contract";
import { CircleAlert, CircleCheck, Loader2, LogIn, Send } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Field } from "@/components/ui/field";
import { AuthShell } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
    <AuthShell
      title="Entrar no SociMan"
      description="Acesso da agência"
      footer={
        <Link className="font-semibold text-primary hover:underline" to="/forgot-password">
          Esqueci a senha
        </Link>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {passwordReset && !serverError && (
          <Alert role="status" className="border-success/40 [&>svg]:text-success">
            <CircleCheck aria-hidden="true" />
            <AlertDescription>Senha redefinida — entre com a nova senha.</AlertDescription>
          </Alert>
        )}
        {serverError && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertDescription>{serverError}</AlertDescription>
          </Alert>
        )}
        {unverifiedEmail &&
          (resent ? (
            <Alert role="status" className="border-success/40 [&>svg]:text-success">
              <CircleCheck aria-hidden="true" />
              <AlertDescription>Se o e-mail estiver cadastrado, enviamos um novo link.</AlertDescription>
            </Alert>
          ) : (
            <Button
              type="button"
              variant="outline"
              className="w-full"
              disabled={resending}
              aria-busy={resending}
              onClick={onResend}
            >
              {resending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
              Reenviar link
            </Button>
          ))}
        <Field label="E-mail" error={errors.email?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="email"
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
              autoComplete="current-password"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("password")}
            />
          )}
        </Field>
        <Button
          type="submit"
          variant="band" className="w-full text-xs font-bold tracking-wide uppercase"
          disabled={isSubmitting}
          aria-busy={isSubmitting}
        >
          {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <LogIn aria-hidden="true" />}
          Entrar
        </Button>
      </form>
    </AuthShell>
  );
}
