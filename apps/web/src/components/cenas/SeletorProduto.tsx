import { useQuery } from "@tanstack/react-query";
import { Package } from "lucide-react";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import type { CenaProdutoRef } from "@/lib/cenas";
import { estadoProdutoLabel, produtoKey, produtosKey, variantesAtivas, type ProdutoEstado } from "@/lib/produtos";

export interface EscolhaProduto {
  produtoId: string | null;
  produtoVarianteId: string | null;
}

// Seletor do catálogo para a cena (spec 012, US4, T039; FR-020/FR-025): só os produtos aprovados e
// não arquivados do perfil, mais o já ligado (que pode ter saído de `aprovado`, com o estado no
// rótulo). A variante é opcional (vazio = a primeira ativa) e só lista as ativas com recorte, com a
// miniatura do recorte escolhido ao lado.
export function SeletorProduto({
  perfilId,
  valor,
  atual,
  onChange,
  disabled,
}: {
  perfilId: string;
  valor: EscolhaProduto;
  atual?: CenaProdutoRef | null;
  onChange: (v: EscolhaProduto) => void;
  disabled?: boolean;
}) {
  const aprovados = useQuery({
    queryKey: [...produtosKey(perfilId), "aprovados-cena"],
    queryFn: () => api.produtos.listar(perfilId, { status: ["aprovado"], arquivados: "false", limit: 100 }),
    enabled: perfilId !== "",
  });
  const produto = useQuery({ queryKey: produtoKey(valor.produtoId ?? ""), queryFn: () => api.produtos.ver(valor.produtoId!), enabled: Boolean(valor.produtoId) });

  const opcoes = (aprovados.data?.itens ?? []).map((p) => ({ id: p.id, nome: p.nomeComercial ?? p.name }));
  if (atual && !opcoes.some((o) => o.id === atual.id)) {
    const fora = atual.estado !== "aprovado" ? ` (${estadoProdutoLabel[atual.estado as ProdutoEstado] ?? atual.estado})` : "";
    opcoes.unshift({ id: atual.id, nome: `${atual.nomeComercial ?? atual.nome}${fora}` });
  }
  const variantes = produto.data ? variantesAtivas(produto.data).filter((v) => v.recorte) : [];
  const escolhida = variantes.find((v) => v.id === valor.produtoVarianteId) ?? variantes[0];
  const miniatura = escolhida?.recorte?.thumbUrl ?? (atual?.id === valor.produtoId ? atual?.variante?.thumbUrl : null) ?? null;

  return (
    <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" data-testid="seletor-produto">
      <Field label="Produto do catálogo" hint={aprovados.data && opcoes.length === 0 ? "Nenhum produto aprovado neste perfil." : "Só produtos aprovados."}>
        {({ id, describedBy }) => (
          <NativeSelect
            id={id}
            aria-describedby={describedBy}
            value={valor.produtoId ?? ""}
            disabled={disabled}
            onChange={(e) => onChange({ produtoId: e.target.value || null, produtoVarianteId: null })}
          >
            <option value="">Nenhum</option>
            {opcoes.map((o) => (
              <option key={o.id} value={o.id}>
                {o.nome}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label="Variante" hint="Vazio: a primeira variante ativa.">
        {({ id, describedBy }) => (
          <NativeSelect
            id={id}
            aria-describedby={describedBy}
            value={valor.produtoVarianteId ?? ""}
            disabled={disabled || !valor.produtoId}
            onChange={(e) => onChange({ produtoId: valor.produtoId, produtoVarianteId: e.target.value || null })}
          >
            <option value="">Primeira variante</option>
            {valor.produtoVarianteId && !variantes.some((v) => v.id === valor.produtoVarianteId) && (
              <option value={valor.produtoVarianteId}>{atual?.variante?.corPt ?? "Variante escolhida"}</option>
            )}
            {variantes.map((v, i) => (
              <option key={v.id} value={v.id}>
                {i + 1}. {v.corPt ?? "Sem cor"}
                {v.corEn ? ` (${v.corEn})` : ""}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <span className="flex size-14 items-center justify-center overflow-hidden rounded-md border bg-white" data-testid="produto-miniatura">
        {valor.produtoId && miniatura ? (
          <img src={miniatura} alt="Recorte da variante escolhida" className="size-full object-contain" />
        ) : (
          <Package className="size-5 text-muted-foreground" aria-hidden="true" />
        )}
      </span>
    </div>
  );
}
