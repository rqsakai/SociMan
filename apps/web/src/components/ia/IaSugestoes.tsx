/*
 * Sugestões com seleção para as listas do kit (bordões e séries; spec 008, Q3 e R9). A IA devolve até
 * 10 sugestões; o usuário marca as que quer (e pode editar as marcadas) e "Aplicar" acrescenta as
 * marcadas ao fim da lista do kit, sem repetir e sem passar de 20. "Gerar mais" manda os aceitos (os
 * marcados ainda não aplicados; os da lista vão em `valorAtual`) e os rejeitados da sessão.
 *
 * <IaSugestoes tipo="kit.bordoes" perfilId alvo={{ entityType: "kit", entityId: perfilId }} value onSave campo="Bordões">
 *   {(botao) => <LinesField … action={botao} />}
 * </IaSugestoes>
 *
 * Depois de aplicar, o painel continua aberto e os aplicados passam a contar como lista.
 * Spec 017: a sugestão com palavra proibida pelo guia (`chamada.proibidas`) vem marcada e só entra
 * editada (marcar abre a edição); "Guia usado" mostra as versões dos guias do pedido.
 */
import type { IaAlvo, IaAplicacao, IaChamada, TipoCampoId } from "@sociman/contract";
import { Loader2, RefreshCw, Save, Sparkles, X } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent } from "@/components/ui/collapsible";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { guiaContaPath, guiaPerfilPath, partesComProibidas } from "@/lib/guia";
import {
  chaveItem,
  descartarChamadas,
  iaErroRepetivel,
  iaErroTexto,
  INSTRUCAO_MAX,
  novoSessaoId,
  useIaTipo,
  useSessaoIa,
  type IaOnSave,
} from "@/lib/ia";
import { cn } from "@/lib/utils";
import { ProibidasMarcadas } from "../guia/ProibidasMarcadas";
import { IaBotao } from "./IaBotao";
import { EmptyState } from "@/components/shell";

interface Item {
  id: string;
  chamadaId: string;
  original: string;
  texto: string;
  marcado: boolean;
  aplicado: boolean;
}

interface Sessao {
  aberto: boolean;
  sessaoId: string;
  instrucao: string;
  chamadas: IaChamada[];
  itens: Item[];
}

const nova = (): Sessao => ({ aberto: false, sessaoId: novoSessaoId(), instrucao: "", chamadas: [], itens: [] });

const LISTA_MAX = 20;
const REJEITADOS_MAX = 100;
const IA_MAX = 10;

export interface IaSugestoesProps {
  tipo: TipoCampoId;
  perfilId: string;
  alvo: IaAlvo;
  // A lista do formulário agora (salva ou não).
  value: string[];
  // Recebe a lista final (a do formulário + as marcadas no fim, sem repetir).
  onSave: IaOnSave<string[]>;
  // Nome da lista (só documenta a tela; fora dos nomes acessíveis, como no IaAssist).
  campo: string;
  disabled?: boolean;
  onReload?: () => void;
  children: (botao: ReactNode) => ReactNode;
}

export function IaSugestoes({ tipo, perfilId, alvo, value, onSave, disabled, onReload, children }: IaSugestoesProps) {
  const info = useIaTipo(tipo);
  const tituloId = useId();
  const key = `ia:${tipo}:${alvo.entityType}:${alvo.entityId ?? ""}`;
  const [s, set] = useSessaoIa<Sessao>(key, nova, (abandonada) => descartarChamadas(semAplicacao(abandonada)));
  const [gerando, setGerando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const [erroSalvar, setErroSalvar] = useState<unknown>(null);

  const maxLista = info?.limites.maxItens ?? LISTA_MAX;
  const maxItem = info?.limites.maxCharsItem ?? null;
  const naLista = new Set(value.map(chaveItem));
  const marcados = s.itens.filter((i) => i.marcado && !i.aplicado);
  const cabem = Math.max(0, maxLista - value.length);
  const restam = cabem - marcados.length;
  const cheia = value.length >= maxLista;
  const repetido = (item: Item) =>
    naLista.has(chaveItem(item.texto)) || marcados.some((m) => m.id !== item.id && chaveItem(m.texto) === chaveItem(item.texto));
  // Spec 017: proibidas da chamada de onde veio o item; sem editar, o item não entra (FR-004).
  const proibidasDe = (item: Item) => s.chamadas.find((c) => c.id === item.chamadaId)?.proibidas ?? [];
  const temProibida = (item: Item) => partesComProibidas(item.original, proibidasDe(item)).some((p) => p.proibida);
  const semEditar = (item: Item) => temProibida(item) && item.texto.trim() === item.original.trim();
  const invalido = (item: Item) =>
    item.texto.trim().length === 0 ||
    (maxItem !== null && item.texto.trim().length > maxItem) ||
    repetido(item) ||
    semEditar(item);
  const podeAplicar = marcados.length > 0 && marcados.length <= cabem && !marcados.some(invalido);

  function fechar() {
    descartarChamadas(semAplicacao(s));
    set(() => nova());
    setErro(null);
    setErroSalvar(null);
  }

  const atualizarItem = (id: string, patch: Partial<Item>) =>
    set((cur) => ({ ...cur, itens: cur.itens.map((i) => (i.id === id ? { ...i, ...patch } : i)) }));

  async function gerar() {
    setErro(null);
    setErroSalvar(null);
    setGerando(true);
    try {
      const pendentes = s.itens.filter((i) => !i.aplicado);
      const { chamada } = await api.ia.gerar({
        tipoCampo: tipo,
        perfilId,
        alvo,
        valorAtual: { itens: value },
        instrucao: s.instrucao.trim(),
        sessaoId: s.sessaoId,
        anteriores: s.chamadas.slice(-5).map((c) => c.id),
        selecao: {
          aceitos: pendentes
            .filter((i) => i.marcado)
            .map((i) => i.texto.trim())
            .slice(0, LISTA_MAX),
          rejeitados: pendentes
            .filter((i) => !i.marcado)
            .map((i) => i.original)
            .slice(-REJEITADOS_MAX),
        },
      });
      const novos: Item[] = (chamada.proposta?.itens ?? []).map((texto, n) => ({
        id: `${chamada.id}:${n}`,
        chamadaId: chamada.id,
        original: texto,
        texto,
        marcado: false,
        aplicado: false,
      }));
      set((cur) => ({ ...cur, chamadas: [...cur.chamadas, chamada], itens: [...cur.itens, ...novos] }));
    } catch (err) {
      setErro(err);
    } finally {
      setGerando(false);
    }
  }

  async function aplicar() {
    if (!podeAplicar) return;
    setErroSalvar(null);
    setSalvando(true);
    const final = [...value];
    const porChamada = new Map<string, string[]>();
    for (const m of marcados) {
      const texto = m.texto.trim();
      if (final.some((x) => chaveItem(x) === chaveItem(texto))) continue;
      final.push(texto);
      porChamada.set(m.chamadaId, [...(porChamada.get(m.chamadaId) ?? []), texto]);
    }
    const ia: IaAplicacao[] = [...porChamada.entries()]
      .slice(0, IA_MAX)
      .map(([chamadaId, itens]) => ({ tipoCampo: tipo, chamadaId, itens }));
    try {
      await onSave(final, ia);
      const ids = new Set(marcados.map((m) => m.id));
      set((cur) => ({ ...cur, itens: cur.itens.map((i) => (ids.has(i.id) ? { ...i, marcado: false, aplicado: true } : i)) }));
      toast.success("Salvo com ajuda da IA.");
    } catch (err) {
      setErroSalvar(err);
    } finally {
      setSalvando(false);
    }
  }

  const ocupado = gerando || salvando;

  return (
    <Collapsible
      open={s.aberto}
      onOpenChange={(aberto) => (aberto ? set((cur) => ({ ...cur, aberto: true })) : fechar())}
      className="space-y-2"
    >
      {children(<IaBotao tipo={tipo} disabled={disabled} />)}
      <CollapsibleContent
        role="region"
        aria-labelledby={tituloId}
        data-testid={`ia-painel-${tipo}`}
        className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3"
      >
        <div className="flex items-start justify-between gap-2">
          <p id={tituloId} className="flex items-center gap-2 text-sm font-medium">
            <Sparkles className="size-4 text-primary" aria-hidden="true" />
            Sugestões da IA
          </p>
          <Button type="button" variant="ghost" size="icon" className="size-7" aria-label="Fechar o painel da IA" onClick={fechar}>
            <X aria-hidden="true" />
          </Button>
        </div>

        <Field
          label="Como a IA deve ajudar? (opcional)"
          hint={
            <span className="flex flex-wrap justify-between gap-2">
              <span>Vazio: sugestões novas no tom da lista atual.</span>
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
              onChange={(e) => {
                const instrucao = e.target.value;
                set((cur) => ({ ...cur, instrucao }));
              }}
            />
          )}
        </Field>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" disabled={ocupado || disabled || cheia} aria-busy={gerando} onClick={() => void gerar()}>
            {gerando ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : s.chamadas.length > 0 ? (
              <RefreshCw aria-hidden="true" />
            ) : (
              <Sparkles aria-hidden="true" />
            )}
            {gerando ? "Gerando…" : s.chamadas.length > 0 ? "Gerar mais" : "Gerar"}
          </Button>
          <span
            aria-live="polite"
            className={cn("text-xs text-muted-foreground", (cheia || restam <= 0) && "font-medium text-destructive")}
          >
            {value.length + marcados.length} de {maxLista}
          </span>
        </div>
        {(cheia || (s.itens.length > 0 && restam <= 0)) && (
          <p role="alert" className="text-sm text-destructive">
            A lista está cheia (máximo de {maxLista}).
          </p>
        )}

        {erro !== null && (
          <Alert variant="destructive">
            <AlertTitle>Não foi possível gerar</AlertTitle>
            <AlertDescription>
              <p>{iaErroTexto(erro)}</p>
              <p>A lista continua editável à mão.</p>
              {iaErroRepetivel(erro) && (
                <Button type="button" variant="outline" size="sm" className="mt-1" disabled={ocupado} onClick={() => void gerar()}>
                  <RefreshCw aria-hidden="true" />
                  Tentar de novo
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}

        {s.chamadas.length > 0 && (
          <div className="space-y-3 border-t pt-3">
            {s.itens.length === 0 ? (
              <EmptyState titulo="Nenhuma sugestão nova desta vez." className="py-4" />
            ) : (
              <ul aria-label="Sugestões" className="space-y-1.5">
                {s.itens.map((item) => {
                  const bloqueado = item.aplicado || (!item.marcado && (restam <= 0 || naLista.has(chaveItem(item.texto))));
                  const longo = maxItem !== null && item.texto.trim().length > maxItem;
                  return (
                    <li key={item.id} className="flex items-center gap-2">
                      <Checkbox
                        checked={item.marcado || item.aplicado}
                        disabled={bloqueado || salvando}
                        aria-label={item.texto}
                        onCheckedChange={(v) => atualizarItem(item.id, { marcado: v === true })}
                      />
                      {item.marcado ? (
                        <Input
                          value={item.texto}
                          aria-label={`Editar: ${item.original}`}
                          aria-invalid={invalido(item)}
                          className="h-8"
                          onChange={(e) => atualizarItem(item.id, { texto: e.target.value })}
                        />
                      ) : (
                        <span className={cn("min-w-0 flex-1 text-sm break-words", item.aplicado && "text-muted-foreground")}>
                          <ProibidasMarcadas texto={item.texto} proibidas={item.aplicado ? [] : proibidasDe(item)} />
                        </span>
                      )}
                      {item.aplicado && <Badge variant="secondary">no kit</Badge>}
                      {!item.aplicado && naLista.has(chaveItem(item.texto)) && !item.marcado && (
                        <Badge variant="outline">já na lista</Badge>
                      )}
                      {!item.aplicado && temProibida(item) && (
                        <Badge variant="outline" className="border-destructive/50 text-destructive">
                          {semEditar(item) ? "proibida: edite" : "editada"}
                        </Badge>
                      )}
                      {longo && (
                        <span className="shrink-0 text-xs text-destructive">
                          {item.texto.trim().length}/{maxItem}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            {s.chamadas.at(-1)?.avisos.map((a) => (
              <p key={a} className="text-xs text-muted-foreground">
                {a}
              </p>
            ))}
            {s.chamadas.at(-1)?.explicacao && <p className="text-sm">{s.chamadas.at(-1)!.explicacao}</p>}
            {s.chamadas.at(-1) && <GuiaUsado chamada={s.chamadas.at(-1)!} />}
            {marcados.some(invalido) && (
              <p role="alert" className="text-sm text-destructive">
                Ajuste as marcadas: sem repetir a lista{maxItem !== null ? ` e com até ${maxItem} caracteres cada` : ""}
                {marcados.some(semEditar) ? "; as com palavra proibida pelo guia só entram editadas" : ""}.
              </p>
            )}

            {erroSalvar !== null && <ApiErrorAlert error={erroSalvar} onReload={onReload} />}

            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                disabled={!podeAplicar || ocupado || disabled}
                aria-busy={salvando}
                onClick={() => void aplicar()}
              >
                {salvando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                {salvando ? "Salvando…" : marcados.length > 0 ? `Aplicar ${marcados.length}` : "Aplicar"}
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={salvando} onClick={fechar}>
                {s.itens.some((i) => i.aplicado) ? "Fechar" : "Descartar"}
              </Button>
            </div>
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

// "Guia usado: perfil vN · conta vM" (spec 017, FR-006), como no IaAssist.
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

// Chamadas da sessão de onde nenhum item entrou no kit (essas vão para "descartada").
function semAplicacao(s: Sessao): string[] {
  const aplicadas = new Set(s.itens.filter((i) => i.aplicado).map((i) => i.chamadaId));
  return s.chamadas.filter((c) => !aplicadas.has(c.id)).map((c) => c.id);
}
