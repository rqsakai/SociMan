import { NovoAssetDialog } from "@/components/assets/NovoAssetMenu";
import type { NovoTipo } from "@/components/cenas/CenaForm";
import { NovoProdutoDialog } from "@/components/produtos/NovoProdutoDialog";
import type { Produto } from "@/lib/produtos";

export interface ItemCriado {
  tipo: NovoTipo;
  id: string;
  produto?: Produto;
}

// Criação no lugar (spec 029, US3, T029; FR-016/FR-017): o cadastro de avatar, cenário ou produto num
// diálogo, sem sair da cena. Nasce com o perfil base da cena (trocável no diálogo) e segue as regras
// do cadastro normal. Ao salvar chama `onCriado` (a página escolhe o item na cena); ao cancelar, nada
// é criado. A página o renderiza FORA do `<form>` da cena, para o submit do diálogo não salvar a cena.
export function NovoItemDialog({
  tipo,
  perfilId,
  onClose,
  onCriado,
}: {
  tipo: NovoTipo | null;
  perfilId: string | null;
  onClose: () => void;
  onCriado: (item: ItemCriado) => void;
}) {
  return (
    <>
      <NovoAssetDialog
        perfilId={perfilId}
        tipo={tipo === "avatar" || tipo === "cenario" ? tipo : null}
        onClose={onClose}
        onCreated={(id) => {
          if (tipo === "avatar" || tipo === "cenario") onCriado({ tipo, id });
        }}
      />
      <NovoProdutoDialog
        perfilId={perfilId}
        open={tipo === "produto"}
        onOpenChange={(o) => {
          if (!o) onClose();
        }}
        onCriado={(produto) => onCriado({ tipo: "produto", id: produto.id, produto })}
      />
    </>
  );
}
