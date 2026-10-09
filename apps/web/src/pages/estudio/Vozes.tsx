import { VozesLista } from "@/components/estudio/VozesLista";
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { usePerfilFiltro } from "@/lib/estudio";

// AI Studio › Vozes (spec 029, US1): as vozes da agência, com o estado e a sincronização (025).
export default function Vozes() {
  const [perfil, setPerfil] = usePerfilFiltro();
  usePageMeta({ title: "Vozes", breadcrumbs: [{ label: "AI Studio" }] });
  return (
    <Page>
      <PageHeading title="Vozes" description="As vozes de narração, de todos os perfis e sem perfil." />
      <VozesLista perfilFiltro={perfil} onPerfilFiltro={setPerfil} />
    </Page>
  );
}
