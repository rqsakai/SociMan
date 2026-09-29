import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Offline } from "./components/Offline";
import { CHANGE_PASSWORD_PATH, RequireAuth } from "./components/RequireAuth";
import { RequireOwner } from "./components/RequireOwner";
import { UpdatePrompt } from "./components/UpdatePrompt";
import { bootstrapSession } from "./lib/authActions";
import { useAuth } from "./lib/authStore";
import Account from "./pages/Account";
import AppHome from "./pages/AppHome";
import ChangePassword from "./pages/ChangePassword";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import ContaHistorico from "./pages/perfis/ContaHistorico";
import PerfilDetalhe from "./pages/perfis/PerfilDetalhe";
import PerfilNovo from "./pages/perfis/PerfilNovo";
import PerfisList from "./pages/perfis/PerfisList";
import ResetPassword from "./pages/ResetPassword";
import SecurityEvents from "./pages/SecurityEvents";
import Users from "./pages/Users";
import VerifyEmail from "./pages/VerifyEmail";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function RootRedirect() {
  const status = useAuth((s) => s.status);
  if (status === "unknown") {
    return <p className="p-8 text-sm" aria-live="polite">Carregando…</p>;
  }
  return <Navigate to={status === "authenticated" ? "/app" : "/login"} replace />;
}

export default function App() {
  const offline = useAuth((s) => s.status === "offline");
  // Restaura a sessão no reload via cookie de refresh (access token é só memória).
  useEffect(() => {
    void bootstrapSession();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* Boot sem rede: "Sem conexão" no lugar de qualquer rota (US2). */}
        {offline ? (
          <Offline />
        ) : (
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route
              path={CHANGE_PASSWORD_PATH}
              element={
                <RequireAuth>
                  <ChangePassword />
                </RequireAuth>
              }
            />
            <Route
              path="/app"
              element={
                <RequireAuth>
                  <AppHome />
                </RequireAuth>
              }
            />
            <Route
              path="/app/conta"
              element={
                <RequireAuth>
                  <Account />
                </RequireAuth>
              }
            />
            <Route
              path="/app/perfis"
              element={
                <RequireAuth>
                  <PerfisList />
                </RequireAuth>
              }
            />
            <Route
              path="/app/perfis/novo"
              element={
                <RequireAuth>
                  <PerfilNovo />
                </RequireAuth>
              }
            />
            <Route
              path="/app/perfis/:id"
              element={
                <RequireAuth>
                  <PerfilDetalhe />
                </RequireAuth>
              }
            />
            <Route
              path="/app/contas/:id/historico"
              element={
                <RequireAuth>
                  <ContaHistorico />
                </RequireAuth>
              }
            />
            <Route
              path="/app/usuarios"
              element={
                <RequireAuth>
                  <RequireOwner>
                    <Users />
                  </RequireOwner>
                </RequireAuth>
              }
            />
            <Route
              path="/app/seguranca"
              element={
                <RequireAuth>
                  <RequireOwner>
                    <SecurityEvents />
                  </RequireOwner>
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </BrowserRouter>
      {/* Fora das rotas: o aviso de versão nova aparece em qualquer tela (US3). */}
      <UpdatePrompt />
    </QueryClientProvider>
  );
}
