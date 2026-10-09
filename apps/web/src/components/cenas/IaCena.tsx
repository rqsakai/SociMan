/*
 * IA na cena (spec 010, US4; FR-014/FR-015): "Melhorar com IA" na ação, no detalhe de câmera, na
 * iluminação e estilo e no áudio (o IaAssist da 008), e "Ajustar cena com IA", que propõe os quatro
 * juntos (formato `campos_cena`). Os tipos `cena.*` recebem só as palavras proibidas do guia e o
 * avatar, o cenário e o produto como contexto; a descrição do avatar e o prompt do cenário não são
 * campos da cena, então a IA não os muda. Gerar nunca salva: o "Aplicar" humano grava só os campos
 * propostos (PATCH com `ia`) ou, na cena nova, preenche o formulário e leva a marca para o "Salvar".
 */
import { ApiError, type IaChamada, type IaGerarRequest, type TipoCampoId } from "@sociman/contract";
import { Loader2, RefreshCw, Save, Sparkles, TriangleAlert, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ProibidasMarcadas } from "@/components/guia/ProibidasMarcadas";
import { IaAssist } from "@/components/ia/IaAssist";
import { IaDiff } from "@/components/ia/IaDiff";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { descartarChamadas, iaErroTexto, INSTRUCAO_MAX, novoSessaoId } from "@/lib/ia";
import type { Cena, CenaCampos, IaAplicacaoCena } from "@/lib/cenas";
import type { CampoIa } from "./CenaForm";

export type IaCenaDecorador = (campo: CampoIa, render: (botao: ReactNode) => ReactNode) => ReactNode;

export interface IaCtx {
  // o perfil base da cena (029: null = nenhum; a chamada vai sem guia)
  perfilId: string | null;
  cena: Cena | null;
  valores: CenaCampos;
  // Cena salva: grava só os campos (PATCH com `ia`). Cena nova: preenche e guarda a marca para o POST.
  salvar: (patch: Partial<CenaCampos>, ia: IaAplicacaoCena[]) => Promise<void>;
  disabled: boolean;
}

const CAMPOS: CampoIa[] = ["acao", "camera", "estilo", "audio"];
const rotulo: Record<CampoIa, string> = { acao: "Ação", camera: "Detalhe de câmera", estilo: "Iluminação e estilo", audio: "Áudio e ambiente" };

function contexto(v: CenaCampos): NonNullable<IaGerarRequest["cenaContexto"]> {
  return {
    avatarId: v.avatarId,
    avatarArquivoId: v.avatarArquivoId,
    cenarioId: v.cenarioId,
    produtoNome: v.produtoNome,
    fala: v.fala,
    duracaoS: v.duracaoS,
    modo: v.modo,
  };
}

// Decora os 4 campos de texto do CenaForm com o "Melhorar com IA".
export function iaCenaDecorador(ctx: IaCtx): IaCenaDecorador {
  const alvo = { entityType: "cena" as const, entityId: ctx.cena?.id ?? null };
  return (campo, render) => (
    <IaAssist
      tipo={`cena.${campo}` as TipoCampoId}
      perfilId={ctx.perfilId}
      perfilBaseId={ctx.perfilId}
      alvo={alvo}
      value={ctx.valores[campo] ?? ""}
      campo={rotulo[campo]}
      disabled={ctx.disabled}
      cenaContexto={ctx.cena ? undefined : contexto(ctx.valores)}
      sessaoKey={`ia:cena.${campo}:${ctx.cena?.id ?? `nova:${ctx.perfilId}`}`}
      onSave={(valor, ia) => ctx.salvar({ [campo]: campo === "acao" ? valor : valor || null } as Partial<CenaCampos>, ia)}
    >
      {render}
    </IaAssist>
  );
}

// "Ajustar cena com IA": os 4 campos juntos, com uma instrução opcional ("mais close no produto").
export function AjustarCenaIa({ ctx }: { ctx: IaCtx }) {
  const [aberto, setAberto] = useState(false);
  const [instrucao, setInstrucao] = useState("");
  const [sessaoId] = useState(novoSessaoId);
  const [chamadas, setChamadas] = useState<IaChamada[]>([]);
  const [gerando, setGerando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const atual = chamadas.at(-1) ?? null;
  const proposta = (atual?.proposta?.cena ?? {}) as Partial<Record<CampoIa, string | null>>;
  const mudam = CAMPOS.filter((c) => proposta[c] != null);
  const proibidas = atual?.proibidas ?? [];
  const v = ctx.valores;

  function fechar() {
    descartarChamadas(chamadas.map((c) => c.id));
    setChamadas([]);
    setErro(null);
    setAberto(false);
  }

  async function gerar(outra: boolean) {
    setErro(null);
    setGerando(true);
    try {
      const { chamada } = await api.ia.gerar({
        tipoCampo: "cena.ajustar" as TipoCampoId,
        ...(ctx.perfilId ? { perfilId: ctx.perfilId } : {}),
        perfilBaseId: ctx.perfilId,
        alvo: { entityType: "cena", entityId: ctx.cena?.id ?? null },
        valorAtual: { cena: { acao: v.acao, camera: v.camera, estilo: v.estilo, audio: v.audio } },
        instrucao: instrucao.trim(),
        sessaoId,
        anteriores: outra ? chamadas.slice(-5).map((c) => c.id) : [],
        ...(ctx.cena ? {} : { cenaContexto: contexto(v) }),
      });
      setChamadas((cur) => [...cur, chamada]);
    } catch (err) {
      setErro(err);
    } finally {
      setGerando(false);
    }
  }

  async function aplicar() {
    if (!atual) return;
    setErro(null);
    setSalvando(true);
    try {
      const patch = Object.fromEntries(mudam.map((c) => [c, proposta[c] || (c === "acao" ? v.acao : null)])) as Partial<CenaCampos>;
      await ctx.salvar(patch, [{ tipoCampo: "cena.ajustar" as TipoCampoId, chamadaId: atual.id }]);
      descartarChamadas(chamadas.filter((c) => c.id !== atual.id).map((c) => c.id));
      setChamadas([]);
      setAberto(false);
      toast.success(ctx.cena ? "Salvo com ajuda da IA." : "Campos preenchidos com ajuda da IA. Salve a cena.");
    } catch (err) {
      setErro(err);
    } finally {
      setSalvando(false);
    }
  }

  if (!aberto) {
    return (
      <Button type="button" variant="outline" size="sm" className="text-primary" disabled={ctx.disabled} onClick={() => setAberto(true)} data-testid="ia-botao-cena.ajustar">
        <Sparkles aria-hidden="true" />
        Ajustar cena com IA
      </Button>
    );
  }

  const ocupado = gerando || salvando;
  const mostrar = (t: string | null | undefined): ReactNode => (t ? <ProibidasMarcadas texto={t} proibidas={proibidas} /> : "");

  return (
    <section
      role="region"
      aria-label="Ajustar cena com IA"
      data-testid="ia-painel-cena.ajustar"
      className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="size-4 text-primary" aria-hidden="true" />
          Ajustar cena com IA
          <span className="font-normal text-muted-foreground">· ação, câmera, estilo e áudio · Inglês</span>
        </p>
        <Button type="button" variant="ghost" size="icon" className="size-7" aria-label="Fechar o ajuste da cena com IA" onClick={fechar}>
          <X aria-hidden="true" />
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">A descrição do avatar e o prompt do cenário vêm dos assets e não mudam aqui.</p>
      <Field label="Como a IA deve ajustar? (opcional)" hint={`${instrucao.length}/${INSTRUCAO_MAX}`}>
        {({ id, describedBy }) => (
          <Textarea
            id={id}
            rows={2}
            maxLength={INSTRUCAO_MAX}
            value={instrucao}
            aria-describedby={describedBy}
            placeholder="Ex.: mais close no produto, câmera lenta"
            onChange={(e) => setInstrucao(e.target.value)}
          />
        )}
      </Field>
      <Button type="button" size="sm" disabled={ocupado || ctx.disabled} aria-busy={gerando} onClick={() => void gerar(false)}>
        {gerando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
        {gerando ? "Gerando…" : "Gerar"}
      </Button>
      {erro !== null &&
        (erro instanceof ApiError && erro.code === "ia_proibida" ? (
          <ApiErrorAlert error={erro} />
        ) : (
          <Alert variant="destructive">
            <AlertTitle>Não foi possível concluir</AlertTitle>
            <AlertDescription>{iaErroTexto(erro)}</AlertDescription>
          </Alert>
        ))}
      {atual && (
        <div className="space-y-3 border-t pt-3">
          {mudam.length === 0 ? (
            <p className="text-sm text-muted-foreground">A IA não propôs mudança. Tente outra versão ou mude a instrução.</p>
          ) : (
            mudam.map((c) => (
              <div key={c} className="space-y-1">
                <p className="text-sm font-medium">{rotulo[c]}</p>
                <IaDiff antes={v[c] ?? ""} depois={mostrar(proposta[c])} />
              </div>
            ))
          )}
          {proibidas.length > 0 && (
            <Alert className="border-warning/60">
              <TriangleAlert className="text-warning" aria-hidden="true" />
              <AlertTitle>Palavra proibida pelo guia</AlertTitle>
              <AlertDescription>A proposta usa uma palavra proibida pelo guia ({proibidas.join(", ")}). Edite os campos à mão.</AlertDescription>
            </Alert>
          )}
          {atual.explicacao && <p className="text-sm">{atual.explicacao}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" disabled={ocupado || mudam.length === 0 || proibidas.length > 0} aria-busy={salvando} onClick={() => void aplicar()}>
              {salvando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              {salvando ? "Salvando…" : "Aplicar"}
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={ocupado} onClick={() => void gerar(true)}>
              <RefreshCw aria-hidden="true" />
              Outra versão
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={salvando} onClick={fechar}>
              Descartar
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
