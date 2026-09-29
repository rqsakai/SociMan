import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, History, Loader2, Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { AssetFileCard, type RunAction } from "../../components/assets/AssetFileCard";
import { AssetThumb } from "../../components/assets/AssetThumb";
import { AssetUpload } from "../../components/assets/AssetUpload";
import { AvatarCampos, PROMPT_MAX, type PromptFields } from "../../components/assets/AvatarCampos";
import { LooksSection } from "../../components/assets/LooksSection";
import { PosesGrid } from "../../components/assets/PosesGrid";
import { UsosList, usosText } from "../../components/assets/UsosList";
import { api } from "../../lib/api";
import {
  activeFiles,
  assetKey,
  assetsKey,
  assetVersionsKey,
  isSingleFile,
  parseTags,
  tipoLabel,
  usosFromError,
  type Asset,
} from "../../lib/assets";
import { perfilKey } from "../../lib/perfis";

// /app/assets/:id: detalhe de um asset (spec 007, R9). Cabeçalho com miniatura (ou iniciais),
// tipo, tags e Arquivar/Restaurar; dados e textos (avatar: descrição para prompts, tom de voz e
// regras de imagem; cenário: prompt do ambiente); "Onde é usado"; e os arquivos: looks e poses do
// avatar, referências do cenário ou o arquivo único dos demais tipos. Toda mutação manda a
// `version` lida; o 409 de versão mostra "Recarregar".
export default function AssetDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [archiving, setArchiving] = useState(false);

  const detail = useQuery({ queryKey: assetKey(id), queryFn: () => api.assets.get(id) });
  const perfilId = detail.data?.asset.perfilId ?? "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: perfilId !== "" });
  const perfilName = perfil.data?.perfil.name;
  usePageMeta({
    title: detail.data?.asset.name ?? "Asset",
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(perfilName ? [{ label: perfilName, to: `/app/perfis/${perfilId}?aba=assets` }] : []),
    ],
  });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: assetKey(id) }),
      queryClient.invalidateQueries({ queryKey: assetVersionsKey(id) }),
      ...(perfilId ? [queryClient.invalidateQueries({ queryKey: assetsKey(perfilId) })] : []),
    ]);
  }

  const run: RunAction = async (action, done) => {
    setError(null);
    try {
      await action();
      toast.success(done);
      await refresh();
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  };

  if (detail.isPending) {
    return (
      <div className="space-y-4" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }
  if (detail.isError) {
    return (
      <div className="space-y-4">
        <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
          <Link to="/app/perfis">
            <ArrowLeft aria-hidden="true" />
            Perfis
          </Link>
        </Button>
        <ApiErrorAlert error={detail.error} />
      </div>
    );
  }

  const { asset, usos } = detail.data;
  const single = isSingleFile(asset.tipo);
  const singleFile = single ? activeFiles(asset, "arquivo")[0] : undefined;

  async function toggleArchive() {
    setArchiving(true);
    await run(
      () => (asset.archived ? api.assets.restore(asset.id, asset.version) : api.assets.archive(asset.id, asset.version)),
      asset.archived ? "Asset restaurado." : "Asset arquivado.",
    );
    setArchiving(false);
  }

  const blocking = usos.filter((u) => u.bloqueia);
  const errorUsos = usosFromError(error);

  return (
    <div className="space-y-6">
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to={`/app/perfis/${asset.perfilId}?aba=assets`}>
          <ArrowLeft aria-hidden="true" />
          Voltar para a biblioteca
        </Link>
      </Button>

      <Card className="shadow-card">
        <CardContent className="flex flex-wrap items-center gap-4">
          <div className="size-24 shrink-0 overflow-hidden rounded-xl border bg-muted">
            <AssetThumb name={asset.name} tipo={asset.tipo} cover={asset.cover} />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <h1 className="truncate text-xl font-bold sm:text-2xl">{asset.name}</h1>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary">{tipoLabel[asset.tipo]}</Badge>
              {asset.inUse && <Badge className="bg-success text-success-foreground">Em uso</Badge>}
              {asset.archived && <Badge className="bg-dark text-dark-foreground">Arquivado</Badge>}
              {asset.tags.map((t) => (
                <Badge key={t} variant="outline">
                  #{t}
                </Badge>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" asChild>
              <Link to={`/app/assets/${asset.id}/historico`}>
                <History aria-hidden="true" />
                Histórico
              </Link>
            </Button>
            <ConfirmButton
              label={asset.archived ? "Restaurar" : "Arquivar"}
              icon={asset.archived ? ArchiveRestore : Archive}
              busy={archiving}
              title={asset.archived ? `Restaurar ${asset.name}?` : `Arquivar ${asset.name}?`}
              description={
                asset.archived
                  ? "O asset volta para a biblioteca e para os seletores do kit."
                  : blocking.length > 0
                    ? `Este asset está em uso no kit (${usosText(blocking)}). Troque a imagem no kit antes de arquivar.`
                    : "O asset sai da biblioteca e dos seletores do kit. Os arquivos continuam guardados, os links continuam valendo e os cortes antigos não mudam."
              }
              onConfirm={toggleArchive}
            />
          </div>
        </CardContent>
      </Card>

      {error !== null && (
        <div className="space-y-1">
          <ApiErrorAlert error={error} onReload={() => void refresh().then(() => setError(null))} />
          {errorUsos.length > 0 && <p className="text-sm text-destructive">Em uso em: {usosText(errorUsos)}.</p>}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <DadosCard key={asset.id} asset={asset} run={run} />
        <div className="flex flex-col gap-6">
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Onde é usado</h2>
              </CardTitle>
              <CardDescription>Só o uso no kit impede arquivar; os cortes são só informação.</CardDescription>
            </CardHeader>
            <CardContent>
              <UsosList usos={usos} />
            </CardContent>
          </Card>
          {single && singleFile && (
            <ul aria-label="Arquivo">
              <AssetFileCard asset={asset} file={singleFile} index={0} run={run} />
            </ul>
          )}
        </div>
      </div>

      {asset.tipo === "avatar" && (
        <>
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Looks</h2>
              </CardTitle>
              <CardDescription>Imagens de referência agrupadas por look. Uma delas é a principal (a capa do avatar).</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <LooksSection asset={asset} run={run} />
              {!asset.archived && (
                <AssetUpload
                  assetId={asset.id}
                  tipo="avatar"
                  role="referencia"
                  submitLabel="Enviar referência"
                  looks={[...new Set(activeFiles(asset, "referencia").flatMap((f) => (f.look ? [f.look] : [])))]}
                  onUploaded={refresh}
                />
              )}
            </CardContent>
          </Card>
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Poses</h2>
              </CardTitle>
              <CardDescription>
                O avatar em posições diferentes, com rótulo e "quando usar". Reordene com os botões ou arrastando.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <PosesGrid asset={asset} role="pose" run={run} empty="Nenhuma pose ainda." />
              {!asset.archived && <AssetUpload assetId={asset.id} tipo="avatar" role="pose" submitLabel="Enviar pose" onUploaded={refresh} />}
            </CardContent>
          </Card>
        </>
      )}

      {asset.tipo === "cenario" && (
        <Card className="shadow-card">
          <CardHeader>
            <CardTitle>
              <h2>Imagens de referência</h2>
            </CardTitle>
            <CardDescription>Aparecem no seletor de fundo do kit (gancho e card final).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <PosesGrid asset={asset} role="referencia" run={run} empty="Nenhuma imagem de referência ainda." />
            {!asset.archived && (
              <AssetUpload assetId={asset.id} tipo="cenario" role="referencia" submitLabel="Enviar referência" onUploaded={refresh} />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

interface DadosForm {
  name: string;
  tags: string;
  description: string;
  texts: PromptFields;
}

const formFromAsset = (asset: Asset): DadosForm => ({
  name: asset.name,
  tags: asset.tags.join(", "),
  description: asset.description,
  texts: { prompt: asset.prompt ?? "", voiceTone: asset.voiceTone ?? "", imageRules: asset.imageRules ?? "" },
});

const sameForm = (a: DadosForm, b: DadosForm) =>
  a.name === b.name &&
  a.tags === b.tags &&
  a.description === b.description &&
  a.texts.prompt === b.texts.prompt &&
  a.texts.voiceTone === b.texts.voiceTone &&
  a.texts.imageRules === b.texts.imageRules;

// Dados do asset: nome, tags, descrição e, no avatar e no cenário, os textos de prompt. Manda só o
// que mudou, com a versão atual do asset. O prompt vai exatamente como digitado (sem trim, FR-009).
function DadosCard({ asset, run }: { asset: Asset; run: RunAction }) {
  const withPrompt = asset.tipo === "avatar" || asset.tipo === "cenario";
  const [form, setForm] = useState<DadosForm>(() => formFromAsset(asset));
  // O que veio do servidor quando o formulário foi (re)carregado: base para saber se está sujo.
  const [base, setBase] = useState<{ version: number; form: DadosForm }>(() => ({ version: asset.version, form: formFromAsset(asset) }));
  const [justSaved, setJustSaved] = useState(false);
  const { name, tags, description, texts } = form;
  const setName = (v: string) => setForm((f) => ({ ...f, name: v }));
  const setTags = (v: string) => setForm((f) => ({ ...f, tags: v }));
  const setDescription = (v: string) => setForm((f) => ({ ...f, description: v }));
  const setTexts = (v: PromptFields) => setForm((f) => ({ ...f, texts: v }));

  // A versão mudou (envio de imagem, reordenação, save): recarrega do servidor só se o formulário
  // não tem edição pendente, ou logo depois do próprio save. Com edição pendente, mantém o que foi
  // digitado; o próximo save manda a versão nova (as outras mutações não mexem nestes campos).
  if (asset.version !== base.version) {
    const fresh = formFromAsset(asset);
    if (justSaved || sameForm(form, base.form)) {
      setForm(fresh);
      setJustSaved(false);
    }
    setBase({ version: asset.version, form: fresh });
  }
  const [nameError, setNameError] = useState<string | null>(null);
  const [tagsError, setTagsError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    const tagList = parseTags(tags);
    setNameError(trimmed.length < 1 || trimmed.length > 80 ? "Dê um nome de até 80 caracteres" : null);
    setTagsError(
      tagList.length > 20 ? "Até 20 tags" : tagList.some((t) => t.length > 30) ? "Cada tag tem até 30 caracteres" : null,
    );
    if (trimmed.length < 1 || trimmed.length > 80 || tagList.length > 20 || tagList.some((t) => t.length > 30)) return;
    if (description.length > 2000 || texts.prompt.length > PROMPT_MAX || texts.voiceTone.length > 500 || texts.imageRules.length > PROMPT_MAX) return;

    const body: Parameters<typeof api.assets.update>[1] = { version: asset.version };
    if (trimmed !== asset.name) body.name = trimmed;
    if (tagList.join(",") !== asset.tags.join(",")) body.tags = tagList;
    if (description !== asset.description) body.description = description;
    if (withPrompt && texts.prompt !== (asset.prompt ?? "")) body.prompt = texts.prompt;
    if (asset.tipo === "avatar") {
      if (texts.voiceTone !== (asset.voiceTone ?? "")) body.voiceTone = texts.voiceTone;
      if (texts.imageRules !== (asset.imageRules ?? "")) body.imageRules = texts.imageRules;
    }
    if (Object.keys(body).length === 1) {
      toast.info("Nada para salvar.");
      return;
    }
    setBusy(true);
    // Marca antes da chamada: o run() espera o recarregamento, e a versão nova pode chegar antes dele
    // terminar.
    setJustSaved(true);
    if (!(await run(() => api.assets.update(asset.id, body), "Alterações salvas."))) setJustSaved(false);
    setBusy(false);
  }

  const disabled = asset.archived;
  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Dados</h2>
        </CardTitle>
        <CardDescription>{disabled ? "Restaure o asset antes de editar." : "Nome, tags e textos do asset."}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nome" error={nameError ?? undefined}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  value={name}
                  maxLength={80}
                  autoComplete="off"
                  disabled={disabled}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  onChange={(e) => setName(e.target.value)}
                />
              )}
            </Field>
            <Field label="Tags" error={tagsError ?? undefined} hint="Separadas por vírgula. Ex.: reação, promo">
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  value={tags}
                  autoComplete="off"
                  disabled={disabled}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  onChange={(e) => setTags(e.target.value)}
                />
              )}
            </Field>
          </div>
          {withPrompt && (
            <AvatarCampos
              tipo={asset.tipo as "avatar" | "cenario"}
              value={texts}
              savedPrompt={asset.prompt}
              disabled={disabled}
              onChange={setTexts}
            />
          )}
          <Field label="Notas" error={description.length > 2000 ? "Até 2.000 caracteres" : undefined}>
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={3}
                value={description}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setDescription(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" disabled={busy || disabled} aria-busy={busy}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
