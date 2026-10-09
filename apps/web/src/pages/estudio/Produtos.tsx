import { ProdutosLista } from "@/components/estudio/ProdutosLista";
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { usePerfilFiltro } from "@/lib/estudio";

// AI Studio › Produtos (spec 029, US1): o catálogo do TikTok Shop da agência, com o status (012).
export default function Produtos() {
  const [perfil, setPerfil] = usePerfilFiltro();
  usePageMeta({ title: "Produtos", breadcrumbs: [{ label: "AI Studio" }] });
  return (
    <Page>
      <PageHeading title="Produtos" description="Os produtos do TikTok Shop, de todos os perfis e sem perfil." />
      <ProdutosLista perfilFiltro={perfil} onPerfilFiltro={setPerfil} />
    </Page>
  );
}
