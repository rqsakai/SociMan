import { CenasLista } from "@/components/estudio/CenasLista";
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { usePerfilFiltro } from "@/lib/estudio";

// AI Studio › Cenas (spec 029, US1): as tomadas da agência, com o status (010).
export default function Cenas() {
  const [perfil, setPerfil] = usePerfilFiltro();
  usePageMeta({ title: "Cenas", breadcrumbs: [{ label: "AI Studio" }] });
  return (
    <Page>
      <PageHeading title="Cenas" description="As tomadas para o Google Flow, de todos os perfis e sem perfil." />
      <CenasLista perfilFiltro={perfil} onPerfilFiltro={setPerfil} />
    </Page>
  );
}
