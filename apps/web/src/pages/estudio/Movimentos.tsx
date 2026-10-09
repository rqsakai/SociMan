import { Move } from "lucide-react";
import { PageHeading } from "@/components/PageHeading";
import { EmptyState, Page, usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";

// AI Studio › Movimentos (spec 029, US1 cenário 3): "em breve". A clonagem de movimento (um vídeo de
// referência guia o gesto do avatar) chega na spec 030; a página não tem ação.
export default function Movimentos() {
  usePageMeta({ title: "Movimentos", breadcrumbs: [{ label: "AI Studio" }] });
  return (
    <Page>
      <PageHeading title="Movimentos" description="Clonagem de movimento para os avatares." />
      <section className="rounded-xl bg-card p-6 shadow-card" data-testid="movimentos-em-breve">
        <EmptyState
          icone={Move}
          titulo="Em breve"
          descricao="Você vai enviar um vídeo curto de referência (um gesto, um jeito de apontar ou de segurar o produto) e o avatar repete o movimento nas cenas. Chega com a spec 030."
          acao={<Badge variant="secondary">em breve</Badge>}
        />
      </section>
    </Page>
  );
}
