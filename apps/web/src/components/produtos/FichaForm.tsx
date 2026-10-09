import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Copy, Loader2, Plus, Save, Undo2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import {
  campoFichaLabel,
  contarPalavras,
  COR_MAX,
  fichaParaForm,
  invalidarProduto,
  LIM_LISTA,
  LIM_TEXTO,
  MATERIAL_PALAVRAS,
  produtoKey,
  variantesAtivas,
  type CampoLista,
  type CampoTexto,
  type Produto,
  type ProdutoFichaIn,
} from "@/lib/produtos";
import { useRascunho } from "./useRascunho";

type Cores = Record<string, { corEn: string; corPt: string }>;
interface Rascunho {
  ficha: ProdutoFichaIn;
  cores: Cores;
}

function rascunhoDe(p: Produto): Rascunho {
  const cores: Cores = {};
  for (const v of variantesAtivas(p)) cores[v.id] = { corEn: v.corEn ?? "", corPt: v.corPt ?? "" };
  return { ficha: fichaParaForm(p.ficha), cores };
}

// O selo dos campos que vão literais para os prompts (em inglês, sem tradução).
export function SeloLiteral() {
  return (
    <Badge variant="outline" className="text-[11px] font-normal" data-testid="selo-literal">
      vai literal para os prompts
    </Badge>
  );
}

// Campo de erro do 400 `invalid_produto` (`detalhesVisiveis[2]` → `detalhesVisiveis`).
function campoBase(field: string | null): string | null {
  if (!field) return null;
  const m = /^cores\[(\d+)\]/.exec(field);
  if (m) return `cores[${m[1]}]`;
  return field.split("[")[0] ?? null;
}

// Ficha técnica (spec 012, US3, T033): todos os campos editáveis, listas item a item, o selo
// "vai literal para os prompts" nos campos em inglês, "Copiar descrição para prompts", o switch
// `precisaFlat` e as cores das variantes. Campo vazio = não preenchido (a ficha à mão pode ir por
// partes; completa só para aprovar). Salvar: `PUT …/ficha` com a ficha inteira e as cores.
export function FichaForm({ produto, manual = false, disabled = false }: { produto: Produto; manual?: boolean; disabled?: boolean }) {
  const queryClient = useQueryClient();
  const r = useRascunho(rascunhoDe(produto), produto.version);
  const { ficha, cores } = r.valor;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const ativas = variantesAtivas(produto);

  const erroCampo = error instanceof ApiError && error.code === "invalid_produto" ? campoBase(error.field) : null;
  const msgCampo = (campo: string) => (erroCampo === campo && error instanceof ApiError ? error.message.replace(/^[^:]+:\s*/, "") : undefined);

  const setCampo = <K extends keyof ProdutoFichaIn>(k: K, v: ProdutoFichaIn[K]) => r.setValor({ ficha: { ...ficha, [k]: v }, cores });
  const setCor = (id: string, k: "corEn" | "corPt", v: string) =>
    r.setValor({ ficha, cores: { ...cores, [id]: { ...(cores[id] ?? { corEn: "", corPt: "" }), [k]: v } } });

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const novo = await api.produtos.salvarFicha(produto.id, {
        version: r.versao,
        ficha: {
          ...ficha,
          detalhesVisiveis: ficha.detalhesVisiveis.filter((s) => s.trim()),
          cuidados: ficha.cuidados.filter((s) => s.trim()),
        },
        cores: ativas.map((v) => ({ varianteId: v.id, corEn: cores[v.id]?.corEn ?? "", corPt: cores[v.id]?.corPt ?? "" })),
      });
      queryClient.setQueryData(produtoKey(produto.id), novo);
      r.reiniciar(rascunhoDe(novo), novo.version);
      toast.success("Ficha salva.");
      await invalidarProduto(queryClient, produto.id, produto.perfilId);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function copiarDescricao() {
    try {
      await navigator.clipboard.writeText(ficha.descricaoPrompt);
      toast.success("Descrição para prompts copiada.");
    } catch {
      toast.error("Não foi possível copiar. Selecione o texto e copie à mão.");
    }
  }

  const texto = (campo: CampoTexto, opts: { literal?: boolean; linhas?: number; hint?: string } = {}) => {
    const valor = ficha[campo];
    const contagem = `${valor.length}/${LIM_TEXTO[campo]}`;
    return (
      <Field
        label={campoFichaLabel[campo]}
        action={opts.literal ? <SeloLiteral /> : undefined}
        error={msgCampo(campo)}
        hint={opts.hint ? `${opts.hint} ${contagem}` : contagem}
      >
        {({ id, describedBy, invalid }) =>
          opts.linhas ? (
            <Textarea
              id={id}
              rows={opts.linhas}
              value={valor}
              maxLength={LIM_TEXTO[campo]}
              disabled={disabled}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              lang={opts.literal ? "en" : undefined}
              onChange={(e) => setCampo(campo, e.target.value)}
            />
          ) : (
            <Input
              id={id}
              value={valor}
              maxLength={LIM_TEXTO[campo]}
              disabled={disabled}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              lang={opts.literal ? "en" : undefined}
              onChange={(e) => setCampo(campo, e.target.value)}
            />
          )
        }
      </Field>
    );
  };

  const palavras = contarPalavras(ficha.materialEn);

  return (
    <form onSubmit={(e) => void salvar(e)} className="space-y-5" data-testid="ficha-form" noValidate>
      {manual && !produto.ficha && (
        <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
          Preenchendo à mão: a ficha fica com a origem "Preenchida à mão" e libera os recortes. Pode salvar por partes; para aprovar, todos
          os campos precisam estar preenchidos.
        </p>
      )}
      {r.mudouFora && (
        <p role="status" className="rounded-lg border border-warning p-3 text-sm">
          A ficha mudou em outro lugar enquanto você editava. Salvar vai pedir para recarregar.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {texto("nomeComercial")}
        {texto("categoria", { hint: 'Ex.: "roupa > shorts".' })}
        {texto("materialEn", {
          literal: true,
          hint: `De ${MATERIAL_PALAVRAS[0]} a ${MATERIAL_PALAVRAS[1]} palavras exatas (ex.: "ribbed knit"); agora ${palavras}.`,
        })}
        {texto("materialPt")}
      </div>
      {texto("formatoCorte", { literal: true, linhas: 2 })}
      <ListaEditavel
        campo="detalhesVisiveis"
        literal
        itens={ficha.detalhesVisiveis}
        disabled={disabled}
        erro={msgCampo("detalhesVisiveis")}
        dica="Logo com texto, cor e posição; cós; costuras."
        onChange={(itens) => setCampo("detalhesVisiveis", itens)}
      />
      {texto("tamanhoRelativo", { literal: true, hint: 'Ex.: "all variants identical in size and cut".' })}
      <div className="space-y-2">
        {texto("descricaoPrompt", { literal: true, linhas: 3, hint: "Uma frase em inglês, usada literalmente nas cenas." })}
        <Button type="button" variant="outline" size="sm" disabled={!ficha.descricaoPrompt.trim()} onClick={() => void copiarDescricao()}>
          <Copy aria-hidden="true" />
          Copiar descrição para prompts
        </Button>
      </div>
      <ListaEditavel
        campo="cuidados"
        itens={ficha.cuidados}
        disabled={disabled}
        erro={msgCampo("cuidados")}
        dica='O que os modelos de vídeo erram neste produto (ex.: "não trocar a malha canelada por jeans").'
        onChange={(itens) => setCampo("cuidados", itens)}
      />
      {texto("descricaoVenda", { linhas: 3, hint: "2 a 3 frases, só o que se vê nas fotos." })}

      <label className="flex items-start gap-3 rounded-lg border p-3">
        <Switch
          checked={ficha.precisaFlat ?? false}
          disabled={disabled}
          onCheckedChange={(on) => setCampo("precisaFlat", on)}
          aria-label={campoFichaLabel.precisaFlat}
          className="mt-0.5"
        />
        <span className="space-y-0.5 text-sm">
          <span className="block font-medium">{campoFichaLabel.precisaFlat}</span>
          <span className="block text-muted-foreground">
            Roupa ou tecido fotografado em forma 3D. Ligado, toda variante precisa de flat escolhido para aprovar; desligado, os flats
            ficam guardados mas não vão para o render.
          </span>
        </span>
      </label>

      {ativas.length > 0 && (
        <fieldset className="space-y-3" data-testid="ficha-cores">
          <legend className="text-sm font-medium">Cores das variantes</legend>
          {ativas.map((v, i) => {
            const n = i + 1;
            const erro = erroCampo === `cores[${i}]` ? msgCampo(`cores[${i}]`) : undefined;
            return (
              <div key={v.id} className="grid gap-3 rounded-lg border p-3 sm:grid-cols-[3rem_1fr_1fr]">
                <img src={(v.recorte ?? v.original).thumbUrl} alt={`Variante ${n}`} className="size-12 rounded-md border bg-white object-contain" />
                <Field label={`Cor da variante ${n} (inglês)`} action={<SeloLiteral />} error={erro}>
                  {({ id, describedBy, invalid }) => (
                    <Input
                      id={id}
                      lang="en"
                      value={cores[v.id]?.corEn ?? ""}
                      maxLength={COR_MAX}
                      disabled={disabled}
                      aria-invalid={invalid}
                      aria-describedby={describedBy}
                      onChange={(e) => setCor(v.id, "corEn", e.target.value)}
                    />
                  )}
                </Field>
                <Field label={`Cor da variante ${n} (português)`}>
                  {({ id }) => (
                    <Input id={id} value={cores[v.id]?.corPt ?? ""} maxLength={COR_MAX} disabled={disabled} onChange={(e) => setCor(v.id, "corPt", e.target.value)} />
                  )}
                </Field>
              </div>
            );
          })}
        </fieldset>
      )}

      {error !== null && (
        <ApiErrorAlert
          error={error}
          onReload={() => {
            setError(null);
            r.reiniciar(rascunhoDe(produto), produto.version);
            void invalidarProduto(queryClient, produto.id);
          }}
        />
      )}

      {!disabled && (
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy || (!r.sujo && !manual)} aria-busy={busy}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar ficha
          </Button>
          {r.sujo && (
            <Button type="button" variant="ghost" disabled={busy} onClick={() => r.reiniciar(rascunhoDe(produto), produto.version)}>
              <Undo2 aria-hidden="true" />
              Descartar alterações
            </Button>
          )}
        </div>
      )}
    </form>
  );
}

// Lista editável item a item (detalhes visíveis, cuidados): até 12 itens de até 200 caracteres.
function ListaEditavel({
  campo,
  itens,
  literal,
  disabled,
  erro,
  dica,
  onChange,
}: {
  campo: CampoLista;
  itens: string[];
  literal?: boolean;
  disabled?: boolean;
  erro?: string;
  dica: string;
  onChange: (itens: string[]) => void;
}) {
  const rotulo = campoFichaLabel[campo];
  return (
    <fieldset className="space-y-2" data-testid={`lista-${campo}`}>
      <legend className="flex min-h-7 w-full flex-wrap items-center justify-between gap-x-2 text-sm font-medium">
        {rotulo}
        {literal && <SeloLiteral />}
      </legend>
      {itens.length === 0 && <p className="text-sm text-muted-foreground">Nenhum item.</p>}
      <ol className="space-y-2">
        {itens.map((item, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-5 shrink-0 text-right text-xs text-muted-foreground tabular-nums">{i + 1}.</span>
            <Input
              aria-label={`${rotulo}, item ${i + 1}`}
              value={item}
              maxLength={LIM_LISTA.item}
              disabled={disabled}
              lang={literal ? "en" : undefined}
              onChange={(e) => onChange(itens.map((v, k) => (k === i ? e.target.value : v)))}
            />
            {!disabled && (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remover item ${i + 1} de ${rotulo.toLowerCase()}`}
                onClick={() => onChange(itens.filter((_, k) => k !== i))}
              >
                <X aria-hidden="true" />
              </Button>
            )}
          </li>
        ))}
      </ol>
      <p className="text-xs text-muted-foreground">
        {dica} Até {LIM_LISTA.itens} itens.
      </p>
      {erro && (
        <p role="alert" className="text-sm text-destructive">
          {erro}
        </p>
      )}
      {!disabled && itens.length < LIM_LISTA.itens && (
        <Button type="button" variant="outline" size="sm" aria-label={`Adicionar item em ${rotulo.toLowerCase()}`} onClick={() => onChange([...itens, ""])}>
          <Plus aria-hidden="true" />
          Adicionar item
        </Button>
      )}
    </fieldset>
  );
}
