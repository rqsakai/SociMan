/*
 * Filtros na URL (spec 014 R10; movido para cá na spec 024). Voltar, recarregar e compartilhar o
 * link mantêm a lista. `prefixo` (ex.: "reg_") separa os filtros de duas listas na mesma tela: o
 * `params` devolvido só traz as chaves com o prefixo (já sem ele) e o `set` o acrescenta.
 */
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

// Cada filtro escolhido empilha no histórico ("Voltar" volta ao filtro anterior); só a busca
// digitada substitui a entrada (`replace`), para não empilhar a cada pausa. Vazio tira o parâmetro.
export function useFiltroUrl(prefixo = "") {
  const [todos, setParams] = useSearchParams();
  const params = useMemo(() => {
    if (!prefixo) return todos;
    const proprios = new URLSearchParams();
    for (const [k, v] of todos) if (k.startsWith(prefixo)) proprios.append(k.slice(prefixo.length), v);
    return proprios;
  }, [todos, prefixo]);
  const set = (patch: Record<string, string | null>, opts: { replace?: boolean } = {}) =>
    setParams(
      // parte da URL do momento, não dos params do render: no react-router 7 a navegação vai num
      // transition, e dois patches seguidos (ex.: período e logo o perfil) apagariam um ao outro
      () => {
        const next = new URLSearchParams(window.location.search);
        for (const [k, v] of Object.entries(patch)) {
          if (v) next.set(prefixo + k, v);
          else next.delete(prefixo + k);
        }
        return next;
      },
      { replace: Boolean(opts.replace) },
    );
  return [params, set] as const;
}
