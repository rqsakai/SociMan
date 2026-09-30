/*
 * Volta do login da TikTok (spec 015, US1; T038; research R1). Página sem o layout do painel.
 *
 * A TikTok redireciona para /app/conexoes/retorno?code&state (ou ?error&error_description). Esta
 * página envia os parâmetros para POST /api/conexoes/retorno com a sessão do dono e, com sucesso,
 * volta para a aba Contas do perfil. Recusa (conta diferente, permissão faltando, login expirado)
 * aparece em pt-BR com "Tentar de novo".
 */
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Loader2, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { modosKey } from "@/lib/postagem";
import { errorText } from "@/lib/perfis";
import {
  abrirEm,
  conexaoErroTitulo,
  conexaoKey,
  conexaoVersionsKey,
  iniciarConexao,
  lerConexaoPendente,
  limparConexaoPendente,
} from "@/lib/publicacao";

export default function Retorno() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [retrying, setRetrying] = useState(false);
  const enviado = useRef(false);
  const pendente = lerConexaoPendente();

  useEffect(() => {
    document.title = "Conectando a conta · SociMan";
    // StrictMode monta duas vezes em dev: o `state` só vale uma vez, então envia uma vez só.
    if (enviado.current) return;
    enviado.current = true;
    const state = params.get("state") ?? "";
    if (!state) {
      setError(new ApiError(400, "state_invalido", "A TikTok voltou sem o código do login. Comece de novo pelo botão Conectar."));
      return;
    }
    const code = params.get("code");
    const err = params.get("error");
    const desc = params.get("error_description");
    void (async () => {
      try {
        const r = await api.conexoes.retorno({ state, ...(code ? { code } : {}), ...(err ? { error: err } : {}), ...(desc ? { errorDescription: desc } : {}) });
        limparConexaoPendente();
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: conexaoKey(r.contaId) }),
          queryClient.invalidateQueries({ queryKey: conexaoVersionsKey(r.contaId) }),
          queryClient.invalidateQueries({ queryKey: modosKey(r.contaId) }),
        ]);
        const quem = r.conexao.username ? `@${r.conexao.username}` : "A conta";
        toast.success(`${quem} conectada à TikTok.`);
        void navigate(`/app/perfis/${r.perfilId}?aba=contas`, { replace: true });
      } catch (e) {
        setError(e);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function tentarDeNovo() {
    if (!pendente) return;
    setRetrying(true);
    try {
      await iniciarConexao(pendente.contaId, pendente.perfilId);
    } catch (e) {
      setError(e);
      setRetrying(false);
    }
  }

  const code = error instanceof ApiError ? error.code : null;
  const titulo = (code && conexaoErroTitulo[code]) || "Não foi possível conectar a conta";
  const outroEndereco = abrirEm(error);
  const diferente = error instanceof ApiError && error.code === "conta_diferente" ? error.details : null;
  const faltando = error instanceof ApiError && error.code === "escopo_faltando" && Array.isArray(error.details.faltando) ? (error.details.faltando as string[]) : [];

  return (
    <main className="flex min-h-svh items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md shadow-card">
        <CardHeader>
          <CardTitle>
            <h1>Conexão com a TikTok</h1>
          </CardTitle>
          <CardDescription>{error === null ? "Concluindo o login…" : "O login voltou com um problema."}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error === null ? (
            <p className="flex items-center gap-2 text-sm" aria-live="polite">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Conferindo a conta autorizada…
            </p>
          ) : (
            <Alert variant="destructive" role="alert">
              <CircleAlert aria-hidden="true" />
              <AlertTitle>{titulo}</AlertTitle>
              <AlertDescription>
                <p>{errorText(error)}</p>
                {diferente && typeof diferente.autorizado === "string" && typeof diferente.esperado === "string" && (
                  <p>
                    Você autorizou @{String(diferente.autorizado).replace(/^@/, "")}, mas esta conta é @{String(diferente.esperado).replace(/^@/, "")}. Saia da
                    TikTok no navegador e entre com a conta certa. Nada foi guardado.
                  </p>
                )}
                {faltando.length > 0 && <p>Permissões que faltaram: {faltando.join(", ")}. Autorize todas na tela da TikTok.</p>}
                {outroEndereco && (
                  <p>
                    Abra o SociMan em{" "}
                    <a href={outroEndereco} className="font-medium underline">
                      {outroEndereco}
                    </a>{" "}
                    e conecte de novo.
                  </p>
                )}
              </AlertDescription>
            </Alert>
          )}
          {error !== null && (
            <div className="flex flex-wrap gap-2">
              {pendente && (
                <Button type="button" disabled={retrying} aria-busy={retrying} onClick={() => void tentarDeNovo()}>
                  {retrying ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
                  Tentar de novo
                </Button>
              )}
              <Button variant="outline" asChild>
                <Link to={pendente ? `/app/perfis/${pendente.perfilId}?aba=contas` : "/app/perfis"}>Voltar ao perfil</Link>
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
