/*
 * Formulário do guia de comunicação (spec 017, US1): tom, faça/não faça, vocabulário, proibidas,
 * emojis, hashtags fixas (e, na conta, o máximo delas) e até N exemplos. As listas são "uma por
 * linha"; os contadores e limites vêm de `guia.limites` (a API é a fonte). Só o dono edita: para o
 * membro tudo fica desabilitado, sem Salvar, Montar nem Testar.
 *
 * <GuiaForm key={guia.version} nivel="conta" perfilId contaId guia fixasPerfil contas />
 *
 * O "Montar com IA" só preenche o formulário; a proposta vale ao salvar (o `ia` vai no PUT).
 */
import type { Conta, IaAplicacao } from "@sociman/contract";
import { Loader2, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { EmptyState } from "@/components/shell/EmptyState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/authStore";
import {
  camposDe,
  contasComProblema,
  emojisLabel,
  erroDoCampo,
  erroDoExemplo,
  errosDeCampo,
  exemploTipoLabel,
  fixasDe,
  fixasSomadas,
  formDe,
  guiaContaPath,
  itens,
  maximoFixas,
  tamanhoDe,
  useGuiaMutations,
  type CampoLista,
  type Guia,
  type GuiaCampos,
  type GuiaExemplo,
  type GuiaForm as GuiaFormValues,
  type GuiaLimites,
  type Nivel,
} from "@/lib/guia";
import { cn } from "@/lib/utils";
import { MontarGuiaDialog } from "./MontarGuiaDialog";
import { TestarGuiaDialog } from "./TestarGuiaDialog";

const fmt = (n: number) => n.toLocaleString("pt-BR");

export interface GuiaFormProps {
  nivel: Nivel;
  perfilId: string;
  contaId?: string;
  guia: Guia;
  // Conta: as fixas do perfil salvas (entram na soma e no "sobram N vagas").
  fixasPerfil?: string[];
  // Contas do perfil, para o "Testar guia" (na conta, só ela).
  contas: Conta[];
  // Perfil ou conta arquivados: só leitura.
  arquivado?: boolean;
}

export function GuiaForm({ nivel, perfilId, contaId, guia, fixasPerfil = [], contas, arquivado }: GuiaFormProps) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const podeEditar = isOwner && !arquivado;
  const { salvarPerfil, salvarConta } = useGuiaMutations();
  const [f, setF] = useState<GuiaFormValues>(() => formDe(guia.campos));
  const [erro, setErro] = useState<unknown>(null);
  const [salvando, setSalvando] = useState(false);
  // Chamada do "Montar com IA" usada no formulário: vai no `ia` do Salvar (desfecho aplicada/editada).
  const [montarChamadaId, setMontarChamadaId] = useState<string | null>(null);
  const limites = guia.limites;
  const erros = errosDeCampo(erro);
  const contasErro = contasComProblema(erro);
  const soValidacao = Object.keys(erros).length > 0 || contasErro.length > 0;

  const set = <K extends keyof GuiaFormValues>(k: K, v: GuiaFormValues[K]) => setF((cur) => ({ ...cur, [k]: v }));

  async function salvar() {
    setErro(null);
    setSalvando(true);
    const ia: IaAplicacao[] | undefined = montarChamadaId ? [{ tipoCampo: "guia.montar", chamadaId: montarChamadaId }] : undefined;
    const body = { version: guia.version, campos: camposDe(f, nivel), ...(ia ? { ia } : {}) };
    try {
      if (nivel === "conta" && contaId) await salvarConta(contaId, body);
      else await salvarPerfil(perfilId, body);
      toast.success("Guia salvo.");
    } catch (err) {
      setErro(err);
    } finally {
      setSalvando(false);
    }
  }

  function usarProposta(proposta: GuiaCampos, chamadaId: string) {
    // Fixas, máximo e exemplos não vêm da IA: ficam como estão no formulário.
    const p = formDe({ ...proposta, hashtagsFixas: [], maxHashtagsFixas: null, exemplos: [] });
    setF((cur) => ({
      ...cur,
      tom: p.tom,
      faca: p.faca,
      naoFaca: p.naoFaca,
      vocabulario: p.vocabulario,
      proibidas: p.proibidas,
      emojis: p.emojis,
      emojisPreferidos: p.emojisPreferidos,
    }));
    setMontarChamadaId(chamadaId);
    setErro(null);
    toast.info("Proposta no formulário. Revise e salve para valer.");
  }

  const tamanho = tamanhoDe(f);

  return (
    <form
      className="space-y-5"
      noValidate
      aria-label={nivel === "perfil" ? "Guia de comunicação do perfil" : "Guia de comunicação da conta"}
      onSubmit={(e) => {
        e.preventDefault();
        if (podeEditar) void salvar();
      }}
    >
      {!isOwner && <p className="text-sm text-muted-foreground">Só o dono edita o guia; você pode consultar.</p>}
      {isOwner && arquivado && <p className="text-sm text-muted-foreground">{nivel === "perfil" ? "Perfil arquivado" : "Conta arquivada"}: o guia fica guardado, sem uso.</p>}

      {podeEditar && (
        <div className="flex flex-wrap gap-2">
          <MontarGuiaDialog perfilId={perfilId} contaId={contaId} guiaAtual={camposDe(f, nivel)} onUsar={usarProposta} />
          <TestarGuiaDialog
            perfilId={perfilId}
            nivel={nivel}
            contaId={contaId}
            contas={contas}
            guia={camposDe(f, nivel)}
            onErroGuia={setErro}
          />
        </div>
      )}

      <Field
        label="Tom de voz"
        error={erroDoCampo(erros, "tom")}
        hint={<Contagem atual={f.tom.trim().length} max={limites?.tomMax} unidade="caracteres" />}
      >
        {({ id, describedBy, invalid }) => (
          <Textarea
            id={id}
            rows={2}
            value={f.tom}
            disabled={!podeEditar}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            placeholder="Ex.: narrador de RPG, íntimo e bem-humorado"
            onChange={(e) => set("tom", e.target.value)}
          />
        )}
      </Field>

      <div className="grid gap-4 md:grid-cols-2">
        <Lista campo="faca" label="Faça" f={f} set={set} erros={erros} max={limites?.regrasItens} disabled={!podeEditar} />
        <Lista campo="naoFaca" label="Não faça" f={f} set={set} erros={erros} max={limites?.regrasItens} disabled={!podeEditar} />
        <Lista
          campo="vocabulario"
          label="Vocabulário da casa"
          f={f}
          set={set}
          erros={erros}
          max={limites?.vocabularioItens}
          disabled={!podeEditar}
          placeholder={"taverneiro\naventureiro"}
        />
        <Lista
          campo="proibidas"
          label="Palavras proibidas"
          f={f}
          set={set}
          erros={erros}
          max={limites?.proibidasItens}
          disabled={!podeEditar}
          extra="Nunca aparecem no que a IA gera, nem nos prompts de imagem."
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Emojis" error={erroDoCampo(erros, "emojis")}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect
              id={id}
              value={f.emojis}
              disabled={!podeEditar}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => set("emojis", e.target.value as GuiaFormValues["emojis"])}
            >
              <option value="">{nivel === "conta" ? "Como no perfil" : "Não definido"}</option>
              {Object.entries(emojisLabel).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Lista
          campo="emojisPreferidos"
          label="Emojis preferidos"
          f={f}
          set={set}
          erros={erros}
          max={limites?.emojisItens}
          disabled={!podeEditar}
          rows={2}
        />
      </div>

      <Fixas nivel={nivel} f={f} set={set} erros={erros} limites={limites} fixasPerfil={fixasPerfil} disabled={!podeEditar} />

      <Exemplos f={f} set={set} erros={erros} limites={limites} disabled={!podeEditar} />

      <p
        aria-live="polite"
        className={cn("text-sm text-muted-foreground", limites && tamanho > limites.totalMax && "font-medium text-destructive")}
      >
        Tamanho do guia: {fmt(tamanho)}
        {limites ? `/${fmt(limites.totalMax)}` : ""} caracteres
      </p>
      {erros.total && (
        <p role="alert" className="text-sm text-destructive">
          {erros.total}
        </p>
      )}

      {contasErro.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>Contas afetadas por esta mudança</AlertTitle>
          <AlertDescription>
            <ul className="list-disc space-y-1 pl-5">
              {contasErro.map((c) => (
                <li key={c.contaId}>
                  <Link to={guiaContaPath(c.contaId)} className="font-medium underline">
                    {c.rotulo}
                  </Link>
                  {c.mensagem ? `: ${c.mensagem}` : ` (${c.campos.join(", ")})`}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      {erro !== null && (soValidacao ? (
        <p role="alert" className="text-sm text-destructive">
          O guia não foi salvo: corrija os campos marcados.
        </p>
      ) : (
        <ApiErrorAlert error={erro} />
      ))}

      {podeEditar && (
        <Button type="submit" disabled={salvando} aria-busy={salvando}>
          {salvando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
          {salvando ? "Salvando…" : "Salvar guia"}
        </Button>
      )}
    </form>
  );
}

type SetCampo = <K extends keyof GuiaFormValues>(k: K, v: GuiaFormValues[K]) => void;

function Contagem({ atual, max, unidade }: { atual: number; max: number | undefined; unidade: string }) {
  if (max === undefined) return null;
  return (
    <span aria-live="polite" className={cn(atual > max && "font-medium text-destructive")}>
      {fmt(atual)}/{fmt(max)} {unidade}
    </span>
  );
}

function Lista({
  campo,
  label,
  f,
  set,
  erros,
  max,
  disabled,
  placeholder,
  extra,
  rows = 4,
}: {
  campo: CampoLista;
  label: string;
  f: GuiaFormValues;
  set: SetCampo;
  erros: Record<string, string>;
  max: number | undefined;
  disabled: boolean;
  placeholder?: string;
  extra?: string;
  rows?: number;
}) {
  const n = itens(f[campo]).length;
  return (
    <Field
      label={label}
      error={erroDoCampo(erros, campo)}
      hint={
        <span className="flex flex-wrap justify-between gap-2">
          <span>{extra ? `Uma por linha. ${extra}` : "Uma por linha."}</span>
          <Contagem atual={n} max={max} unidade="itens" />
        </span>
      }
    >
      {({ id, describedBy, invalid }) => (
        <Textarea
          id={id}
          rows={rows}
          value={f[campo]}
          disabled={disabled}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          placeholder={placeholder}
          onChange={(e) => set(campo, e.target.value)}
        />
      )}
    </Field>
  );
}

function Fixas({
  nivel,
  f,
  set,
  erros,
  limites,
  fixasPerfil,
  disabled,
}: {
  nivel: Nivel;
  f: GuiaFormValues;
  set: SetCampo;
  erros: Record<string, string>;
  limites: GuiaLimites | undefined;
  fixasPerfil: string[];
  disabled: boolean;
}) {
  const proprias = fixasDe(f.hashtagsFixas);
  const efetivas = nivel === "conta" ? fixasSomadas(fixasPerfil, proprias) : proprias;
  const maximo = limites ? (nivel === "conta" ? maximoFixas(f, limites) : limites.hashtagsFixasPerfil) : undefined;
  const vagas = limites ? Math.max(limites.hashtagsFixasTeto - efetivas.length, 0) : undefined;
  const acima = maximo !== undefined && efetivas.length > maximo;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field
        label="Hashtags fixas"
        error={erroDoCampo(erros, "hashtagsFixas")}
        hint={
          <span className="space-y-0.5">
            <span className="block">Uma por linha. Entram sempre nas hashtags geradas e contam no limite da postagem.</span>
            {maximo !== undefined && vagas !== undefined && (
              <span aria-live="polite" className={cn("block", acima && "font-medium text-destructive")}>
                {nivel === "conta"
                  ? `Perfil e conta: ${efetivas.length} de no máximo ${maximo} fixas`
                  : `${efetivas.length}/${maximo} fixas`}
                {" · "}
                {vagas === 1 ? "sobra 1 vaga" : `sobram ${vagas} vagas`} para a IA
              </span>
            )}
          </span>
        }
      >
        {({ id, describedBy, invalid }) => (
          <Textarea
            id={id}
            rows={3}
            value={f.hashtagsFixas}
            disabled={disabled}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            placeholder="#atavernanerd"
            onChange={(e) => set("hashtagsFixas", e.target.value)}
          />
        )}
      </Field>
      {nivel === "conta" && (
        <Field
          label="Máximo de hashtags fixas"
          error={erroDoCampo(erros, "maxHashtagsFixas")}
          hint={
            limites
              ? `Vazio: ${limites.hashtagsFixasPadrao}. De 0 a ${limites.hashtagsFixasTeto} (o limite de hashtags da postagem), somando as do perfil.`
              : undefined
          }
        >
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="number"
              inputMode="numeric"
              min={0}
              max={limites?.hashtagsFixasTeto}
              value={f.maxHashtagsFixas}
              disabled={disabled}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              placeholder={limites ? String(limites.hashtagsFixasPadrao) : undefined}
              onChange={(e) => set("maxHashtagsFixas", e.target.value)}
            />
          )}
        </Field>
      )}
    </div>
  );
}

function Exemplos({
  f,
  set,
  erros,
  limites,
  disabled,
}: {
  f: GuiaFormValues;
  set: SetCampo;
  erros: Record<string, string>;
  limites: GuiaLimites | undefined;
  disabled: boolean;
}) {
  const max = limites?.exemplos;
  const muda = (i: number, e: Partial<GuiaExemplo>) => set("exemplos", f.exemplos.map((x, j) => (j === i ? { ...x, ...e } : x)));
  const geral = erros.exemplos;
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-medium">Exemplos aprovados</legend>
      <p className="text-xs text-muted-foreground">
        Títulos, legendas ou bordões que são "a cara" da conta; a IA imita o jeito.
        {max !== undefined && ` ${f.exemplos.length}/${max}.`}
      </p>
      {f.exemplos.map((ex, i) => (
        <div key={i} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[10rem_1fr_auto]">
          <Field label={`Tipo do exemplo ${i + 1}`}>
            {({ id }) => (
              <NativeSelect id={id} value={ex.tipo} disabled={disabled} onChange={(e) => muda(i, { tipo: e.target.value as GuiaExemplo["tipo"] })}>
                {Object.entries(exemploTipoLabel).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field
            label={`Exemplo ${i + 1}`}
            error={erroDoExemplo(erros, i)}
            hint={<Contagem atual={ex.texto.trim().length} max={limites?.exemploMax} unidade="caracteres" />}
          >
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={2}
                value={ex.texto}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => muda(i, { texto: e.target.value })}
              />
            )}
          </Field>
          {!disabled && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="self-end"
              aria-label={`Remover o exemplo ${i + 1}`}
              onClick={() => set("exemplos", f.exemplos.filter((_, j) => j !== i))}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          )}
        </div>
      ))}
      {f.exemplos.length === 0 && <EmptyState titulo="Nenhum exemplo." className="py-4" />}
      {geral && (
        <p role="alert" className="text-sm text-destructive">
          {geral}
        </p>
      )}
      {!disabled && (
        // Sem trava no máximo: o 6º é recusado pela API no campo (a tela avisa pelo contador).
        <Button type="button" variant="outline" size="sm" onClick={() => set("exemplos", [...f.exemplos, { tipo: "legenda", texto: "" }])}>
          <Plus aria-hidden="true" />
          Adicionar exemplo
        </Button>
      )}
    </fieldset>
  );
}
