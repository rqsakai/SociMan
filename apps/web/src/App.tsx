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
import AssetDetalhe from "./pages/assets/AssetDetalhe";
import AssetHistorico from "./pages/assets/AssetHistorico";
import ContaHistorico from "./pages/perfis/ContaHistorico";
import KitHistorico from "./pages/perfis/KitHistorico";
import PerfilDetalhe from "./pages/perfis/PerfilDetalhe";
import PerfilNovo from "./pages/perfis/PerfilNovo";
import PerfisList from "./pages/perfis/PerfisList";
import ResetPassword from "./pages/ResetPassword";
import SecurityEvents from "./pages/SecurityEvents";
import Users from "./pages/Users";
import VerifyEmail from "./pages/VerifyEmail";
// 006-cortes-openshorts
import Calendario from "./pages/calendario/Calendario";
import CanalDetalhe from "./pages/canais/CanalDetalhe";
import CanaisList from "./pages/canais/CanaisList";
import Descobrir from "./pages/descobrir/Descobrir";
import EnvioDetalhe from "./pages/envios/EnvioDetalhe";
import EnviosList from "./pages/envios/EnviosList";
// 008-assistente-ia
import AssistenteIa from "./pages/ia/AssistenteIa";
import RegraDetalhe from "./pages/ia/RegraDetalhe";
// 014-central-de-conteudos
import ConteudoDetalhe from "./pages/conteudos/ConteudoDetalhe";
import Conteudos from "./pages/conteudos/Conteudos";
// 015-tiktok-rascunho
import ConexaoRetorno from "./pages/conexoes/Retorno";
import PublicacaoConfig from "./pages/configuracoes/Publicacao";
// 016-metricas-tiktok
import VideoMetricas from "./pages/metricas/VideoMetricas";
// 017-guia-de-comunicacao
import ContaGuia from "./pages/perfis/ContaGuia";
import ContaStudio from "./pages/perfis/ContaStudio";

// 009-mcp
import Agentes from "./pages/configuracoes/Agentes";
import Propostas from "./pages/propostas/Propostas";

// 019-analytics: /app/metricas carrega sob demanda (traz o ECharts, chunk `graficos`).
const Analytics = lazy(() => import("./pages/analytics/Analytics"));

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
              {/* spec 015: volta do login da TikTok, sem o layout do painel */}
              <Route
                path="/app/conexoes/retorno"
                element={
                  <RequireAuth>
                    <ConexaoRetorno />
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
                <Route path="/app/contas/:id/guia" element={<ContaGuia />} />
                <Route path="/app/contas/:id/studio" element={<ContaStudio />} />
                <Route path="/app/cortes/:id" element={<CorteDetalhe />} />
                <Route path="/app/assets/:id" element={<AssetDetalhe />} />
                <Route path="/app/assets/:id/historico" element={<AssetHistorico />} />
                <Route path="/app/fontes" element={<CanaisList />} />
                <Route path="/app/fontes/:id" element={<CanalDetalhe />} />
                <Route path="/app/descobrir" element={<Descobrir />} />
                <Route path="/app/envios" element={<EnviosList />} />
                <Route path="/app/envios/:id" element={<EnvioDetalhe />} />
                <Route path="/app/calendario" element={<Calendario />} />
                <Route path="/app/conteudos" element={<Conteudos />} />
                <Route path="/app/conteudos/:id" element={<ConteudoDetalhe />} />
                <Route
                  path="/app/metricas"
                  element={
                    <Suspense fallback={<p className="text-sm text-muted-foreground" aria-live="polite">Carregando…</p>}>
                      <Analytics />
                    </Suspense>
                  }
                />
                <Route path="/app/metricas/videos/:id" element={<VideoMetricas />} />
                <Route path="/app/assistente-ia" element={<AssistenteIa />} />
                <Route path="/app/assistente-ia/regras/:tipo" element={<RegraDetalhe />} />
                <Route path="/app/propostas" element={<Propostas />} />
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
                <Route
                  path="/app/configuracoes/publicacao"
                  element={
                    <RequireOwner>
                      <PublicacaoConfig />
                    </RequireOwner>
                  }
                />
                <Route
                  path="/app/configuracoes/agentes"
                  element={
                    <RequireOwner>
                      <Agentes />
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
