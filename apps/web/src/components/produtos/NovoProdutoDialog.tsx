import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Loader2, Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PerfilBaseField } from "@/components/estudio/PerfilBaseField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/lib/perfis";
import {
  criarProduto,
  FOTO_ACCEPT,
  FOTO_MAX_BYTES,
  FOTO_MIN_LADO,
  FOTOS_MAX,
  fotoDoErro,
  LIM,
  type Produto,
} from "@/lib/produtos";

// Uma foto escolhida: a prévia é data: (a CSP não aceita blob:) e o erro é o da checagem local ou o
// 400 `invalid_image` da API (`field = "fotos[N]"`).
export interface FotoEscolhida {
  chave: string;
  arquivo: File;
  previa: string | null;
  erro: string | null;
}

function lerDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("leitura"));
    reader.readAsDataURL(file);
  });
}

function medir(src: string): Promise<{ w: number; h: number } | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

// A mesma régua da API (PNG/JPG/WebP, ≥ 512×512, até 20 MB); a API confere pelo conteúdo de novo.
export async function prepararFoto(arquivo: File): Promise<FotoEscolhida> {
  const chave = `${arquivo.name}-${arquivo.size}-${arquivo.lastModified}-${Math.random().toString(36).slice(2, 8)}`;
  if (!FOTO_ACCEPT.split(",").includes(arquivo.type)) return { chave, arquivo, previa: null, erro: "Formato não aceito: use PNG, JPG ou WebP." };
  if (arquivo.size > FOTO_MAX_BYTES) return { chave, arquivo, previa: null, erro: "Foto maior que 20 MB." };
  const previa = await lerDataUrl(arquivo).catch(() => null);
  const dim = previa ? await medir(previa) : null;
  if (dim && (dim.w < FOTO_MIN_LADO || dim.h < FOTO_MIN_LADO)) {
    return { chave, arquivo, previa, erro: `Foto pequena demais (${dim.w} × ${dim.h}); o mínimo é ${FOTO_MIN_LADO} × ${FOTO_MIN_LADO}.` };
  }
  return { chave, arquivo, previa, erro: null };
}

// "Novo produto" (spec 012, US1, T022): nome, até 6 fotos (uma por cor ou variante, na ordem da
// lista), observação e o link da loja (opcional). Criar já pede a ficha ao Claude; a tela do produto
// acompanha o resto. Spec 029: o perfil base nasce com o filtro da lista (ou o da cena) e pode ficar
// vazio; `onCriado` (criação no lugar da cena) fica na tela em vez de abrir o produto.
export function NovoProdutoDialog({
  perfilId,
  open,
  onOpenChange,
  onCriado,
}: {
  perfilId: string | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onCriado?: (produto: Produto) => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [obs, setObs] = useState("");
  const [urlLoja, setUrlLoja] = useState("");
  const [fotos, setFotos] = useState<FotoEscolhida[]>([]);
  const [inputKey, setInputKey] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [progresso, setProgresso] = useState(0);
  const [perfilBase, setPerfilBase] = useState<string | null>(perfilId);

  function abrir(o: boolean) {
    if (o) {
      setName("");
      setObs("");
      setUrlLoja("");
      setFotos([]);
      setErrors({});
      setError(null);
      setPerfilBase(perfilId);
    }
    onOpenChange(o);
  }

  async function escolher(lista: FileList | null) {
    const novos = Array.from(lista ?? []);
    setInputKey((k) => k + 1);
    if (novos.length === 0) return;
    const vagas = FOTOS_MAX - fotos.length;
    if (novos.length > vagas) toast.warning(`No máximo ${FOTOS_MAX} fotos: ${novos.length - Math.max(0, vagas)} ficaram de fora.`);
    const preparadas = await Promise.all(novos.slice(0, Math.max(0, vagas)).map(prepararFoto));
    setFotos((atual) => [...atual, ...preparadas].slice(0, FOTOS_MAX));
    setErrors((e) => ({ ...e, fotos: "" }));
  }

  function mover(i: number, delta: -1 | 1) {
    setFotos((atual) => {
      const j = i + delta;
      if (j < 0 || j >= atual.length) return atual;
      const copia = [...atual];
      [copia[i], copia[j]] = [copia[j]!, copia[i]!];
      return copia;
    });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = "Informe o nome";
    if (urlLoja.trim() && !/^https:\/\/\S+$/.test(urlLoja.trim())) errs.urlLoja = "Use um link que comece com https://";
    if (fotos.some((f) => f.erro)) errs.fotos = "Tire ou troque as fotos com problema.";
    setErrors(errs);
    if (Object.values(errs).some(Boolean)) return;
    setBusy(true);
    setError(null);
    setProgresso(0);
    try {
      const produto = await criarProduto(perfilBase, { name, obs, urlLoja, fotos: fotos.map((f) => f.arquivo) }, setProgresso);
      toast.success(fotos.length > 0 ? "Produto criado. A ficha técnica já foi pedida." : "Produto criado como rascunho.");
      await queryClient.invalidateQueries({ queryKey: ["produtos"] });
      onOpenChange(false);
      if (onCriado) onCriado(produto);
      else void navigate(`/app/produtos/${produto.id}`);
    } catch (err) {
      const i = fotoDoErro(err);
      if (i !== null && fotos[i]) {
        setFotos((atual) => atual.map((f, k) => (k === i ? { ...f, erro: errorText(err).replace(/^fotos\[\d+\]:\s*/, "") } : f)));
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && abrir(o)}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>Novo produto</DialogTitle>
            <DialogDescription>
              Uma foto por cor ou variante, na ordem da lista. O SociMan pede a ficha técnica ao Claude e depois faz o recorte (e, para
              roupa, o flat lay) de cada variante.
            </DialogDescription>
          </DialogHeader>

          <Field label="Nome do produto" error={errors.name} hint={`Nome interno. ${name.length}/${LIM.nome}`}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} value={name} maxLength={LIM.nome} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setName(e.target.value)} />
            )}
          </Field>

          <PerfilBaseField value={perfilBase} onChange={setPerfilBase} disabled={busy} hint="O guia e as palavras proibidas deste perfil entram na ficha técnica." />

          <Field
            label="Fotos"
            error={errors.fotos || undefined}
            hint={`Até ${FOTOS_MAX} fotos PNG, JPG ou WebP, com no mínimo ${FOTO_MIN_LADO} × ${FOTO_MIN_LADO} e até 20 MB cada (${fotos.length}/${FOTOS_MAX}).`}
          >
            {({ id, describedBy }) => (
              <FileField
                key={inputKey}
                id={id}
                accept={FOTO_ACCEPT}
                multiple
                disabled={busy || fotos.length >= FOTOS_MAX}
                aria-describedby={describedBy}
                rotuloBotao="Escolher fotos"
                onChange={(e) => void escolher(e.target.files)}
              />
            )}
          </Field>

          {fotos.length > 0 && (
            <ol aria-label="Fotos escolhidas" className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {fotos.map((f, i) => (
                <li key={f.chave} data-testid={`foto-${i + 1}`} className="space-y-1.5 rounded-lg border p-2">
                  <div className="aspect-square overflow-hidden rounded-md bg-muted">
                    {f.previa ? <img src={f.previa} alt={`Prévia da foto ${i + 1}`} className="size-full object-contain" /> : null}
                  </div>
                  <p className="truncate text-xs text-muted-foreground" title={f.arquivo.name}>
                    {i + 1}. {f.arquivo.name}
                  </p>
                  {f.erro && (
                    <p role="alert" className="text-xs text-destructive" data-testid={`erro-foto-${i + 1}`}>
                      {f.erro}
                    </p>
                  )}
                  <div className="flex gap-1">
                    <Button type="button" size="icon-sm" variant="ghost" aria-label={`Subir foto ${i + 1}`} disabled={busy || i === 0} onClick={() => mover(i, -1)}>
                      <ArrowUp aria-hidden="true" />
                    </Button>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`Descer foto ${i + 1}`}
                      disabled={busy || i === fotos.length - 1}
                      onClick={() => mover(i, 1)}
                    >
                      <ArrowDown aria-hidden="true" />
                    </Button>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      className="ml-auto"
                      aria-label={`Remover foto ${i + 1}`}
                      disabled={busy}
                      onClick={() => setFotos((atual) => atual.filter((_, k) => k !== i))}
                    >
                      <X aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              ))}
            </ol>
          )}

          <Field label="Observação" hint={`Vai para o pedido da ficha (ex.: "shorts de cintura alta canelados, 3 cores, logo LS"). ${obs.length}/${LIM.obs}`}>
            {({ id, describedBy }) => <Textarea id={id} rows={3} value={obs} maxLength={LIM.obs} aria-describedby={describedBy} onChange={(e) => setObs(e.target.value)} />}
          </Field>

          <Field label="Link da loja (opcional)" error={errors.urlLoja} hint="Só informativo: o SociMan não consulta a loja.">
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                type="url"
                inputMode="url"
                placeholder="https://"
                value={urlLoja}
                maxLength={LIM.urlLoja}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setUrlLoja(e.target.value)}
              />
            )}
          </Field>

          {error !== null && <ApiErrorAlert error={error} />}

          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={busy} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
              {busy && fotos.length > 0 ? `Enviando ${Math.round(progresso * 100)}%` : "Criar produto"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
