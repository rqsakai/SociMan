import { zodResolver } from "@hookform/resolvers/zod";
import { CircleCheck, Loader2, Send } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { Field } from "@/components/ui/field";
import { AuthShell } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
    <AuthShell
      title="Recuperar senha"
      description="Enviamos um link para o seu e-mail"
      footer={
        <Link className="font-semibold text-primary hover:underline" to="/login">
          Voltar para o login
        </Link>
      }
    >
      {sent ? (
        <Alert role="status" className="border-success/40 [&>svg]:text-success">
          <CircleCheck aria-hidden="true" />
          <AlertDescription>
            Se existir uma conta com esse e-mail, enviamos um link para redefinir a senha. O link
            expira em alguns minutos.
          </AlertDescription>
        </Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
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
          <Button
            type="submit"
            variant="band" className="w-full text-xs font-bold tracking-wide uppercase"
            disabled={isSubmitting}
            aria-busy={isSubmitting}
          >
            {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            Enviar link de recuperação
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
