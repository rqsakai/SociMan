import { Info, Loader2, LogOut } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthShell } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ChangePasswordForm } from "../components/ChangePasswordForm";
import { logout } from "../lib/authActions";
import { useAuth } from "../lib/authStore";

// /trocar-senha: obrigatória enquanto mustChangePassword (senha provisória).
export default function ChangePassword() {
  const navigate = useNavigate();
  const mustChange = useAuth((s) => s.user?.mustChangePassword ?? false);
  const [loggingOut, setLoggingOut] = useState(false);

  async function onLogout() {
    setLoggingOut(true);
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <AuthShell
      title="Trocar senha"
      footer={
        <Button type="button" variant="ghost" size="sm" disabled={loggingOut} aria-busy={loggingOut} onClick={onLogout}>
          {loggingOut ? <Loader2 className="animate-spin" aria-hidden="true" /> : <LogOut aria-hidden="true" />}
          Sair
        </Button>
      }
    >
      <div className="space-y-4">
        {mustChange && (
          <Alert role="status" className="border-info/40 [&>svg]:text-info">
            <Info aria-hidden="true" />
            <AlertDescription>Sua senha é provisória. Defina uma senha nova para continuar.</AlertDescription>
          </Alert>
        )}
        <ChangePasswordForm onSuccess={() => navigate("/app", { replace: true })} />
      </div>
    </AuthShell>
  );
}
