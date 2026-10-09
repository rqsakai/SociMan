import type { Integracoes } from "@sociman/contract";
import { api } from "./api";

export type { Integracoes } from "@sociman/contract";

// Estado das integrações (spec 006, T073): GET /api/integracoes nunca traz valor de chave; a UI
// só avisa quando o YouTube ou o Claude estão ausentes e mostra a cota do dia.
export const integracoesQuery = {
  queryKey: ["integracoes"] as const,
  queryFn: () => api.integracoes(),
  staleTime: 60_000,
};

export function youtubeAviso(i: Integracoes | undefined): { titulo: string; texto: string } | null {
  if (!i || i.youtube === "ok") return null;
  if (i.youtube === "ausente") {
    return {
      titulo: "O YouTube não está configurado",
      texto:
        "Sem a chave da API do YouTube (YOUTUBE_API_KEY no .env) não dá para cadastrar canais nem buscar vídeos. O envio avulso por link ou arquivo continua funcionando.",
    };
  }
  return {
    titulo: "A chave do YouTube foi recusada",
    texto: "A API do YouTube recusou a chave configurada. Troque a YOUTUBE_API_KEY no .env; o envio avulso continua funcionando.",
  };
}

export const claudeAusente = (i: Integracoes | undefined) => i?.claude === "ausente";
export const CLAUDE_AUSENTE_TEXTO =
  "A sugestão de textos precisa da chave do Claude (ANTHROPIC_API_KEY no .env). Os campos continuam editáveis à mão.";
