/*
 * "Testar guia" (spec 017, US3): gera 3 títulos/legendas de exemplo para um conteúdo escolhido, com
 * o guia do formulário (ainda não salvo). Nada é gravado além da chamada no registro: nenhum
 * conteúdo muda e o guia não ganha versão. Formulário inválido volta como 400 por campo (o erro vai
 * para o formulário, sem chamar a IA).
 */
import { ApiError, type Conta, type GuiaCampos, type IaChamada } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Loader2 } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import type { Nivel } from "@/lib/guia";
import { iaErroTexto } from "@/lib/ia";
import { contaPlatformText } from "@/lib/perfis";
import { ProibidasMarcadas } from "./ProibidasMarcadas";

export function TestarGuiaDialog({
  perfilId,
  nivel,
  contaId,
  contas,
  guia,
  onErroGuia,
}: {
  perfilId: string;
  nivel: Nivel;
  // Guia da conta: a conta é fixa.
  contaId?: string;
  contas: Conta[];
  guia: GuiaCampos;
  // 400 de validação do guia do formulário: o formulário mostra por campo.
  onErroGuia: (err: unknown) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const ativas = contas.filter((c) => !c.archived);
  // Sugere a 1ª conta ativa.
  const sugerida = contaId ?? (ativas.find((c) => c.status === "ativa") ?? ativas[0])?.id ?? "";
  const [conta, setConta] = useState(sugerida);
  const [conteudoId, setConteudoId] = useState("");
  const [testando, setTestando] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const [chamada, setChamada] = useState<IaChamada | null>(null);

  const conteudos = useQuery({
    queryKey: ["guia-testar-conteudos", perfilId],
    queryFn: () => api.conteudos.list({ perfilId: [perfilId], limit: 50 }),
    enabled: aberto,
  });
  const escolhido = conteudoId || conteudos.data?.items[0]?.id || "";

  async function testar() {
    setErro(null);
    setTestando(true);
    try {
      const out = await api.ia.guiaTestar({
        perfilId,
        nivel,
        contaId: contaId ?? conta,
        alvo: { entityType: "conteudo", entityId: escolhido },
        guia,
      });
      setChamada(out.chamada);
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error" && err.details.fields) {
        onErroGuia(err);
        setAberto(false);
        return;
      }
      setErro(err);
    } finally {
      setTestando(false);
    }
  }

  const variacoes = chamada?.proposta?.variacoes ?? [];
  const proibidas = chamada?.proibidas ?? [];

  return (
    <Dialog
      open={aberto}
      onOpenChange={(open) => {
        setAberto(open);
        if (!open) {
          setChamada(null);
          setErro(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          <FlaskConical aria-hidden="true" />
          Testar guia
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Testar o guia</DialogTitle>
          <DialogDescription>
            Gera 3 exemplos de título e legenda com o guia do formulário, sem salvar. Nenhum conteúdo muda.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Conteúdo">
            {({ id }) => (
              <NativeSelect id={id} value={escolhido} disabled={!conteudos.data} onChange={(e) => setConteudoId(e.target.value)}>
                {conteudos.data?.items.length === 0 && <option value="">Nenhum conteúdo neste perfil</option>}
                {conteudos.data?.items.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.titulo || "(sem título)"}
                    {c.origem === "corte" ? " · corte" : " · vídeo próprio"}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Conta">
            {({ id }) => (
              <NativeSelect id={id} value={contaId ?? conta} disabled={Boolean(contaId)} onChange={(e) => setConta(e.target.value)}>
                {ativas.length === 0 && <option value="">Nenhuma conta ativa</option>}
                {(contaId ? contas.filter((c) => c.id === contaId) : ativas).map((c) => (
                  <option key={c.id} value={c.id}>
                    @{c.handle} · {contaPlatformText(c)}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
        {conteudos.isError && <p className="text-sm text-destructive">{iaErroTexto(conteudos.error)}</p>}
        <div>
          <Button type="button" size="sm" disabled={testando || !escolhido || !(contaId ?? conta)} aria-busy={testando} onClick={() => void testar()}>
            {testando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <FlaskConical aria-hidden="true" />}
            {testando ? "Gerando…" : "Gerar 3 exemplos"}
          </Button>
        </div>

        {erro !== null && (
          <Alert variant="destructive">
            <AlertTitle>Não foi possível testar</AlertTitle>
            <AlertDescription>{iaErroTexto(erro)}</AlertDescription>
          </Alert>
        )}

        {chamada && (
          <div className="space-y-3">
            <ul aria-label="Variações geradas" className="grid gap-3 md:grid-cols-3">
              {variacoes.map((v, i) => (
                <li key={i} className="space-y-2 rounded-lg border bg-card p-3 text-sm break-words">
                  <p className="text-xs font-semibold text-muted-foreground uppercase">Variação {i + 1}</p>
                  <p className="font-medium">
                    <ProibidasMarcadas texto={v.titulo} proibidas={proibidas} />
                  </p>
                  <p className="whitespace-pre-wrap">
                    <ProibidasMarcadas texto={v.descricao} proibidas={proibidas} />
                  </p>
                  <p className="text-muted-foreground">
                    <ProibidasMarcadas texto={v.hashtags.join(" ")} proibidas={proibidas} />
                  </p>
                </li>
              ))}
            </ul>
            {chamada.explicacao && <p className="text-sm">{chamada.explicacao}</p>}
            {chamada.avisos.length > 0 && (
              <ul aria-label="Avisos da IA" className="list-disc space-y-0.5 pl-5 text-sm text-warning-foreground">
                {chamada.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
