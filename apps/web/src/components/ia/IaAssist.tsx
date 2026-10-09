/*
 * Painel "Melhorar com IA" de um campo (spec 008, R11). Não conhece rotas de entidade: gera pelo
 * `POST /api/ia/gerar` e, no clique humano em Aplicar, chama o `onSave` da tela, que salva só aquele
 * campo pelo save normal (com `ia` no corpo). Gerar nunca salva.
 *
 * <IaAssist tipo="avatar.descricao_prompt" perfilId alvo={{ entityType: "asset", entityId }} value onSave>
 *   {(botao) => <Field label="Descrição para prompts" action={botao}>…</Field>}
 * </IaAssist>
 *
 * - `value`: o que está no formulário agora (salvo ou não): string (`texto`), string[] (`lista`) ou
 *   { titulo, descricao, hashtags } (`textos_postagem`). As listas de sugestões usam <IaSugestoes>.
 * - A sessão (propostas "Versão N", instrução, edição) sobrevive à remontagem do formulário; some
 *   ao aplicar, descartar ou fechar. As chamadas sem aplicação são descartadas (melhor esforço).
 * - Erro no `onSave` (409, 400, rede): a proposta continua no painel e nada muda no formulário.
 * - Spec 017: a proposta com palavra proibida pelo guia (`chamada.proibidas`) vem marcada, o
 *   "Aplicar" fica desabilitado e o "Editar e aplicar" continua liberado (editado por um humano, a
 *   decisão é dele). "Guia usado" mostra as versões dos guias que entraram no pedido.
 */
import type { IaAlvo, IaChamada, IaGerarRequest, TipoCampo, TipoCampoId } from "@sociman/contract";
import { ApiError } from "@sociman/contract";
import { Loader2, PencilLine, RefreshCw, Save, Sparkles, TriangleAlert, X } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent } from "@/components/ui/collapsible";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { guiaContaPath, guiaPerfilPath } from "@/lib/guia";
import {
  descartarChamadas,
  iaErroRepetivel,
  iaErroTexto,
  idiomaLabel,
  INSTRUCAO_MAX,
  novoSessaoId,
  useIaTipo,
  useSessaoIa,
  valorAtual,
  type IaOnSave,
  type IaValorCampo,
  type TextosPostagem,
} from "@/lib/ia";
import { DESCRICAO_MAX, HASHTAGS_MAX, parseHashtags, TITULO_MAX } from "@/lib/postagem";
import { cn } from "@/lib/utils";
import { ProibidasMarcadas } from "../guia/ProibidasMarcadas";
import { IaBotao } from "./IaBotao";
import { IaDiff } from "./IaDiff";

interface Sessao<V> {
  aberto: boolean;
  sessaoId: string;
  instrucao: string;
  chamadas: IaChamada[];
  atual: string | null;
  // Texto do "Editar e aplicar" (null = mostrando a proposta como veio).
  edicao: V | null;
}

const nova = <V,>(): Sessao<V> => ({ aberto: false, sessaoId: novoSessaoId(), instrucao: "", chamadas: [], atual: null, edicao: null });

export interface IaAssistProps<V extends IaValorCampo> {
  tipo: TipoCampoId;
  perfilId: string;
  alvo: IaAlvo;
  value: V;
  onSave: IaOnSave<V>;
  // Nome do campo. Não entra em nome acessível nenhum: o getByLabel("<campo>") dos e2e tem de achar
  // só o campo.
  campo: string;
  disabled?: boolean;
  // Chave da sessão do painel; o padrão é tipo + alvo (a postagem nova usa corte + conta).
  sessaoKey?: string;
  botaoLabel?: string;
  // "Recarregar" do aviso de conflito de versão.
  onReload?: () => void;
  // Spec 010: o formulário atual da cena (obrigatório para a cena ainda não salva).
  cenaContexto?: IaGerarRequest["cenaContexto"];
  children: (botao: ReactNode) => ReactNode;
}

export function IaAssist<V extends IaValorCampo>({
  tipo,
  perfilId,
  alvo,
  value,
  onSave,
  disabled,
  sessaoKey,
  botaoLabel,
  onReload,
  cenaContexto,
  children,
}: IaAssistProps<V>) {
  const info = useIaTipo(tipo);
  const tituloId = useId();
  const key = sessaoKey ?? `ia:${tipo}:${alvo.entityType}:${alvo.entityId ?? ""}:${alvo.contaId ?? ""}`;
  const [s, set] = useSessaoIa<Sessao<V>>(key, nova, (abandonada) => descartarChamadas(abandonada.chamadas.map((c) => c.id)));
  const [gerando, setGerando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const [erroSalvar, setErroSalvar] = useState<unknown>(null);
  const formato = info?.formato ?? (typeof value === "string" ? "texto" : Array.isArray(value) ? "lista" : "textos_postagem");

  const chamada = s.chamadas.find((c) => c.id === s.atual) ?? null;
  const proposta = chamada ? (propostaValor(formato, chamada) as V) : null;
  const mostrado = s.edicao ?? proposta;
  // Spec 017: proibidas que ficaram na proposta final (a API já tentou de novo uma vez).
  const proibidas = chamada?.proibidas ?? [];
  const excede =
    mostrado !== null && (s.edicao !== null ? excedeLimite(info, s.edicao) : Boolean(chamada?.excede) || excedeLimite(info, mostrado));

  function fechar() {
    descartarChamadas(s.chamadas.map((c) => c.id));
    set(() => nova());
    setErro(null);
    setErroSalvar(null);
  }

  async function gerar(outra: boolean) {
    setErro(null);
    setErroSalvar(null);
    setGerando(true);
    try {
      const { chamada: nova } = await api.ia.gerar({
        tipoCampo: tipo,
        perfilId,
        alvo,
        valorAtual: valorAtual(formato, value),
        instrucao: s.instrucao.trim(),
        sessaoId: s.sessaoId,
        anteriores: outra ? s.chamadas.slice(-5).map((c) => c.id) : [],
        ...(cenaContexto ? { cenaContexto } : {}),
      });
      set((cur) => ({ ...cur, chamadas: [...cur.chamadas, nova], atual: nova.id, edicao: null }));
    } catch (err) {
      setErro(err);
    } finally {
      setGerando(false);
    }
  }

  async function aplicar(valor: V) {
    if (!chamada) return;
    setErroSalvar(null);
    setSalvando(true);
    try {
      await onSave(valor, [{ tipoCampo: tipo, chamadaId: chamada.id }]);
      descartarChamadas(s.chamadas.filter((c) => c.id !== chamada.id).map((c) => c.id));
      set(() => nova());
      setErro(null);
      toast.success("Salvo com ajuda da IA.");
    } catch (err) {
      setErroSalvar(err);
    } finally {
      setSalvando(false);
    }
  }

  const ocupado = gerando || salvando;
  const idx = chamada ? s.chamadas.indexOf(chamada) : -1;

  return (
    <Collapsible
      open={s.aberto}
      onOpenChange={(aberto) => (aberto ? set((cur) => ({ ...cur, aberto: true })) : fechar())}
      className="space-y-2"
    >
      {children(<IaBotao label={botaoLabel} tipo={tipo} disabled={disabled} />)}
      <CollapsibleContent
        role="region"
        aria-labelledby={tituloId}
        data-testid={`ia-painel-${tipo}`}
        className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3"
      >
        <div className="flex items-start justify-between gap-2">
          <p id={tituloId} className="flex flex-wrap items-center gap-2 text-sm font-medium">
            <Sparkles className="size-4 text-primary" aria-hidden="true" />
            Melhorar com IA
            {info && (
              <span className="font-normal text-muted-foreground">
                · {info.rotulo} · {idiomaLabel[info.idioma]}
              </span>
            )}
          </p>
          <Button type="button" variant="ghost" size="icon" className="size-7" aria-label="Fechar o painel da IA" onClick={fechar}>
            <X aria-hidden="true" />
          </Button>
        </div>

        <Field
          label="Como a IA deve ajudar? (opcional)"
          hint={
            <span className="flex flex-wrap justify-between gap-2">
              <span>Vazio: melhora o texto atual ou cria um, se o campo estiver vazio.</span>
              <span aria-live="polite">
                {s.instrucao.length.toLocaleString("pt-BR")}/{INSTRUCAO_MAX.toLocaleString("pt-BR")}
              </span>
            </span>
          }
        >
          {({ id, describedBy }) => (
            <Textarea
              id={id}
              rows={2}
              maxLength={INSTRUCAO_MAX}
              value={s.instrucao}
              aria-describedby={describedBy}
              placeholder="Ex.: deixa mais curto e acrescenta que ela usa avental rosa"
              onChange={(e) => {
                const instrucao = e.target.value;
                set((cur) => ({ ...cur, instrucao }));
              }}
            />
          )}
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" disabled={ocupado || disabled} aria-busy={gerando} onClick={() => void gerar(false)}>
            {gerando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
            {gerando ? "Gerando…" : "Gerar"}
          </Button>
        </div>

        {erro !== null && (
          <Alert variant="destructive">
            <AlertTitle>Não foi possível gerar</AlertTitle>
            <AlertDescription>
              <p>{iaErroTexto(erro)}</p>
              <p>O campo continua editável à mão.</p>
              {iaErroRepetivel(erro) && (
                <Button type="button" variant="outline" size="sm" className="mt-1" disabled={ocupado} onClick={() => void gerar(false)}>
                  <RefreshCw aria-hidden="true" />
                  Tentar de novo
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}

        {chamada && mostrado !== null && (
          <div className="space-y-3 border-t pt-3">
            {s.chamadas.length > 1 && (
              <div role="group" aria-label="Versões desta sessão" className="flex flex-wrap gap-1">
                {s.chamadas.map((c, i) => (
                  <Button
                    key={c.id}
                    type="button"
                    size="sm"
                    variant={c.id === chamada.id ? "secondary" : "ghost"}
                    aria-pressed={c.id === chamada.id}
                    disabled={salvando}
                    onClick={() => set((cur) => ({ ...cur, atual: c.id, edicao: null }))}
                  >
                    Versão {i + 1}
                  </Button>
                ))}
              </div>
            )}

            {s.edicao === null ? (
              <IaDiff
                antes={mostrar(value)}
                depois={mostrar(mostrado, proibidas)}
                rotuloDepois={s.chamadas.length > 1 ? `Versão ${idx + 1}` : "Proposta"}
              />
            ) : (
              <Editor formato={formato} valor={s.edicao} onChange={(edicao) => set((cur) => ({ ...cur, edicao }))} />
            )}
            <Contador info={info} valor={mostrado} excede={excede} />

            {proibidas.length > 0 && (
              <Alert className="border-warning/60">
                <TriangleAlert className="text-warning" aria-hidden="true" />
                <AlertTitle>Palavra proibida pelo guia</AlertTitle>
                <AlertDescription>
                  A proposta usa uma palavra proibida pelo guia ({proibidas.join(", ")}); edite antes de aplicar.
                </AlertDescription>
              </Alert>
            )}
            {chamada.explicacao && <p className="text-sm">{chamada.explicacao}</p>}
            {avisosSemProibida(chamada).length > 0 && (
              <ul aria-label="Avisos da IA" className="list-disc space-y-0.5 pl-5 text-sm text-warning-foreground">
                {avisosSemProibida(chamada).map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
            {chamada.contextoFaltante.length > 0 && (
              <p className="text-xs text-muted-foreground">Faltou contexto: {chamada.contextoFaltante.join(", ")}.</p>
            )}
            <GuiaUsado chamada={chamada} />
            {excede && (
              <p role="alert" className="text-sm text-destructive">
                Acima do limite do campo. Edite antes de aplicar.
              </p>
            )}

            {erroSalvar !== null &&
              (erroSalvar instanceof ApiError && erroSalvar.code === "ia_proibida" ? (
                <Alert variant="destructive">
                  <AlertTitle>Não foi aplicado</AlertTitle>
                  <AlertDescription>
                    <p>{erroSalvar.message}</p>
                    <p>Use "Editar e aplicar" e troque a palavra; o texto editado por você pode ser salvo.</p>
                  </AlertDescription>
                </Alert>
              ) : (
                <ApiErrorAlert error={erroSalvar} onReload={onReload} />
              ))}

            <div className="flex flex-wrap gap-2">
              {s.edicao === null ? (
                <>
                  <Button
                    type="button"
                    size="sm"
                    disabled={ocupado || disabled || excede || proibidas.length > 0}
                    aria-busy={salvando}
                    onClick={() => void aplicar(mostrado)}
                  >
                    {salvando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                    {salvando ? "Salvando…" : "Aplicar"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={ocupado || disabled}
                    onClick={() => set((cur) => ({ ...cur, edicao: proposta }))}
                  >
                    <PencilLine aria-hidden="true" />
                    Editar e aplicar
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    type="button"
                    size="sm"
                    disabled={ocupado || disabled || excede}
                    aria-busy={salvando}
                    onClick={() => void aplicar(s.edicao!)}
                  >
                    {salvando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                    {salvando ? "Salvando…" : "Salvar"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={salvando}
                    onClick={() => set((cur) => ({ ...cur, edicao: null }))}
                  >
                    Cancelar edição
                  </Button>
                </>
              )}
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={ocupado || disabled}
                aria-busy={gerando}
                onClick={() => void gerar(true)}
              >
                {gerando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
                Outra versão
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={salvando} onClick={fechar}>
                Descartar
              </Button>
            </div>
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

function propostaValor(formato: TipoCampo["formato"], c: IaChamada): IaValorCampo {
  const p = c.proposta ?? {};
  if (formato === "texto") return p.texto ?? "";
  if (formato === "textos_postagem") return { titulo: p.titulo ?? "", descricao: p.descricao ?? "", hashtags: p.hashtags ?? [] };
  return p.itens ?? [];
}

// Spec 017: o aviso da proibida já sai no alerta próprio; os outros avisos seguem na lista.
const avisosSemProibida = (c: IaChamada) =>
  c.proibidas.length > 0 ? c.avisos.filter((a) => !a.startsWith("A proposta usa uma palavra proibida")) : c.avisos;

// "Guia usado: perfil vN · conta vM" (spec 017, FR-006), com link para o guia (e o histórico) de cada nível.
function GuiaUsado({ chamada }: { chamada: IaChamada }) {
  const { guiaPerfilVersion: vp, guiaContaVersion: vc } = chamada;
  const contaId = chamada.alvo.contaId;
  if (vp == null && vc == null) return null;
  return (
    <p className="text-xs text-muted-foreground">
      Guia usado:{" "}
      {vp != null && (
        <Link to={guiaPerfilPath(chamada.perfil.id)} className="underline-offset-4 hover:underline">
          perfil v{vp}
        </Link>
      )}
      {vp != null && vc != null && " · "}
      {vc != null &&
        (contaId ? (
          <Link to={guiaContaPath(contaId)} className="underline-offset-4 hover:underline">
            conta v{vc}
          </Link>
        ) : (
          `conta v${vc}`
        ))}
    </p>
  );
}

function mostrar(v: IaValorCampo, proibidas: string[] = []): ReactNode {
  const m = (t: string) => <ProibidasMarcadas texto={t} proibidas={proibidas} />;
  if (typeof v === "string") return proibidas.length > 0 && v ? m(v) : v;
  if (Array.isArray(v)) return proibidas.length > 0 && v.length > 0 ? m(v.join(" ")) : v.join(" ");
  return (
    <dl className="space-y-1.5">
      <div>
        <dt className="text-xs font-semibold text-muted-foreground">Título</dt>
        <dd>{v.titulo ? m(v.titulo) : "—"}</dd>
      </div>
      <div>
        <dt className="text-xs font-semibold text-muted-foreground">Descrição</dt>
        <dd>{v.descricao ? m(v.descricao) : "—"}</dd>
      </div>
      <div>
        <dt className="text-xs font-semibold text-muted-foreground">Hashtags</dt>
        <dd>{v.hashtags.length > 0 ? m(v.hashtags.join(" ")) : "—"}</dd>
      </div>
    </dl>
  );
}

function excedeLimite(info: TipoCampo | undefined, v: IaValorCampo): boolean {
  if (typeof v === "string") {
    const max = info?.limites.maxChars;
    const min = info?.limites.minChars;
    return (max != null && v.length > max) || (min != null && v.trim().length < min) || (Boolean(info?.limites.umaLinha) && /\n/.test(v));
  }
  if (Array.isArray(v)) {
    const max = info?.limites.maxItens;
    const maxItem = info?.limites.maxCharsItem;
    return (max != null && v.length > max) || (maxItem != null && v.some((i) => i.length > maxItem));
  }
  return v.titulo.length > TITULO_MAX || /\n/.test(v.titulo) || v.descricao.length > DESCRICAO_MAX || v.hashtags.length > HASHTAGS_MAX;
}

function Contador({ info, valor, excede }: { info: TipoCampo | undefined; valor: IaValorCampo; excede: boolean }) {
  let texto: string | null = null;
  if (typeof valor === "string" && info?.limites.maxChars != null) {
    texto = `${valor.length.toLocaleString("pt-BR")}/${info.limites.maxChars.toLocaleString("pt-BR")} caracteres`;
  } else if (Array.isArray(valor) && info?.limites.maxItens != null) {
    texto = `${valor.length}/${info.limites.maxItens} itens`;
  } else if (typeof valor === "object" && !Array.isArray(valor)) {
    texto = `Título ${valor.titulo.length}/${TITULO_MAX} · descrição ${valor.descricao.length.toLocaleString("pt-BR")}/${DESCRICAO_MAX.toLocaleString("pt-BR")} · ${valor.hashtags.length}/${HASHTAGS_MAX} hashtags`;
  }
  if (!texto) return null;
  return (
    <p aria-live="polite" className={cn("text-xs text-muted-foreground", excede && "font-medium text-destructive")}>
      {texto}
    </p>
  );
}

// "Editar e aplicar": a proposta editável no painel, no formato do campo. Os rótulos evitam as
// palavras dos campos da tela (Título, Descrição, Hashtags), que os e2e buscam por getByLabel.
function Editor<V extends IaValorCampo>({
  formato,
  valor,
  onChange,
}: {
  formato: TipoCampo["formato"];
  valor: V;
  onChange: (v: V) => void;
}) {
  if (typeof valor === "string") {
    return (
      <Field label="Proposta (editável)">
        {({ id }) => (
          <Textarea
            id={id}
            rows={formato === "texto" && valor.length < 120 ? 2 : 6}
            value={valor}
            onChange={(e) => onChange(e.target.value as V)}
          />
        )}
      </Field>
    );
  }
  // A única lista que não é de sugestões é a de hashtags.
  if (Array.isArray(valor)) return <HashtagsEditor valor={valor} onChange={(v) => onChange(v as V)} label="Proposta (editável)" />;
  const t = valor as TextosPostagem;
  return (
    <div className="space-y-2">
      <Field label="Proposta: primeira linha">
        {({ id }) => <Input id={id} value={t.titulo} onChange={(e) => onChange({ ...t, titulo: e.target.value } as V)} />}
      </Field>
      <Field label="Proposta: texto">
        {({ id }) => <Textarea id={id} rows={4} value={t.descricao} onChange={(e) => onChange({ ...t, descricao: e.target.value } as V)} />}
      </Field>
      <HashtagsEditor valor={t.hashtags} onChange={(hashtags) => onChange({ ...t, hashtags } as V)} />
    </div>
  );
}

// Hashtags editadas como texto; o texto digitado fica no estado local para o espaço no fim não sumir
// enquanto se digita.
function HashtagsEditor({
  valor,
  onChange,
  label = "Proposta: tags",
}: {
  valor: string[];
  onChange: (v: string[]) => void;
  label?: string;
}) {
  const [texto, setTexto] = useState(valor.join(" "));
  return (
    <Field label={label} hint="Separadas por espaço.">
      {({ id, describedBy }) => (
        <Input
          id={id}
          value={texto}
          aria-describedby={describedBy}
          onChange={(e) => {
            setTexto(e.target.value);
            onChange(parseHashtags(e.target.value));
          }}
        />
      )}
    </Field>
  );
}
