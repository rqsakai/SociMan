import type { ImageRef } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Sparkles, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import type { AssetTipo } from "../../lib/assets";
import { useCriarGeracao, type Geracao, type GeracaoAlvo } from "../../lib/geracoes";
import { integracoesQuery } from "../../lib/integracoes";
import { LibraryImageDialog } from "../assets/LibraryImageDialog";
import { PerfilBaseGeracao } from "../estudio/PerfilBaseField";

const INSTRUCAO_MAX = 2000;

// Pedido de geração (spec 021, T027): instrução, foto de referência opcional escolhida da
// biblioteca do perfil e número de opções (1..nMax do passo). Reutilizável pela 025 e pela 012.
// Spec 029: `perfilId` é o perfil base do item (pode ser null), o padrão do "Perfil base desta geração".
export function PedirGeracao({
  perfilId,
  alvoTipo,
  alvoId,
  passo,
  nPadrao,
  nMax,
  tiposReferencia,
  disabled,
  instrucaoLabel = "Instrução",
  instrucaoHint,
  instrucaoOpcional = false,
  instrucaoPlaceholder,
  onCriada,
}: {
  perfilId: string | null;
  alvoTipo: GeracaoAlvo;
  alvoId: string;
  passo: string;
  nPadrao: number;
  nMax: number;
  // Sem tipos, não há foto de referência.
  tiposReferencia?: readonly AssetTipo[];
  disabled?: boolean;
  instrucaoLabel?: string;
  instrucaoHint?: string;
  // spec 025: no `cenario.cena`, vazio usa o prompt do ambiente do cenário
  instrucaoOpcional?: boolean;
  instrucaoPlaceholder?: string;
  onCriada?: (g: Geracao) => void;
}) {
  const [instrucao, setInstrucao] = useState("");
  const [referencia, setReferencia] = useState<{ image: ImageRef; nome: string } | null>(null);
  const [nOpcoes, setNOpcoes] = useState(Math.min(nPadrao, nMax));
  const [campoErro, setCampoErro] = useState<string | null>(null);
  const criar = useCriarGeracao();
  const [perfilBase, setPerfilBase] = useState<string | null>(perfilId);
  const integracoes = useQuery(integracoesQuery);
  const gerador = integracoes.data?.geracao;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const texto = instrucao.trim();
    if ((!instrucaoOpcional && texto.length < 1) || texto.length > INSTRUCAO_MAX) {
      setCampoErro(`Descreva o que gerar (até ${INSTRUCAO_MAX.toLocaleString("pt-BR")} caracteres)`);
      return;
    }
    setCampoErro(null);
    try {
      const g = await criar.mutateAsync({
        alvoTipo,
        alvoId,
        passo,
        perfilBaseId: perfilBase,
        instrucao: texto,
        referencias: referencia ? [referencia.image.id] : [],
        nOpcoes,
      });
      toast.success("Pedido enviado. As opções aparecem abaixo quando ficarem prontas.");
      setInstrucao("");
      setReferencia(null);
      onCriada?.(g);
    } catch {
      // o erro aparece no alerta (criar.error)
    }
  }

  const opcoes = Array.from({ length: nMax }, (_, i) => i + 1);
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate data-testid="pedir-geracao">
      {gerador?.gerador === "parado" && (
        <Alert>
          <AlertTitle>O gerador está parado</AlertTitle>
          <AlertDescription>O pedido entra na fila e começa quando o gerador voltar.</AlertDescription>
        </Alert>
      )}
      <PerfilBaseGeracao value={perfilBase} onChange={setPerfilBase} disabled={disabled} />
      <Field label={instrucaoLabel} hint={instrucaoHint} error={campoErro ?? undefined}>
        {({ id, describedBy, invalid }) => (
          <Textarea
            id={id}
            rows={3}
            value={instrucao}
            maxLength={INSTRUCAO_MAX}
            placeholder={instrucaoPlaceholder}
            disabled={disabled}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setInstrucao(e.target.value)}
          />
        )}
      </Field>

      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
        {tiposReferencia && tiposReferencia.length > 0 ? (
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Foto de referência (opcional)</p>
            <div className="flex flex-wrap items-center gap-3">
              {referencia ? (
                <div className="flex items-center gap-2" data-testid="referencia-escolhida">
                  <img src={referencia.image.urls.thumb} alt="" className="size-14 rounded-md border object-cover" />
                  <span className="max-w-48 truncate text-sm">{referencia.nome}</span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setReferencia(null)} disabled={disabled}>
                    <X aria-hidden="true" />
                    Tirar referência
                  </Button>
                </div>
              ) : (
                <span className="text-sm text-muted-foreground">Nenhuma foto escolhida.</span>
              )}
              {!disabled && (
                <LibraryImageDialog
                  perfilId={perfilId}
                  tipos={tiposReferencia}
                  value={referencia?.image.id ?? null}
                  onPick={(image, item) => setReferencia({ image, nome: item.label ? `${item.assetName}: ${item.label}` : item.assetName })}
                />
              )}
            </div>
          </div>
        ) : (
          <div />
        )}
        <Field label="Número de opções" className="sm:w-44">
          {({ id }) => (
            <NativeSelect id={id} value={nOpcoes} disabled={disabled || nMax <= 1} onChange={(e) => setNOpcoes(Number(e.target.value))}>
              {opcoes.map((n) => (
                <option key={n} value={n}>
                  {n === 1 ? "1 opção" : `${n} opções`}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
      </div>

      {criar.isError && <ApiErrorAlert error={criar.error} />}
      <Button type="submit" disabled={disabled || criar.isPending} aria-busy={criar.isPending}>
        {criar.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
        Gerar
      </Button>
    </form>
  );
}
