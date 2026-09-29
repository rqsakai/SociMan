import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ConsentBanner } from "./components/ConsentBanner";
import { RequireAuth } from "./components/RequireAuth";
import { bootstrapSession } from "./lib/authActions";
import { useAuth } from "./lib/authStore";
import AppHome from "./pages/AppHome";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ResetPassword from "./pages/ResetPassword";
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
  // Restaura a sessão no reload via cookie de refresh (access token é só memória).
  useEffect(() => {
    void bootstrapSession();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route
            path="/app"
            element={
              <RequireAuth>
                <AppHome />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <ConsentBanner />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
