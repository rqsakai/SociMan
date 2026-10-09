/*
 * Título e trilha da página na barra superior do AppShell.
 *
 * Uso numa página dentro do AppShell:
 *   usePageMeta({ title: perfil.nome, breadcrumbs: [{ label: "Perfis", to: "/app/perfis" }] });
 *
 * - title: texto mostrado na barra (não é heading: a página continua com o próprio <h1>).
 * - breadcrumbs: itens ANTES da página atual; o último item da trilha é o próprio title.
 *   "Início" entra sozinho no começo.
 * - ativo: o `to` do item do menu que fica marcado (029: o detalhe do avatar marca "Avatares", que a
 *   rota /app/assets/:id sozinha não sabe).
 * Sem usePageMeta, a barra usa o item do menu que casa com a URL (nav.ts).
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export interface Crumb {
  label: string;
  to?: string;
}

export interface PageMeta {
  title: string;
  breadcrumbs?: Crumb[];
  ativo?: string;
}

const PageMetaContext = createContext<{
  meta: PageMeta | null;
  setMeta: (meta: PageMeta | null) => void;
} | null>(null);

export function PageMetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<PageMeta | null>(null);
  return <PageMetaContext.Provider value={{ meta, setMeta }}>{children}</PageMetaContext.Provider>;
}

export function useCurrentPageMeta(): PageMeta | null {
  return useContext(PageMetaContext)?.meta ?? null;
}

export function usePageMeta(meta: PageMeta) {
  const setMeta = useContext(PageMetaContext)?.setMeta;
  // serializa para não depender da identidade do objeto (literal novo a cada render)
  const key = JSON.stringify(meta);
  useEffect(() => {
    if (!setMeta) return;
    setMeta(JSON.parse(key) as PageMeta);
    return () => setMeta(null);
  }, [key, setMeta]);
}
