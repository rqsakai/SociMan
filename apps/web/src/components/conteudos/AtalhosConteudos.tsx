/*
 * Atalhos do topo de Conteúdos (spec 014, US1; R10): um botão por recorte com a contagem do
 * `GET /api/conteudos/resumo` (mesmo perfil e conta dos filtros). O atalho ativo fica na URL
 * (`?atalho=`); clicar de novo tira. Mudar o atalho volta à página 1.
 *
 * Spec 024 (FR-023, R15): só aparecem os atalhos com contagem > 0 e o ativo na URL (mesmo com zero).
 * "Ver todos os atalhos" mostra os 11 (estado local); sem nenhum, "Nada pedindo ação agora".
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { atalhos, useFiltroConteudos, useResumo, type AtalhoId } from "@/lib/conteudos";
import { cn } from "@/lib/utils";

// Atalhos que pedem atenção ficam em destaque quando têm itens.
const alerta: Partial<Record<AtalhoId, string>> = {
  aprovacao_pedida: "text-warning-foreground",
  a_postar: "text-primary",
  atrasados: "text-destructive",
  falharam: "text-destructive",
  vencidos: "text-warning-foreground",
  rascunhos_criados: "text-success",
};

const GRADE = "grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2";

export function AtalhosConteudos() {
  const [params, set] = useFiltroConteudos();
  const perfil = params.get("perfil");
  const conta = params.get("conta");
  const resumo = useResumo({ ...(perfil ? { perfilId: [perfil] } : {}), ...(conta ? { contaId: conta } : {}) });
  const ativo = params.get("atalho");
  const [todos, setTodos] = useState(false);

  if (resumo.isPending) {
    return (
      <div aria-hidden="true" className={GRADE}>
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-16 rounded-xl" />
        ))}
      </div>
    );
  }

  const comItens = atalhos.filter((a) => (resumo.data?.[a.campo] ?? 0) > 0 || a.id === ativo);
  const visiveis = todos ? atalhos : comItens;
  const escondidos = atalhos.length - comItens.length;

  return (
    <div className="space-y-2">
      {visiveis.length > 0 && (
        <div role="group" aria-label="Atalhos" className={GRADE}>
          {visiveis.map((a) => {
            const n = resumo.data?.[a.campo];
            const on = ativo === a.id;
            return (
              <button
                key={a.id}
                type="button"
                aria-pressed={on}
                onClick={() => set({ atalho: on ? null : a.id })}
                className={cn(
                  "flex flex-col items-start rounded-xl bg-card px-3 py-2 text-left shadow-card ring-1 ring-transparent transition hover:ring-primary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  on && "bg-primary/10 ring-primary",
                )}
              >
                <span className="text-xs text-muted-foreground">{a.label}</span>
                <span className={cn("text-xl font-bold tabular-nums", n ? alerta[a.id] : "text-muted-foreground")}>
                  {n ?? "—"}
                </span>
              </button>
            );
          })}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {comItens.length === 0 && !todos && <p className="text-muted-foreground">Nada pedindo ação agora.</p>}
        {escondidos > 0 && (
          <Button type="button" variant="link" size="sm" className="h-7 px-0" aria-expanded={todos} onClick={() => setTodos((t) => !t)}>
            {todos ? "Ver só os atalhos com itens" : "Ver todos os atalhos"}
          </Button>
        )}
      </div>
    </div>
  );
}
