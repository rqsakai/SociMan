/*
 * Barra de filtros única (spec 024, R5, FR-034). Entra no slot `toolbar` da <DataTable> (que então
 * não desenha a própria busca) ou no topo do cartão quando a tela não é tabela.
 *
 * <FilterBar
 *   busca={{ valor: params.get("q") ?? "", onChange: (q) => set({ q: q || null }, { replace: true }) }}
 *   principais={<Field label="Perfil">{({ id }) => <NativeSelect id={id} … />}</Field>}
 *   mais={<>…os outros controles…</>}
 *   ativos={[{ chave: "perfil", rotulo: "Perfil", valor: "Receitas", limpar: () => set({ perfil: null }) },
 *            { chave: "tipo", rotulo: "Tipo", valor: "Proposta", limpar: …, mais: true }]}
 *   onLimpar={() => set({ q: null, perfil: null, tipo: null })}
 * />
 *
 * - busca: o campo "Buscar" (searchbox). A digitação fica local e o `onChange` só é chamado 300 ms
 *   depois da última tecla, já cortado em 100 caracteres (o `q` das rotas); um `valor` novo de fora
 *   (voltar, "Limpar filtros") substitui o texto;
 * - principais: até 3 controles rotulados (`Field` + `NativeSelect`), sempre visíveis;
 * - mais: os outros controles, num Sheet aberto por "Mais filtros (N)" (lateral; de baixo em < sm).
 *   N conta os ativos com `mais: true`;
 * - ativos: etiquetas "Rótulo: valor" com o botão "Remover filtro: Rótulo". Inclua a busca, se quiser
 *   a etiqueta dela;
 * - onLimpar: "Limpar filtros" (aparece com algum ativo). Sem a prop, chama o `limpar` de cada um;
 *   com o `useFiltroUrl`, prefira um patch só (`set({ a: null, b: null })`).
 * A aplicação é imediata: não há botão "Filtrar".
 */
import { Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export interface FiltroAtivo {
  chave: string;
  rotulo: string;
  valor: string;
  limpar: () => void;
  // o controle fica em "Mais filtros" (entra na contagem do botão)
  mais?: boolean;
}

export interface FilterBarProps {
  busca?: { valor: string; onChange: (valor: string) => void; placeholder?: string; rotulo?: string };
  principais?: ReactNode;
  mais?: ReactNode;
  ativos?: FiltroAtivo[];
  onLimpar?: () => void;
  className?: string;
}

export const BUSCA_DEBOUNCE_MS = 300;
export const BUSCA_MAX = 100;

// < sm (640 px) do Tailwind: o Sheet vem de baixo
const CELULAR = "(max-width: 639.98px)";

function useCelular(): boolean {
  return useSyncExternalStore(
    (avisar) => {
      const mq = window.matchMedia(CELULAR);
      mq.addEventListener("change", avisar);
      return () => mq.removeEventListener("change", avisar);
    },
    () => window.matchMedia(CELULAR).matches,
    () => false,
  );
}

function CampoBusca({ valor, onChange, placeholder, rotulo = "Buscar" }: NonNullable<FilterBarProps["busca"]>) {
  const [texto, setTexto] = useState(valor);
  const enviado = useRef(valor);
  // valor novo de fora (voltar, limpar): substitui a digitação
  useEffect(() => {
    enviado.current = valor;
    setTexto(valor);
  }, [valor]);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });
  useEffect(() => {
    const final = texto.trim() ? texto.slice(0, BUSCA_MAX) : "";
    if (final === enviado.current) return;
    const t = setTimeout(() => {
      enviado.current = final;
      onChangeRef.current(final);
    }, BUSCA_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [texto]);

  return (
    <div className="relative w-full sm:w-64">
      <Search
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        type="search"
        aria-label={rotulo}
        placeholder={placeholder ?? rotulo}
        value={texto}
        maxLength={BUSCA_MAX}
        onChange={(e) => setTexto(e.target.value)}
        className="pl-9"
      />
    </div>
  );
}

export function FilterBar({ busca, principais, mais, ativos = [], onLimpar, className }: FilterBarProps) {
  const celular = useCelular();
  const naGaveta = ativos.filter((a) => a.mais).length;
  const limparTudo = onLimpar ?? (() => ativos.forEach((a) => a.limpar()));

  return (
    <div className={cn("w-full min-w-0 space-y-3", className)}>
      <div className="flex flex-wrap items-end gap-3">
        {busca && <CampoBusca {...busca} />}
        {principais}
        {mais && (
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline">
                <SlidersHorizontal aria-hidden="true" />
                {naGaveta > 0 ? `Mais filtros (${naGaveta})` : "Mais filtros"}
              </Button>
            </SheetTrigger>
            <SheetContent side={celular ? "bottom" : "right"} className={cn(celular && "max-h-[85dvh]")}>
              <SheetHeader>
                <SheetTitle>Mais filtros</SheetTitle>
                <SheetDescription>A lista se atualiza ao mudar cada filtro.</SheetDescription>
              </SheetHeader>
              <div className="flex min-h-0 flex-col gap-4 overflow-y-auto px-4">{mais}</div>
              <SheetFooter>
                {ativos.length > 0 && (
                  <Button variant="outline" onClick={limparTudo}>
                    Limpar filtros
                  </Button>
                )}
              </SheetFooter>
            </SheetContent>
          </Sheet>
        )}
      </div>

      {ativos.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Filtros ativos" role="group">
          {ativos.map((a) => (
            <Badge key={a.chave} variant="secondary" className="h-7 gap-1 pr-1 pl-2.5 text-xs font-medium">
              <span className="max-w-56 truncate">
                {a.rotulo}: <strong className="font-semibold">{a.valor}</strong>
              </span>
              <button
                type="button"
                onClick={a.limpar}
                aria-label={`Remover filtro: ${a.rotulo}`}
                className="inline-flex size-5 items-center justify-center rounded-full text-muted-foreground hover:bg-background hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-hidden"
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            </Badge>
          ))}
          <Button variant="link" size="sm" className="h-7 px-1" onClick={limparTudo}>
            Limpar filtros
          </Button>
        </div>
      )}
    </div>
  );
}
