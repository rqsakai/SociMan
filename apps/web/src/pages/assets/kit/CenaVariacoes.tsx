import { Lock, Sparkles } from "lucide-react";
import { useState } from "react";
import type { RunAction } from "@/components/assets/AssetFileCard";
import { PosesGrid } from "@/components/assets/PosesGrid";
import { PedirGeracao } from "@/components/geracao/PedirGeracao";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Asset } from "@/lib/assets";
import { arquivoDoSlot, kitStatusTexto, kitStatusTone, passoDoKit } from "@/lib/padrao";
import { PedirPasso } from "./PedirPasso";

// Cenário padrão (spec 025, US5, T043): a "Cena" (2 opções 9:16 de 768×1344, sem pessoas, pelo prompt
// do ambiente ou por uma foto; pedir de novo troca a cena) e as "Variações" por rótulo, derivadas da
// cena escolhida. "Gerar variação" fica bloqueado sem cena; rótulo repetido (sem diferença de caixa)
// a API recusa. O andamento e as opções de cena e de variação ficam em "Gerações deste cenário" (021).
export function CenaVariacoes({ asset, run }: { asset: Asset; run: RunAction }) {
  const [variando, setVariando] = useState(false);
  const kit = asset.kit;
  if (!kit) return null;
  const slot = kit.slots.find((s) => s.slot === "cena");
  const cena = arquivoDoSlot(asset, slot?.fileId ?? null);
  const passoCena = passoDoKit(asset, "cenario.cena");
  const passoVar = passoDoKit(asset, "cenario.variacao");
  const travado = asset.archived;

  return (
    <>
      <Card className="shadow-card" aria-labelledby="cena-titulo" data-testid="cenario-cena">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            <h2 id="cena-titulo">Cena</h2>
            <Badge className={asset.kitStatus ? kitStatusTone[asset.kitStatus] : "bg-secondary text-secondary-foreground"} data-testid="kit-status">
              {kitStatusTexto(asset.kitStatus)}
            </Badge>
          </CardTitle>
          <CardDescription>A imagem padrão do ambiente, vertical (768×1344), sem pessoas e com área livre para o produto.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {cena ? (
            <figure className="max-w-xs space-y-1" data-testid="slot-arquivo-cena">
              <a href={cena.downloadUrl} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg border bg-muted">
                <img src={cena.image.urls.medium} alt="Cena do cenário" className="w-full object-cover" />
              </a>
              <figcaption className="text-xs text-muted-foreground">
                {cena.image.width}×{cena.image.height} · {cena.origemArquivo === "gerado" ? "gerado" : "enviado"}
              </figcaption>
            </figure>
          ) : (
            <p className="text-sm text-muted-foreground">Ainda sem cena escolhida.</p>
          )}
          <div className="space-y-3 border-t pt-4">
            <h3 className="font-semibold">Gerar cena</h3>
            <p className="text-sm text-muted-foreground">
              {travado
                ? "Restaure o cenário antes de gerar."
                : cena
                  ? "Pedir de novo gera opções novas; a escolhida troca a cena atual (a anterior fica arquivada)."
                  : "Você compara as 2 opções e escolhe uma em \"Gerações deste cenário\"."}
            </p>
            {passoCena?.geracaoAberta && (
              <p className="text-sm" role="status">
                Há uma geração de cena aberta: acompanhe e escolha em "Gerações deste cenário".
              </p>
            )}
            <PedirGeracao
              perfilId={asset.perfilId}
              alvoTipo="asset"
              alvoId={asset.id}
              passo="cenario.cena"
              nPadrao={2}
              nMax={2}
              tiposReferencia={["cenario", "fundo", "imagem"]}
              instrucaoOpcional
              instrucaoPlaceholder={asset.prompt ?? undefined}
              instrucaoHint='Opcional: vazio usa o "Prompt do ambiente". Descreva o ambiente, a luz e o clima. Ex.: quarto claro e aconchegante, sol da manhã'
              disabled={travado}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="shadow-card" aria-labelledby="variacoes-titulo" data-testid="cenario-variacoes">
        <CardHeader>
          <CardTitle>
            <h2 id="variacoes-titulo">Variações</h2>
          </CardTitle>
          <CardDescription>A mesma cena com uma mudança e um rótulo ("noite", "outro ângulo"). O rótulo é único neste cenário.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <PosesGrid asset={asset} role="variacao" run={run} empty="Nenhuma variação ainda." archivedLabel="Mostrar arquivadas" />
          {!passoVar?.aberto ? (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground" data-testid="motivo-bloqueio">
              <Lock className="size-4" aria-hidden="true" />
              Gerar variação: escolha a cena antes.
            </p>
          ) : variando ? (
            <PedirPasso
              perfilId={asset.perfilId}
              alvoTipo="asset"
              alvoId={asset.id}
              passo="cenario.variacao"
              n={2}
              rotulo={{ label: "Rótulo da variação", hint: 'Ex.: "noite".' }}
              instrucao={{ label: "O que muda (inglês)", hint: "Ex.: same kitchen at night, warm lamp light.", obrigatoria: true }}
              submitLabel="Gerar variação"
              disabled={travado}
              onCriada={() => setVariando(false)}
            />
          ) : (
            !travado && (
              <Button type="button" variant="outline" size="sm" onClick={() => setVariando(true)}>
                <Sparkles aria-hidden="true" />
                Gerar variação
              </Button>
            )
          )}
          {passoVar?.geracaoAberta && <p className="text-sm" role="status">As opções da variação aparecem em "Gerações deste cenário".</p>}
        </CardContent>
      </Card>
    </>
  );
}
