import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@sociman/contract";
import { CircleAlert, KeyRound, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Field } from "@/components/ui/field";
import { AuthShell } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "../lib/api";
import { resetForm, type ResetForm } from "../lib/forms";
import { useAppConfig } from "../lib/useAppConfig";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  // token inválido, expirado ou já usado: só resta pedir um link novo
  const [linkInvalid, setLinkInvalid] = useState(false);
  // mesmo mínimo de senha que o servidor (ver useAppConfig)
  const { passwordMinLength, passwordMaxLength } = useAppConfig();
  const resolver = useMemo(
    () => zodResolver(resetForm({ passwordMinLength, passwordMaxLength })),
    [passwordMinLength, passwordMaxLength],
  );
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetForm>({ resolver });

  async function onSubmit(data: ResetForm) {
    setServerError(null);
    setLinkInvalid(false);
    try {
      await api.auth.resetPassword({ token, newPassword: data.newPassword });
      navigate("/login", { replace: true, state: { passwordReset: true } });
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Não foi possível redefinir a senha.");
      setLinkInvalid(err instanceof ApiError && err.code === "invalid_token");
    }
  }

  const newLinkFooter = (
    <Link className="font-semibold text-primary hover:underline" to="/forgot-password">
      Pedir novo link
    </Link>
  );

  if (!token) {
    return (
      <AuthShell title="Redefinir senha" footer={newLinkFooter}>
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>Link inválido ou expirado — peça um novo</AlertDescription>
        </Alert>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Redefinir senha"
      description="Escolha uma senha nova"
      footer={linkInvalid ? newLinkFooter : undefined}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {serverError && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertDescription>{serverError}</AlertDescription>
          </Alert>
        )}
        <Field label="Nova senha" error={errors.newPassword?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
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
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("confirmPassword")}
            />
          )}
        </Field>
        <Button
          type="submit"
          className="tone-primary w-full text-xs font-bold tracking-wide uppercase"
          disabled={isSubmitting}
          aria-busy={isSubmitting}
        >
          {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <KeyRound aria-hidden="true" />}
          Redefinir senha
        </Button>
      </form>
    </AuthShell>
  );
}
