/*
 * O modo wizard do vídeo guiado (spec 031, US3, T037; FR-014..016, FR-035, R9): um passo por vez,
 * pela etapa em que o roteiro está: Conversa (o chat e o plano; "Confirmar cenas" aprova o portão
 * do texto) → Narração → Quadros → Clipes → Final. Tudo em 1 versão, para aprovar ou "Não aprovo";
 * sem texto de prompt nem de fala (FR-015). Os portões e o modo automático ficam no avançado.
 */
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, TriangleAlert } from "lucide-react";
import { useState, type ComponentType } from "react";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { ETAPAS, etapaAtual, type Etapa } from "@/lib/roteiros";
import { cn } from "@/lib/utils";
import { OPCAO_TEXTO_CURTO, ajusteAberto, duracaoTexto, invalidarConversa, proximaDuracao, useGrade } from "@/lib/videoGuiado";
import type { EtapaProps } from "../etapas/comum";
import { ClipesWizard } from "./ClipesWizard";
import { Conversa } from "./Conversa";
import { FinalWizard } from "./FinalWizard";
import { NarracaoWizard } from "./NarracaoWizard";
import { QuadrosWizard } from "./QuadrosWizard";

const PASSOS: Record<Etapa, string> = { texto: "Conversa", narracao: "Narração", keyframes: "Quadros", clipes: "Clipes", final: "Final" };

export interface WizardProps extends EtapaProps {
  // O modal de cenas (US4, T042) entra aqui; sem ele, "Confirmar cenas" aprova o portão do texto.
  ModalCenas?: ComponentType<EtapaProps>;
}

export function Wizard({ ModalCenas, ...props }: WizardProps) {
  const { roteiro: r } = props;
  const atual = etapaAtual(r);
  const idx = ETAPAS.findIndex((e) => e.id === atual);
  const pronto = r.status === "pronto";

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="wizard">
      <nav aria-label="Passos do vídeo">
        <ol className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {ETAPAS.map((e, i) => {
            const feito = i < idx || pronto;
            const agora = i === idx && !pronto;
            return (
              <li key={e.id} aria-current={agora ? "step" : undefined} className={cn("flex items-center gap-1.5", agora ? "font-semibold text-foreground" : "text-muted-foreground")} data-testid={`passo-${e.id}`}>
                <span
                  className={cn(
                    "flex size-5 items-center justify-center rounded-full border text-[11px] tabular-nums",
                    feito && "border-success bg-success text-success-foreground",
                    agora && "border-primary bg-primary text-primary-foreground",
                  )}
                  aria-hidden="true"
                >
                  {feito ? "✓" : i + 1}
                </span>
                {PASSOS[e.id]}
                {feito && <span className="sr-only"> (feito)</span>}
              </li>
            );
          })}
        </ol>
      </nav>

      <AvisoFala {...props} />

      {atual === "texto" && <TextoWizard {...props} ModalCenas={ModalCenas} />}
      {atual !== "texto" && (
        <Card className="shadow-card" aria-labelledby="wizard-passo-titulo">
          <CardHeader>
            <h2 id="wizard-passo-titulo" className="text-base font-semibold">
              {PASSOS[atual]}
            </h2>
          </CardHeader>
          <CardContent>
            {atual === "narracao" && <NarracaoWizard {...props} />}
            {atual === "keyframes" && <QuadrosWizard {...props} />}
            {atual === "clipes" && <ClipesWizard {...props} />}
            {atual === "final" && <FinalWizard {...props} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function TextoWizard({ roteiro: r, rodar, travado, ModalCenas }: WizardProps) {
  const [busy, setBusy] = useState(false);
  const pronto = !travado && r.status === "aguardando_texto" && r.posicoes.length > 0;
  return (
    <>
      <Conversa roteiro={r} rodar={rodar} travado={travado} />
      {pronto &&
        (ModalCenas ? (
          <ModalCenas roteiro={r} rodar={rodar} travado={travado} />
        ) : (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/60 bg-warning/5 p-3" data-testid="aprovar-texto">
            <p className="min-w-0 flex-1 text-sm">O plano está montado. Confirme as cenas para a IA gerar a narração.</p>
            <Button
              type="button"
              disabled={busy}
              aria-busy={busy}
              onClick={async () => {
                setBusy(true);
                await rodar(() => api.roteiros.aprovar(r.id, r.version, "texto"), "Cenas confirmadas. A narração vem a seguir.");
                setBusy(false);
              }}
            >
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
              Confirmar cenas
            </Button>
          </div>
        ))}
    </>
  );
}

// T050 (FR-032, FR-033): a fala de uma cena não cabe na duração dela. Duas saídas: um texto mais
// curto (o "Não aprovo" da narração com essa opção; só com a narração esperando aprovação) ou uma
// duração maior (a próxima da grade, que refaz o plano a partir do texto).
function AvisoFala({ roteiro: r, rodar, travado }: EtapaProps) {
  const queryClient = useQueryClient();
  const grade = useGrade();
  const [busy, setBusy] = useState<"curto" | "duracao" | null>(null);
  const avisos = r.avisos.filter((a) => a.code === "fala_nao_cabe");
  if (avisos.length === 0) return null;
  const maior = proximaDuracao(grade.data?.opcoes, r.duracaoAlvoS);
  const podeCurto = !travado && r.status === "aguardando_narracao" && !ajusteAberto(r);
  const cenas = avisos.map((a) => (a.ordem != null ? a.ordem + 1 : null)).filter((x): x is number => x !== null);

  return (
    <Alert data-testid="aviso-fala">
      <TriangleAlert className="text-warning" aria-hidden="true" />
      <AlertTitle>A fala não cabe {cenas.length === 1 ? `na cena ${cenas[0]}` : cenas.length > 1 ? `nas cenas ${cenas.join(", ")}` : "no tempo"}</AlertTitle>
      <AlertDescription>
        <p>Mesmo acelerada até o limite natural, a narração passa do tempo da cena. Escolha uma saída:</p>
        {!travado && (
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!podeCurto || busy !== null}
              aria-busy={busy === "curto"}
              title={podeCurto ? undefined : "Disponível quando a narração estiver esperando a sua aprovação"}
              onClick={async () => {
                setBusy("curto");
                await rodar(() => api.roteiros.recusar(r.id, { alvo: { tipo: "narracao" }, opcoes: [OPCAO_TEXTO_CURTO], texto: null, version: r.version }), "A IA vai encurtar o texto.");
                await invalidarConversa(queryClient, r.id);
                setBusy(null);
              }}
            >
              {busy === "curto" && <Loader2 className="animate-spin" aria-hidden="true" />}
              Texto mais curto
            </Button>
            {maior != null && (
              <ConfirmButton
                label="Duração maior"
                size="sm"
                busy={busy === "duracao"}
                disabled={busy !== null}
                title={`Aumentar o vídeo para ${duracaoTexto(maior)}?`}
                description={`O vídeo passa de ${duracaoTexto(r.duracaoAlvoS ?? 0)} para ${duracaoTexto(maior)} e o plano é refeito a partir do texto: a narração, os quadros e os clipes saem de novo para você aprovar.`}
                onConfirm={async () => {
                  setBusy("duracao");
                  await rodar(() => api.roteiros.editar(r.id, { version: r.version, duracaoS: maior }), `Duração mudada para ${duracaoTexto(maior)}. O plano vai ser refeito.`);
                  setBusy(null);
                }}
              />
            )}
          </div>
        )}
        {!podeCurto && !travado && <p className="mt-1 text-xs text-muted-foreground">O texto mais curto pode ser pedido quando a narração estiver esperando a sua aprovação.</p>}
      </AlertDescription>
    </Alert>
  );
}
