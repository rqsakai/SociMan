import type { AssetSummary } from "../../lib/assets";
import { AssetCard } from "./AssetCard";

// Grade responsiva dos cards da biblioteca.
export function AssetGrid({ items }: { items: AssetSummary[] }) {
  return (
    <ul aria-label="Assets do perfil" className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {items.map((a) => (
        <AssetCard key={a.id} asset={a} />
      ))}
    </ul>
  );
}
