import { AssetsLista } from "@/components/estudio/AssetsLista";
import { PageHeading } from "@/components/PageHeading";
import { Page, usePageMeta } from "@/components/shell";
import { usePerfilFiltro } from "@/lib/estudio";

// AI Studio › Cenários (spec 029, US1): os ambientes da agência, com a cena padrão e as variações (025).
export default function Cenarios() {
  const [perfil, setPerfil] = usePerfilFiltro();
  usePageMeta({ title: "Cenários", breadcrumbs: [{ label: "AI Studio" }] });
  return (
    <Page>
      <PageHeading title="Cenários" description="Os ambientes dos vídeos, de todos os perfis e sem perfil." />
      <AssetsLista
        tipos={["cenario"]}
        perfilFiltro={perfil}
        onPerfilFiltro={setPerfil}
        titulo="Cenários"
        descricao="A cena padrão (9:16, sem pessoas) e as variações por rótulo."
      />
    </Page>
  );
}
