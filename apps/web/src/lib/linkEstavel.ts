import { useEffect, useRef, useState } from "react";

// Links de mídia (`/api/midia/{token}`) têm validade, e a API assina um link NOVO a cada resposta.
// As telas recarregam os dados (polling de 2 s com geração aberta; foco da janela depois do
// `staleTime`), e trocar o `src` de um `<audio>`/`<video>` a cada resposta recria o elemento: o play
// e o download paravam em ~2 s. Este hook segura o link em uso enquanto ele vale e só troca quando:
// é outro item (`chave`), o link está para vencer (30 s) ou o navegador não conseguiu tocar (aí
// `onErro` pede um link novo ao `onRenovar`, uma vez por link, e aceita o próximo que chegar).
const MARGEM_MS = 30_000;

function vence(expiresAt: string | null | undefined): number {
  if (!expiresAt) return Number.POSITIVE_INFINITY;
  const t = new Date(expiresAt).getTime();
  return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
}

export interface LinkMidia {
  url: string;
  expiresAt?: string | null;
}

export function useLinkEstavel(link: LinkMidia | null, chave: string | null, onRenovar?: () => void) {
  const [atual, setAtual] = useState<LinkMidia | null>(link);
  const [chaveAtual, setChaveAtual] = useState(chave);
  const pedido = useRef<string | null>(null);

  if (chave !== chaveAtual) {
    setChaveAtual(chave);
    setAtual(link);
  } else if (link && (!atual || (link.url !== atual.url
             && (vence(atual.expiresAt) - Date.now() < MARGEM_MS || pedido.current === atual.url)))) {
    setAtual(link);
  }

  function renovar() {
    if (!atual || !onRenovar || pedido.current === atual.url) return;
    pedido.current = atual.url;
    onRenovar();
  }

  useEffect(() => {
    if (!atual) return;
    const falta = vence(atual.expiresAt) - Date.now();
    if (!Number.isFinite(falta)) return;
    const t = window.setTimeout(renovar, Math.max(0, falta - MARGEM_MS));
    return () => window.clearTimeout(t);
  }, [atual?.url, atual?.expiresAt]);

  return { url: atual?.url ?? null, onErro: renovar };
}
