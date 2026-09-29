import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChangePasswordForm } from "../components/ChangePasswordForm";
import { AuthLayout } from "../components/layout";
import { Alert, Button } from "../components/ui";
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
    <AuthLayout title="Trocar senha">
      <div className="space-y-4">
        {mustChange && (
          <Alert tone="info">Sua senha é provisória. Defina uma senha nova para continuar.</Alert>
        )}
        <ChangePasswordForm onSuccess={() => navigate("/app", { replace: true })} />
        <Button type="button" variant="ghost" loading={loggingOut} onClick={onLogout}>
          Sair
        </Button>
      </div>
    </AuthLayout>
  );
}
