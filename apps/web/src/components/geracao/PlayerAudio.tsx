import type { Audio } from "../../lib/geracoes";
import { useLinkEstavel } from "../../lib/linkEstavel";

// Player nativo (spec 021, T054). O link do áudio tem validade e muda a cada resposta da API: o
// `useLinkEstavel` segura o link em uso enquanto vale (senão o polling cortava o play em ~2 s) e,
// se o navegador não conseguir tocar, pede um link novo (`onRenovar` recarrega o detalhe).
export function PlayerAudio({ audio, rotulo, onRenovar }: { audio: Audio; rotulo: string; onRenovar: () => void }) {
  const link = useLinkEstavel(audio.link, audio.id, onRenovar);
  return (
    <audio
      key={audio.id}
      controls
      preload="metadata"
      src={link.url ?? undefined}
      aria-label={rotulo}
      className="w-full"
      data-testid="player-audio"
      onError={link.onErro}
    />
  );
}
