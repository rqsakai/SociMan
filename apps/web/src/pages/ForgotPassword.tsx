import { zodResolver } from "@hookform/resolvers/zod";
import { Mail, Send } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { AuthLayout } from "../components/layout";
import { Alert, Button, Field, Input } from "../components/ui";
import { api } from "../lib/api";
import { forgotForm, type ForgotForm } from "../lib/forms";

export default function ForgotPassword() {
  const [sent, setSent] = useState(false);
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotForm>({ resolver: zodResolver(forgotForm) });

  async function onSubmit(data: ForgotForm) {
    // A API sempre responde 200 (sem enumeração) — a UI reflete isso.
    await api.auth.forgotPassword(data).catch(() => {});
    setSent(true);
  }

  return (
    <AuthLayout title="Recuperar senha">
      {sent ? (
        <div className="space-y-4">
          <Alert tone="success">
            Se existir uma conta com esse e-mail, enviamos um link para redefinir a senha. O link
            expira em alguns minutos.
          </Alert>
          <Link className="text-sm text-text underline hover:text-muted" to="/login">
            Voltar para o login
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
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
          <Button type="submit" loading={isSubmitting}>
            {!isSubmitting && <Send className="size-4" aria-hidden="true" />}
            Enviar link de recuperação
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
