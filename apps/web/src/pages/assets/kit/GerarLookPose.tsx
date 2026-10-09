import { Lock, Sparkles } from "lucide-react";
import { useState } from "react";
import { GeracaoAberta } from "@/components/geracao/GeracaoAberta";
import { Button } from "@/components/ui/button";
import { activeFiles, type Asset } from "@/lib/assets";
import { passoDoKit } from "@/lib/padrao";
import { PedirPasso } from "./PedirPasso";

// "Gerar look" e "Gerar pose" (spec 025, US4, T040): 2 opções a partir do corpo-base (ou de uma pose
// ativa), com o rosto frontal como referência de identidade. Bloqueado até o kit ter o rosto frontal
// e o corpo-base. A escolhida entra como referência do look ou como pose, com o selo "gerado".
export function GerarLookPose({ asset, tipo }: { asset: Asset; tipo: "look" | "pose" }) {
  const passo = `avatar.${tipo}`;
  const info = passoDoKit(asset, passo);
  const [aberto, setAberto] = useState(false);
  const travado = asset.archived || asset.revogado;
  if (!asset.kit || !info) return null;
  const rotulo = tipo === "look" ? "Gerar look" : "Gerar pose";
  const poses = activeFiles(asset, "pose").map((f, i) => ({ imageId: f.image.id, nome: f.label ?? `Pose ${i + 1}` }));
  const geracao = info.geracaoAberta;

  return (
    <div className="space-y-3 rounded-lg border border-dashed p-3" data-testid={`gerar-${tipo}`}>
      {!info.aberto ? (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground" data-testid="motivo-bloqueio">
          <Lock className="size-4" aria-hidden="true" />
          {rotulo}: monte o kit até o corpo-base antes.
        </p>
      ) : aberto ? (
        <PedirPasso
          perfilId={asset.perfilId}
          alvoTipo="asset"
          alvoId={asset.id}
          passo={passo}
          n={2}
          rotulo={tipo === "look" ? { label: "Nome do look", hint: 'Ex.: "Cozinha".' } : { label: "Rótulo da pose", hint: 'Ex.: "apontando para o produto". Único entre as poses.' }}
          instrucao={{
            label: tipo === "look" ? "Roupa toda (inglês)" : "Pose e roupa vestida (inglês)",
            hint:
              tipo === "look"
                ? "Ex.: white linen shirt, light blue jeans, brown leather sandals."
                : "Ex.: pointing at a product on a kitchen counter, wearing a white linen shirt and jeans.",
            obrigatoria: true,
          }}
          quandoUsar={tipo === "pose"}
          base={{ label: "Base", opcoes: poses }}
          submitLabel={rotulo}
          disabled={travado}
          onCriada={() => setAberto(false)}
        />
      ) : (
        !travado && (
          <Button type="button" variant="outline" size="sm" onClick={() => setAberto(true)}>
            <Sparkles aria-hidden="true" />
            {rotulo}
          </Button>
        )
      )}
      {geracao && <GeracaoAberta resumo={geracao} alvoVersion={asset.version} titulo={tipo === "look" ? "Look em geração" : "Pose em geração"} disabled={travado} />}
    </div>
  );
}
