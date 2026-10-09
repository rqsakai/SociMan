import { AssetsLista } from "@/components/estudio/AssetsLista";
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { TIPOS_ASSETS, usePerfilFiltro } from "@/lib/estudio";

// AI Studio › Assets (spec 029, US1; Clarification 2): só imagem, sticker, marca d'água e fundo;
// avatares e cenários têm item próprio no menu.
export default function Assets() {
  const [perfil, setPerfil] = usePerfilFiltro();
  usePageMeta({ title: "Assets", breadcrumbs: [{ label: "AI Studio" }] });
  return (
    <Page>
      <PageHeading title="Assets" description="Imagens, stickers, marcas d'água e fundos da agência. Nada é apagado: arquive e restaure." />
      <AssetsLista
        tipos={TIPOS_ASSETS}
        perfilFiltro={perfil}
        onPerfilFiltro={setPerfil}
        titulo="Assets"
        descricao="Um arquivo por asset. O kit de marca escolhe o fundo e a marca d'água daqui."
      />
    </Page>
  );
}
