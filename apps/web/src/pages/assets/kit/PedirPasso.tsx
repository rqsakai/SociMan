import type { ImageRef } from "@sociman/contract";
import { Loader2, Sparkles, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { LibraryImageDialog } from "@/components/assets/LibraryImageDialog";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { AssetTipo } from "@/lib/assets";
import { PerfilBaseGeracao } from "@/components/estudio/PerfilBaseField";
import { useCriarGeracao, type GeracaoAlvo } from "@/lib/geracoes";
import { INSTRUCAO_MAX, QUANDO_USAR_MAX, ROTULO_MAX } from "@/lib/padrao";

export interface CampoTexto {
  label: string;
  hint?: string;
  obrigatoria?: boolean;
  placeholder?: string;
  // idioma do texto (padrão: inglês, como as instruções dos modelos de imagem)
  lang?: string;
}

// Pedido de um passo da 025 (spec 025, T019/T040/T043; contracts/passos.md): só os campos que o passo
// usa. A API confere a ordem do kit (409 `passo_fechado`), a menoridade (400 `menor_proibido`), o
// rótulo repetido e o pedido em andamento antes de criar o job; o erro aparece em pt-BR no alerta.
// Spec 029: `perfilId` é o perfil base do item (pode ser null), o padrão do "Perfil base desta geração".
export function PedirPasso({
  perfilId,
  alvoTipo,
  alvoId,
  passo,
  n,
  instrucao,
  rotulo,
  quandoUsar,
  base,
  referenciaBiblioteca,
  texto,
  submitLabel = "Gerar opções",
  disabled,
  onCriada,
}: {
  perfilId: string | null;
  alvoTipo: GeracaoAlvo;
  alvoId: string;
  passo: string;
  n?: number;
  instrucao?: CampoTexto;
  rotulo?: CampoTexto;
  quandoUsar?: boolean;
  // base do look/pose: o corpo-base (vazio) ou uma pose escolhida (imageId)
  base?: { label: string; opcoes: { imageId: string; nome: string }[] };
  referenciaBiblioteca?: readonly AssetTipo[];
  texto?: CampoTexto;
  submitLabel?: string;
  disabled?: boolean;
  onCriada?: () => void;
}) {
  const criar = useCriarGeracao();
  const [perfilBase, setPerfilBase] = useState<string | null>(perfilId);
  const [vInstrucao, setInstrucao] = useState("");
  const [vRotulo, setRotulo] = useState("");
  const [vQuando, setQuando] = useState("");
  const [vBase, setBase] = useState("");
  const [vTexto, setTexto] = useState("");
  const [referencia, setReferencia] = useState<{ image: ImageRef; nome: string } | null>(null);
  const [erros, setErros] = useState<Record<string, string>>({});

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (instrucao?.obrigatoria && !vInstrucao.trim()) errs.instrucao = "Preencha este campo";
    if (rotulo && !vRotulo.trim()) errs.rotulo = "Dê um rótulo";
    if (texto && !vTexto.trim()) errs.texto = "Escreva o texto";
    setErros(errs);
    if (Object.keys(errs).length > 0) return;
    const referencias = referencia ? [referencia.image.id] : vBase ? [vBase] : [];
    try {
      await criar.mutateAsync({
        alvoTipo,
        alvoId,
        passo,
        perfilBaseId: perfilBase,
        instrucao: vInstrucao.trim(),
        referencias,
        ...(n ? { nOpcoes: n } : {}),
        ...(rotulo ? { rotulo: vRotulo.trim() } : {}),
        ...(texto ? { texto: vTexto.trim() } : {}),
        ...(quandoUsar && vQuando.trim() ? { extras: { quandoUsar: vQuando.trim() } } : {}),
      });
      toast.success("Pedido enviado. As opções aparecem aqui quando ficarem prontas.");
      setInstrucao("");
      setRotulo("");
      setQuando("");
      setTexto("");
      setReferencia(null);
      onCriada?.();
    } catch {
      // o erro aparece no alerta (criar.error)
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate data-testid={`pedir-${passo}`}>
      <PerfilBaseGeracao value={perfilBase} onChange={setPerfilBase} disabled={disabled} />
      {rotulo && (
        <Field label={rotulo.label} hint={rotulo.hint} error={erros.rotulo}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              value={vRotulo}
              maxLength={ROTULO_MAX}
              disabled={disabled}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setRotulo(e.target.value)}
            />
          )}
        </Field>
      )}
      {instrucao && (
        <Field label={instrucao.label} hint={instrucao.hint} error={erros.instrucao}>
          {({ id, describedBy, invalid }) => (
            <Textarea
              id={id}
              rows={3}
              lang={instrucao.lang ?? "en"}
              value={vInstrucao}
              maxLength={INSTRUCAO_MAX}
              placeholder={instrucao.placeholder}
              disabled={disabled}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setInstrucao(e.target.value)}
            />
          )}
        </Field>
      )}
      {quandoUsar && (
        <Field label="Quando usar" hint="Opcional. Ex.: ao apontar para o produto na bancada.">
          {({ id, describedBy }) => (
            <Input id={id} value={vQuando} maxLength={QUANDO_USAR_MAX} disabled={disabled} aria-describedby={describedBy} onChange={(e) => setQuando(e.target.value)} />
          )}
        </Field>
      )}
      {base && (
        <Field label={base.label} hint="A identidade sempre vem do rosto frontal.">
          {({ id, describedBy }) => (
            <NativeSelect id={id} value={vBase} disabled={disabled} aria-describedby={describedBy} onChange={(e) => setBase(e.target.value)}>
              <option value="">Corpo-base</option>
              {base.opcoes.map((o) => (
                <option key={o.imageId} value={o.imageId}>
                  Pose: {o.nome}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
      )}
      {texto && (
        <Field label={texto.label} hint={texto.hint} error={erros.texto}>
          {({ id, describedBy, invalid }) => (
            <Textarea
              id={id}
              rows={3}
              value={vTexto}
              maxLength={500}
              disabled={disabled}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setTexto(e.target.value)}
            />
          )}
        </Field>
      )}
      {referenciaBiblioteca && (
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
                tipos={referenciaBiblioteca}
                value={referencia?.image.id ?? null}
                onPick={(image, item) => setReferencia({ image, nome: item.label ? `${item.assetName}: ${item.label}` : item.assetName })}
              />
            )}
          </div>
        </div>
      )}
      {criar.isError && <ApiErrorAlert error={criar.error} />}
      <Button type="submit" disabled={disabled || criar.isPending} aria-busy={criar.isPending}>
        {criar.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
        {submitLabel}
      </Button>
    </form>
  );
}
