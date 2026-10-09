import { Badge } from "@/components/ui/badge";
import { perfilNomeDe, usePerfisTodos } from "@/lib/estudio";

// O perfil base ao lado do nome nas listas e nos cabeçalhos (spec 029, FR-002): "Sem perfil" quando não há.
export function PerfilBaseSelo({ item, className }: { item: { perfilId?: string | null; perfilNome?: string | null }; className?: string }) {
  const perfis = usePerfisTodos();
  return (
    <Badge variant="outline" className={className} data-testid="perfil-base-selo">
      {perfilNomeDe(item, perfis.data)}
    </Badge>
  );
}
