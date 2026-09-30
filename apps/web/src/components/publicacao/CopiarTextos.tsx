import { ClipboardCopy } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { copyText, legendaDoDestino, textoCompleto, usaLegenda } from "@/lib/postagem";

// "Copiar textos" (spec 015, US2): os textos salvos no destino, prontos para colar no rascunho que
// a rede recebeu. Na TikTok (T102) copia a legenda final: descrição + linha em branco + hashtags.
export function CopiarTextos({
  textos,
  platform,
  size = "sm",
  variant = "default",
}: {
  textos: { titulo: string; descricao: string; hashtags: string[] };
  platform?: string;
  size?: "sm" | "default";
  variant?: "default" | "outline";
}) {
  async function copiar() {
    const texto = platform && usaLegenda(platform) ? legendaDoDestino(textos) : textoCompleto(textos);
    if (!texto.trim()) return toast.info("Este destino ainda não tem textos.");
    if (await copyText(texto)) toast.success("Textos copiados. Cole na legenda do rascunho no app.");
    else toast.error("Não foi possível copiar.");
  }
  return (
    <Button type="button" size={size} variant={variant} onClick={() => void copiar()}>
      <ClipboardCopy aria-hidden="true" />
      Copiar textos
    </Button>
  );
}
