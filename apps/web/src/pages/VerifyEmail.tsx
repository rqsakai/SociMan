import { ApiError } from "@sociman/contract";
import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthLayout } from "../components/layout";
import { Alert } from "../components/ui";
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
    <AuthLayout title="Verificação de e-mail">
      {status === "verifying" && (
        <p className="flex items-center gap-2 text-sm" aria-live="polite">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Verificando…
        </p>
      )}
      {status === "success" && (
        <div className="space-y-4">
          <Alert tone="success">E-mail confirmado, faça login.</Alert>
          <Link className="text-sm text-text underline hover:text-muted" to="/login">
            Ir para o login
          </Link>
        </div>
      )}
      {status === "error" && (
        <div className="space-y-4">
          <Alert tone="error">{message}</Alert>
          <Link className="text-sm text-text underline hover:text-muted" to="/login">
            Voltar para o login
          </Link>
        </div>
      )}
    </AuthLayout>
  );
}
