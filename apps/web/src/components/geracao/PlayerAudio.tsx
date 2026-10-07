import { useEffect, useRef } from "react";
import type { Audio } from "../../lib/geracoes";

// Player nativo (spec 021, T054). O link do áudio tem validade: ao vencer, ou se o navegador não
// conseguir tocar, pede um link novo (`onRenovar` recarrega o detalhe da geração). Pede uma vez
// por link, para não entrar em laço quando o erro não é de validade.
export function PlayerAudio({ audio, rotulo, onRenovar }: { audio: Audio; rotulo: string; onRenovar: () => void }) {
  const pedido = useRef<string | null>(null);
  const { url, expiresAt } = audio.link;

  function renovar() {
    if (pedido.current === url) return;
    pedido.current = url;
    onRenovar();
  }

  useEffect(() => {
    if (!expiresAt) return;
    const falta = new Date(expiresAt).getTime() - Date.now();
    if (!Number.isFinite(falta)) return;
    // Renova um pouco antes de vencer (30 s), para o play não pegar um link morto.
    const t = window.setTimeout(renovar, Math.max(0, falta - 30_000));
    return () => window.clearTimeout(t);
  }, [url, expiresAt]);

  return (
    <audio
      key={url}
      controls
      preload="metadata"
      src={url}
      aria-label={rotulo}
      className="w-full"
      data-testid="player-audio"
      onError={renovar}
    />
  );
}
