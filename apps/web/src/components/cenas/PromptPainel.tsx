import { Lock, Radio } from "lucide-react";
import { CopyButton } from "@/components/assets/CopyButton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { parteLabel, type CenaPrompt, type CenaStatus } from "@/lib/cenas";

// Prompt montado pela API (spec 010, FR-003): o texto exato a copiar para o Flow, as partes na ordem
// fixa (avatar → regras → ação → cenário → câmera → estilo → áudio e fala) e o negative prompt.
// "ao vivo" em rascunho; "congelado" em pronta/usada (Q3).
export function PromptPainel({ prompt, status }: { prompt: CenaPrompt; status: CenaStatus }) {
  return (
    <Card className="gap-3 shadow-card" aria-labelledby="prompt-flow">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <h2 id="prompt-flow">Prompt para o Flow</h2>
          {prompt.congelado ? (
            <Badge className="bg-info text-info-foreground">
              <Lock aria-hidden="true" />
              congelado
            </Badge>
          ) : (
            <Badge variant="outline">
              <Radio aria-hidden="true" />
              ao vivo
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          {prompt.congelado
            ? `Fixo desde que a cena ficou ${status === "usada" ? "pronta" : status}: mudanças no avatar ou no cenário não entram sem "Remontar prompt".`
            : "Acompanha o avatar e o cenário enquanto a cena é rascunho. Em inglês; a fala fica em português."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {prompt.partes.length > 0 && (
        <ol aria-label="Partes do prompt" className="space-y-2">
          {prompt.partes.map((p, i) => (
            <li key={`${p.parte}-${i}`} className="rounded-md border-l-4 border-primary/40 bg-muted/40 px-3 py-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase">{parteLabel[p.parte] ?? p.parte}</p>
              <p className="text-sm break-words whitespace-pre-wrap">{p.texto}</p>
            </li>
          ))}
        </ol>
        )}
        <div className="space-y-1">
          <p className="text-xs font-semibold text-muted-foreground uppercase">Texto completo</p>
          <pre data-testid="prompt-texto" className="max-h-64 overflow-y-auto rounded-md border bg-card p-3 font-mono text-xs break-words whitespace-pre-wrap">
            {prompt.texto}
          </pre>
          <CopyButton text={prompt.texto} label="Copiar prompt" copiedLabel="Prompt copiado" />
        </div>
        <div className="space-y-1">
          <p className="text-xs font-semibold text-muted-foreground uppercase">Negative prompt</p>
          <pre data-testid="prompt-negative" className="rounded-md border bg-card p-3 font-mono text-xs break-words whitespace-pre-wrap">
            {prompt.negative}
          </pre>
          <CopyButton text={prompt.negative} label="Copiar negative prompt" copiedLabel="Negative prompt copiado" />
        </div>
      </CardContent>
    </Card>
  );
}
