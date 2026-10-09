import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

// Copia o texto exato (sem trim nem formatação) para a área de transferência (FR-009, R9). Se o
// navegador recusar, mostra o texto numa Textarea somente leitura, já selecionada, com "Copie com
// Ctrl+C".
export function CopyButton({
  text,
  label,
  copiedLabel = "Copiado",
  size = "sm",
  variant = "outline",
  disabled,
}: {
  text: string;
  label: string;
  copiedLabel?: string;
  size?: "default" | "sm";
  variant?: "outline" | "ghost" | "default";
  disabled?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [fallback, setFallback] = useState(false);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(t);
  }, [copied]);

  useEffect(() => {
    if (fallback) areaRef.current?.select();
  }, [fallback]);

  async function copy() {
    try {
      if (!navigator.clipboard) throw new Error("sem clipboard");
      await navigator.clipboard.writeText(text);
      setFallback(false);
      setCopied(true);
    } catch {
      setFallback(true);
    }
  }

  return (
    <div className="space-y-2">
      <Button type="button" size={size} variant={variant} disabled={disabled} onClick={() => void copy()}>
        {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {label}
      </Button>
      <span role="status" className="sr-only">
        {copied ? copiedLabel : ""}
      </span>
      {fallback && (
        <div className="space-y-1">
          <Textarea
            ref={areaRef}
            readOnly
            value={text}
            aria-label={label}
            onFocus={(e) => e.currentTarget.select()}
            className="max-h-48 font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">Copie com Ctrl+C</p>
        </div>
      )}
    </div>
  );
}
