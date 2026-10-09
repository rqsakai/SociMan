import { AssetsLista } from "@/components/estudio/AssetsLista";
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { usePerfilFiltro } from "@/lib/estudio";

// AI Studio › Avatares (spec 029, US1): os avatares da agência, com o perfil base e a situação do kit (025).
export default function Avatares() {
  const [perfil, setPerfil] = usePerfilFiltro();
  usePageMeta({ title: "Avatares", breadcrumbs: [{ label: "AI Studio" }] });
  return (
    <Page>
      <PageHeading title="Avatares" description="As personas dos vídeos, de todos os perfis e sem perfil, com o kit padrão de cada uma." />
      <AssetsLista
        tipos={["avatar"]}
        perfilFiltro={perfil}
        onPerfilFiltro={setPerfil}
        titulo="Avatares"
        descricao="Rosto, corpo-base, looks e poses. A situação do kit aparece em cada card."
      />
    </Page>
  );
}
