import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "./api";

// spec 009: o registro MCP só conhece o id do destino e aponta para `/app/conteudos?destino=<id>`.
// Na lista de conteúdos, busca o destino e troca a URL pelo detalhe do conteúdo, na aba da conta.
// Se o destino não existir (ou falhar), a lista segue normal.
export function useAbrirDestinoDaUrl(): void {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const destinoId = params.get("destino");
  useEffect(() => {
    if (!destinoId) return;
    let vivo = true;
    api.destinos
      .get(destinoId)
      .then(({ destino }) => {
        if (vivo) navigate(`/app/conteudos/${destino.conteudoId}?destino=${destinoId}`, { replace: true });
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [destinoId, navigate]);
}
