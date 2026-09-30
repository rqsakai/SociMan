/*
 * Atalhos do topo de Conteúdos (spec 014, US1; R10): um botão por recorte com a contagem do
 * `GET /api/conteudos/resumo` (mesmo perfil e conta dos filtros). O atalho ativo fica na URL
 * (`?atalho=`); clicar de novo tira.
 */
import { Skeleton } from "@/components/ui/skeleton";
import { atalhos, useResumo, type AtalhoId } from "@/lib/conteudos";
import { cn } from "@/lib/utils";
import { useFiltroUrl } from "./FiltrosConteudos";

// Atalhos que pedem atenção ficam em destaque quando têm itens.
const alerta: Partial<Record<AtalhoId, string>> = {
  aprovacao_pedida: "text-warning-foreground",
  a_postar: "text-primary",
  atrasados: "text-destructive",
  falharam: "text-destructive",
  vencidos: "text-warning-foreground",
  rascunhos_criados: "text-success",
};

export function AtalhosConteudos() {
  const [params, set] = useFiltroUrl();
  const perfil = params.get("perfil");
  const conta = params.get("conta");
  const resumo = useResumo({ ...(perfil ? { perfilId: [perfil] } : {}), ...(conta ? { contaId: conta } : {}) });
  const ativo = params.get("atalho");

  return (
    <div role="group" aria-label="Atalhos" className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
      {atalhos.map((a) => {
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
            {resumo.isPending ? (
              <Skeleton className="mt-1 h-6 w-8" />
            ) : (
              <span className={cn("text-xl font-bold tabular-nums", n ? alerta[a.id] : "text-muted-foreground")}>
                {n ?? "—"}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
