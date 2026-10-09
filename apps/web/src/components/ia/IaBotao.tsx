import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { IA_AUSENTE_TEXTO } from "@/lib/ia";
import { claudeAusente, integracoesQuery } from "@/lib/integracoes";

// Botão "Melhorar com IA" no rótulo do campo (R11): abre e fecha o painel logo abaixo. Sem a chave
// do Claude (`GET /api/integracoes` diz `claude: ausente`), fica desabilitado com a explicação.
// O nome acessível é só o texto do botão: o rótulo do campo não entra, para o getByLabel("<campo>")
// dos e2e continuar achando só o campo.
export function IaBotao({ label = "Melhorar com IA", tipo, disabled }: { label?: string; tipo: string; disabled?: boolean }) {
  const integracoes = useQuery(integracoesQuery);
  const semIa = claudeAusente(integracoes.data);
  const botao = (
    <CollapsibleTrigger asChild>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-primary"
        disabled={semIa || disabled}
        data-testid={`ia-botao-${tipo}`}
      >
        <Sparkles aria-hidden="true" />
        {label}
      </Button>
    </CollapsibleTrigger>
  );
  if (!semIa) return botao;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* O botão desabilitado não recebe foco nem hover; o span leva a explicação. */}
        <span tabIndex={0} aria-label={IA_AUSENTE_TEXTO} className="inline-flex">
          {botao}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{IA_AUSENTE_TEXTO}</TooltipContent>
    </Tooltip>
  );
}
