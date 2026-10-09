import { Download, ImageOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { papelLabel, type Ingrediente } from "@/lib/cenas";

// Ingredientes do "Ingredients to Video" (spec 010, FR-004): até 3 imagens, na ordem avatar →
// produto → cenário, cada uma com "Baixar" (original, link de mídia sem validade da 007).
export function Ingredientes({ itens }: { itens: Ingrediente[] }) {
  return (
    <Card className="gap-3 shadow-card" aria-labelledby="ingredientes-flow">
      <CardHeader>
        <CardTitle>
          <h2 id="ingredientes-flow">Ingredientes ({itens.length}/3)</h2>
        </CardTitle>
        <CardDescription>Imagens de referência para enviar ao Flow junto com o prompt.</CardDescription>
      </CardHeader>
      <CardContent>
        {itens.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <ImageOff className="size-4" aria-hidden="true" />
            Nenhuma imagem: escolha um avatar, um produto (do catálogo ou uma foto) ou um cenário com imagem.
          </p>
        ) : (
          <ul aria-label="Ingredientes" className="grid grid-cols-3 gap-3">
            {itens.map((i) => (
              <li key={`${i.papel}-${i.arquivoId ?? i.produtoVarianteId ?? i.produtoId ?? ""}`} className="min-w-0 space-y-1">
                <div className="aspect-square overflow-hidden rounded-md border bg-muted">
                  {i.thumbUrl ? <img src={i.thumbUrl} alt="" loading="lazy" className="size-full object-cover" /> : null}
                </div>
                <p className="truncate text-xs font-medium" title={i.nome}>
                  {papelLabel[i.papel]}
                </p>
                <p className="truncate text-xs text-muted-foreground" title={i.nome}>
                  {i.nome}
                  {i.largura && i.altura ? ` · ${i.largura}×${i.altura}` : ""}
                </p>
                <Button asChild size="sm" variant="outline" className="w-full px-2">
                  <a href={i.downloadUrl} download aria-label={`Baixar ${papelLabel[i.papel].toLowerCase()}: ${i.nome}`}>
                    <Download aria-hidden="true" />
                    Baixar
                  </a>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
