import { useEffect, useState } from "react";
import { fontFamilyName, type FontOption } from "../../lib/marca";

// Carrega cada fonte do kit como FontFace (família interna `sociman-<ref>`, R7) a partir da URL
// da API (mesma origem: a CSP `default-src 'self'` cobre). Devolve o conjunto de refs já
// carregadas, para a prévia trocar da fonte genérica para a real quando ela chega.
const loaded = new Map<string, Promise<boolean>>();

function load(option: FontOption): Promise<boolean> {
  const cacheKey = `${option.ref}|${option.url}`;
  let promise = loaded.get(cacheKey);
  if (!promise) {
    const face = new FontFace(fontFamilyName(option.ref), `url(${JSON.stringify(option.url)})`);
    promise = face
      .load()
      .then((f) => {
        document.fonts.add(f);
        return true;
      })
      .catch(() => false);
    loaded.set(cacheKey, promise);
  }
  return promise;
}

export function useKitFonts(options: FontOption[]): Set<string> {
  const [ready, setReady] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    let alive = true;
    for (const option of options) {
      void load(option).then((ok) => {
        if (ok && alive) setReady((prev) => (prev.has(option.ref) ? prev : new Set(prev).add(option.ref)));
      });
    }
    return () => {
      alive = false;
    };
  }, [options]);
  return ready;
}

// Pilha CSS de uma fonte do kit: a real (se carregou) e um fallback parecido.
export function fontStack(ref: string, ready: Set<string>): string {
  const fallback = ref.includes("serif") && !ref.includes("sans") ? "serif" : "sans-serif";
  return ready.has(ref) ? `"${fontFamilyName(ref)}", ${fallback}` : fallback;
}
