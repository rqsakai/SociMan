import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Offline } from "./components/Offline";
import { CHANGE_PASSWORD_PATH, RequireAuth } from "./components/RequireAuth";
import { RequireOwner } from "./components/RequireOwner";
import { AppShell } from "./components/shell";
import { UpdatePrompt } from "./components/UpdatePrompt";
import { Toaster } from "./components/ui/sonner";
import { TooltipProvider } from "./components/ui/tooltip";
import { bootstrapSession } from "./lib/authActions";
import { useAuth } from "./lib/authStore";
import Account from "./pages/Account";
import ChangePassword from "./pages/ChangePassword";
import ForgotPassword from "./pages/ForgotPassword";
import Home from "./pages/Home";
import Login from "./pages/Login";
import CorteDetalhe from "./pages/cortes/CorteDetalhe";
import ContaHistorico from "./pages/perfis/ContaHistorico";
import KitHistorico from "./pages/perfis/KitHistorico";
import PerfilDetalhe from "./pages/perfis/PerfilDetalhe";
import PerfilNovo from "./pages/perfis/PerfilNovo";
import PerfisList from "./pages/perfis/PerfisList";
import ResetPassword from "./pages/ResetPassword";
import SecurityEvents from "./pages/SecurityEvents";
import Users from "./pages/Users";
import VerifyEmail from "./pages/VerifyEmail";

// Vitrine dos componentes da spec 005 (só em dev; o build de produção descarta o import).
const Showcase = import.meta.env.DEV ? lazy(() => import("./pages/_Showcase")) : null;

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
      <TooltipProvider>
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
              {/* Área logada: o AppShell é rota de layout (o menu não remonta ao navegar). */}
              <Route
                element={
                  <RequireAuth>
                    <AppShell />
                  </RequireAuth>
                }
              >
                <Route path="/app" element={<Home />} />
                <Route path="/app/conta" element={<Account />} />
                <Route path="/app/perfis" element={<PerfisList />} />
                <Route path="/app/perfis/novo" element={<PerfilNovo />} />
                <Route path="/app/perfis/:id" element={<PerfilDetalhe />} />
                <Route path="/app/perfis/:id/kit/historico" element={<KitHistorico />} />
                <Route path="/app/contas/:id/historico" element={<ContaHistorico />} />
                <Route path="/app/cortes/:id" element={<CorteDetalhe />} />
                <Route
                  path="/app/usuarios"
                  element={
                    <RequireOwner>
                      <Users />
                    </RequireOwner>
                  }
                />
                <Route
                  path="/app/seguranca"
                  element={
                    <RequireOwner>
                      <SecurityEvents />
                    </RequireOwner>
                  }
                />
              </Route>
              {Showcase && (
                <Route
                  path="/app/_showcase"
                  element={
                    <Suspense fallback={null}>
                      <Showcase />
                    </Suspense>
                  }
                />
              )}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          )}
        </BrowserRouter>
        {/* Fora das rotas: o aviso de versão nova aparece em qualquer tela (US3). */}
        <UpdatePrompt />
        <Toaster position="top-right" richColors closeButton />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
