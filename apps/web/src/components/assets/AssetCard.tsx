import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { type AssetSummary, tipoLabel } from "../../lib/assets";
import { PerfilBaseSelo } from "@/components/estudio/PerfilBaseSelo";
import { kitStatusLabel, kitStatusTone } from "@/lib/padrao";
import { AssetThumb } from "./AssetThumb";

// Card da grade da biblioteca: miniatura (ou iniciais), nome, tipo, perfil base (029), situação do
// kit (025) e os selos "Em uso" e "Arquivado".
// O card inteiro é o link para o detalhe (/app/assets/:id).
export function AssetCard({ asset }: { asset: AssetSummary }) {
  return (
    <li className="min-w-0">
      <Link
        to={`/app/assets/${asset.id}`}
        aria-label={`${asset.name} (${tipoLabel[asset.tipo]})`}
        className="group block overflow-hidden rounded-xl border bg-card shadow-card transition-shadow outline-none hover:shadow-md focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <div className="aspect-square bg-muted">
          <AssetThumb name={asset.name} tipo={asset.tipo} cover={asset.cover} />
        </div>
        <div className="space-y-1.5 p-3">
          <p className="truncate font-semibold group-hover:underline">{asset.name}</p>
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant="secondary">{tipoLabel[asset.tipo]}</Badge>
            {asset.inUse && <Badge className="bg-success text-success-foreground">Em uso</Badge>}
            <PerfilBaseSelo item={asset} />
            {asset.kitStatus && (
              <Badge className={kitStatusTone[asset.kitStatus]} data-testid="kit-status">
                Kit: {kitStatusLabel[asset.kitStatus].toLowerCase()}
              </Badge>
            )}
            {asset.archived && <Badge className="bg-dark text-dark-foreground">Arquivado</Badge>}
          </div>
          {asset.tags.length > 0 && (
            <p className="truncate text-xs text-muted-foreground">{asset.tags.map((t) => `#${t}`).join(" ")}</p>
          )}
        </div>
      </Link>
    </li>
  );
}
