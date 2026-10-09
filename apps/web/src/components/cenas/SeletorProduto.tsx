import { useQuery } from "@tanstack/react-query";
import { Package, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import type { CenaProdutoRef } from "@/lib/cenas";
import { perfilNomeDe, TETO_TEXTO, usePerfisTodos, useProdutosOpcoes } from "@/lib/estudio";
import { estadoProdutoLabel, produtoKey, variantesAtivas, type ProdutoEstado } from "@/lib/produtos";

export interface EscolhaProduto {
  produtoId: string | null;
  produtoVarianteId: string | null;
}

// Seletor do catálogo para a cena (spec 012, US4, T039; FR-020/FR-025): só os produtos aprovados e
// não arquivados do perfil, mais o já ligado (que pode ter saído de `aprovado`, com o estado no
// rótulo). A variante é opcional (vazio = a primeira ativa) e só lista as ativas com recorte, com a
// miniatura do recorte escolhido ao lado. Spec 029: os aprovados da agência inteira (qualquer perfil
// base), com o perfil ao lado do nome, e "+ Novo produto" (`onNovo`, o diálogo fica na página).
export function SeletorProduto({
  perfilBase,
  valor,
  atual,
  onChange,
  disabled,
  onNovo,
}: {
  valor: EscolhaProduto;
  atual?: CenaProdutoRef | null;
  onChange: (v: EscolhaProduto) => void;
  disabled?: boolean;
  onNovo?: () => void;
  // os aprovados deste perfil base aparecem primeiro
  perfilBase?: string | null;
}) {
  const perfis = usePerfisTodos();
  const aprovados = useProdutosOpcoes("aprovados", perfilBase);
  const produto = useQuery({ queryKey: produtoKey(valor.produtoId ?? ""), queryFn: () => api.produtos.ver(valor.produtoId!), enabled: Boolean(valor.produtoId) });

  const opcoes = (aprovados.itens ?? []).map((p) => ({ id: p.id, nome: `${p.nomeComercial ?? p.name} · ${perfilNomeDe(p, perfis.data)}` }));
  if (atual && !opcoes.some((o) => o.id === atual.id)) {
    const fora = atual.estado !== "aprovado" ? ` (${estadoProdutoLabel[atual.estado as ProdutoEstado] ?? atual.estado})` : "";
    opcoes.unshift({ id: atual.id, nome: `${atual.nomeComercial ?? atual.nome}${fora}` });
  }
  const variantes = produto.data ? variantesAtivas(produto.data).filter((v) => v.recorte) : [];
  const escolhida = variantes.find((v) => v.id === valor.produtoVarianteId) ?? variantes[0];
  const miniatura = escolhida?.recorte?.thumbUrl ?? (atual?.id === valor.produtoId ? atual?.variante?.thumbUrl : null) ?? null;

  return (
    <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" data-testid="seletor-produto">
      <Field
        label="Produto do catálogo"
        action={
          onNovo ? (
            <Button type="button" variant="ghost" size="xs" onClick={onNovo}>
              <Plus aria-hidden="true" />
              Novo produto
            </Button>
          ) : undefined
        }
        hint={aprovados.truncado
            ? TETO_TEXTO
            : aprovados.itens && opcoes.length === 0
              ? "Nenhum produto aprovado na agência."
              : "Só produtos aprovados. Um produto novo só aparece depois de aprovado."}
      >
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
