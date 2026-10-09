import type { AssetFileEnviado } from "@sociman/contract";
import { Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { GeracaoAberta } from "@/components/geracao/GeracaoAberta";
import { IaSelo } from "@/components/ia/IaSelo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Asset } from "@/lib/assets";
import { useCriarGeracao } from "@/lib/geracoes";
import { derivadosTexto, kitStatusTexto, kitStatusTone, origemLabel, passoDoKit, PASSOS_KIT, type AvisoDerivados } from "@/lib/padrao";
import { formatDateTime } from "@/lib/tz";
import { PerfilBaseGeracao } from "@/components/estudio/PerfilBaseField";
import { SlotCard } from "./SlotCard";

// "Kit padrão" do avatar (spec 025, US1/US6, T019; FR-031): a situação do kit, os 4 passos de imagem
// em ordem (o par 3/4 num passo só), a checagem de identidade (pedida pelo servidor quando os 5
// slots ficam prontos; "Checar de novo" quando ela falhou ou está pendente), a descrição para prompts
// que a checagem escreveu e o aviso de derivados depois de trocar um slot.
export function KitAvatar({ asset, refresh }: { asset: Asset; refresh: () => Promise<void> }) {
  const kit = asset.kit;
  const [derivados, setDerivados] = useState<AvisoDerivados[]>([]);
  const criar = useCriarGeracao();
  const [perfilBase, setPerfilBase] = useState<string | null>(asset.perfilId ?? null);
  if (!kit) return null;
  const identidadePasso = passoDoKit(asset, "avatar.identidade");
  const checagem = identidadePasso?.geracaoAberta ?? null;
  const temConsentimento = Boolean(asset.consentimento?.registradoEm) && !asset.revogado;
  const travado = asset.archived || asset.revogado;

  async function enviado(r: AssetFileEnviado) {
    setDerivados(r.avisos ?? []);
    toast.success(r.checagemGeracaoId ? "Imagem no slot. A checagem de identidade foi pedida." : "Imagem no slot.");
    await refresh();
  }

  async function checarDeNovo() {
    try {
      await criar.mutateAsync({ alvoTipo: "asset", alvoId: asset.id, passo: "avatar.identidade", instrucao: "", perfilBaseId: perfilBase });
      toast.success("Checagem pedida.");
    } catch {
      // erro no alerta
    }
  }

  return (
    <Card className="shadow-card" aria-labelledby="kit-titulo" data-testid="kit-padrao">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <h2 id="kit-titulo">Kit padrão</h2>
          <Badge className={asset.kitStatus ? kitStatusTone[asset.kitStatus] : "bg-secondary text-secondary-foreground"} data-testid="kit-status">
            {kitStatusTexto(asset.kitStatus)}
          </Badge>
          {asset.origem && (
            <Badge variant="outline" data-testid="kit-origem">
              {origemLabel[asset.origem]}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Rosto de origem, rosto frontal, rostos 3/4 e corpo-base, nesta ordem: cada passo abre depois que o anterior foi escolhido. Com os
          5 slots, a IA confere a identidade de cada imagem (nota de 0 a 10) e escreve a descrição para prompts.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {derivados.map((d, i) => (
          <Alert key={i} data-testid="aviso-derivados">
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>Derivados feitos com a imagem anterior</AlertTitle>
            <AlertDescription>
              {derivadosTexto(d.itens)} saíram da imagem que você trocou. Nada foi apagado nem gerado de novo: refaça os que precisar.
            </AlertDescription>
          </Alert>
        ))}

        <ol className="grid gap-4 xl:grid-cols-2" aria-label="Passos do kit">
          {PASSOS_KIT.map((c, i) => (
            <SlotCard key={c.passo} asset={asset} config={c} numero={i + 1} temConsentimento={temConsentimento} onEnviado={enviado} />
          ))}
        </ol>

        <section aria-label="Checagem de identidade" className="space-y-3 rounded-xl border p-4" data-testid="checagem-identidade">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">5. Checagem de identidade</h3>
            {asset.identidade?.data && (
              <span className="text-xs text-muted-foreground">
                {asset.identidade.modelo ? `${asset.identidade.modelo} · ` : ""}
                {formatDateTime(asset.identidade.data)}
              </span>
            )}
          </div>
          {!identidadePasso?.aberto && !asset.identidade && identidadePasso?.motivo && (
            <p className="text-sm text-muted-foreground" data-testid="motivo-bloqueio">
              {identidadePasso.motivo}
            </p>
          )}
          {checagem && <GeracaoAberta resumo={checagem} disabled={travado} />}
          {kit.checagemPendente && !checagem && (
            <div className="space-y-2" role="status">
              <p className="text-sm">Checagem pendente: os 5 slots estão prontos, mas a identidade ainda não foi conferida.</p>
              {!travado && <PerfilBaseGeracao value={perfilBase} onChange={setPerfilBase} />}
              {!travado && (
                <Button type="button" variant="outline" size="sm" disabled={criar.isPending} aria-busy={criar.isPending} onClick={() => void checarDeNovo()}>
                  {criar.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
                  Checar de novo
                </Button>
              )}
            </div>
          )}
          {criar.isError && <ApiErrorAlert error={criar.error} />}
          {asset.identidade && (
            <p className="text-sm text-muted-foreground">As notas aparecem em cada slot acima. Nota abaixo de 7 põe o kit em "Atenção".</p>
          )}
          {kit.descricaoNaoAplicada && (
            <Alert data-testid="descricao-nao-aplicada">
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>Descrição sugerida não aplicada</AlertTitle>
              <AlertDescription>
                Ela tinha palavras proibidas do guia de comunicação ({kit.descricaoNaoAplicada.proibidas.join(", ")}). A descrição anterior
                continua.
              </AlertDescription>
            </Alert>
          )}
          {asset.prompt && (
            <div className="space-y-1.5" data-testid="kit-descricao">
              <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                Descrição para prompts {asset.identidade?.geracaoId && <IaSelo />}
              </p>
              <p className="rounded-lg bg-muted/50 p-3 text-sm whitespace-pre-wrap" lang="en">
                {asset.prompt}
              </p>
              <p className="text-xs text-muted-foreground">Edite no campo "Descrição para prompts" do cartão "Dados". Uma nova checagem reescreve o texto (o anterior fica no histórico).</p>
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
