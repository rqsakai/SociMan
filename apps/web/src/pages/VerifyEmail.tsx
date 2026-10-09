import { ApiError } from "@sociman/contract";
import { CircleAlert, CircleCheck, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthShell } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api } from "../lib/api";

type Status = "verifying" | "success" | "error";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [status, setStatus] = useState<Status>(token ? "verifying" : "error");
  const [message, setMessage] = useState("Link inválido");
  const fired = useRef(false);

  useEffect(() => {
    if (!token || fired.current) return;
    fired.current = true; // StrictMode roda efeitos 2x em dev; o token é single-shot
    api.auth
      .verifyEmail({ token })
      .then(() => setStatus("success"))
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof ApiError ? err.message : "Não foi possível verificar o e-mail.");
      });
  }, [token]);

  return (
    <AuthShell
      title="Verificação de e-mail"
      tone={status === "error" ? "destructive" : status === "success" ? "success" : "primary"}
      footer={
        status !== "verifying" && (
          <Link className="font-semibold text-primary hover:underline" to="/login">
            {status === "success" ? "Ir para o login" : "Voltar para o login"}
          </Link>
        )
      }
    >
      {status === "verifying" && (
        <p className="flex items-center gap-2 text-sm" aria-live="polite">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Verificando…
        </p>
      )}
      {status === "success" && (
        <Alert role="status" className="border-success/40 [&>svg]:text-success">
          <CircleCheck aria-hidden="true" />
          <AlertDescription>E-mail confirmado, faça login.</AlertDescription>
        </Alert>
      )}
      {status === "error" && (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}
    </AuthShell>
  );
}
