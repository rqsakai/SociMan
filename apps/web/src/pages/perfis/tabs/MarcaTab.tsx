import type { Conta, Perfil } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, History, Loader2, Save } from "lucide-react";
import { useId, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Page } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { IaSugestoes } from "../../../components/ia/IaSugestoes";
import { ColorTokenInput } from "../../../components/marca/ColorTokenInput";
import { FontSelect } from "../../../components/marca/FontSelect";
import { FundoImagePicker } from "../../../components/marca/FundoImagePicker";
import { KitPreview, type PreviewMoment } from "../../../components/marca/KitPreview";
import { NumberField } from "../../../components/marca/NumberField";
import { PaletteEditor } from "../../../components/marca/PaletteEditor";
import { SectionCard } from "../../../components/marca/SectionCard";
import { useKitFonts } from "../../../components/marca/useKitFonts";
import { WatermarkImagePicker } from "../../../components/marca/WatermarkImagePicker";
import {
  cortesKey,
  fundosKey,
  fundoTipoLabel,
  ganchoPosicaoLabel,
  ganchoTamanhoLabel,
  kitFieldText,
  kitKey,
  kitTokens,
  kitErrorField,
  kitVersionsKey,
  legendaEfeitoLabel,
  legendaEstiloLabel,
  legendaPosicaoLabel,
  marcaDaguaKey,
  marcaPosicaoLabel,
  marcaTipoLabel,
  paletteUsage,
  replaceColorKey,
  validateKit,
  type FontOption,
  type Kit,
  type KitTokens,
} from "../../../lib/marca";
import { api } from "../../../lib/api";
import { comRebase, useFormRebase, type IaOnSave } from "../../../lib/ia";
import { contaPlatformText } from "../../../lib/perfis";
import { formatDateTime } from "@/lib/tz";


// Aba Marca do perfil (US1, T013): editor do kit por seção com a prévia 9:16 ao lado (embaixo no
// celular). Salva o kit inteiro com a versão lida (controle otimista); o histórico fica em
// /app/perfis/:id/kit/historico.
export function MarcaTab({ perfil, contas }: { perfil: Perfil; contas: Conta[] }) {
  const kit = useQuery({ queryKey: kitKey(perfil.id), queryFn: () => api.kit.get(perfil.id) });

  if (kit.isPending) {
    return (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-96 rounded-xl" />
        <Skeleton className="aspect-[9/16] rounded-xl" />
      </div>
    );
  }
  if (kit.isError) return <ApiErrorAlert error={kit.error} />;

  return (
    <KitEditor
      // Versão nova (salvar, reverter, recarregar depois de conflito) recomeça o rascunho.
      key={`${kit.data.kit.version}-${kit.dataUpdatedAt}`}
      perfil={perfil}
      contas={contas}
      kit={kit.data.kit}
      fontOptions={kit.data.fontOptions}
      onReload={() => void kit.refetch()}
    />
  );
}

function KitEditor({
  perfil,
  contas,
  kit,
  fontOptions,
  onReload,
}: {
  perfil: Perfil;
  contas: Conta[];
  kit: Kit;
  fontOptions: FontOption[];
  onReload: () => void;
}) {
  const queryClient = useQueryClient();
  const initial = useMemo(() => kitTokens(kit), [kit]);
  // O Aplicar da IA (bordões e séries) salva o kit e remonta o editor pela `key`; o rascunho das
  // outras seções volta por cima do kit novo (spec 008, R-9).
  const rebase = useFormRebase<KitTokens>(`kit:${perfil.id}`);
  const [draft, setDraft] = useState<KitTokens>(() => rebase.retomado ?? initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [moment, setMoment] = useState<PreviewMoment>("inicio");
  const [sampleHook, setSampleHook] = useState("3 achadinhos que salvaram minha cozinha");
  const [watermarkUrl, setWatermarkUrl] = useState<string | null>(null);
  // URLs das imagens de fundo recém-enviadas, até a lista do perfil recarregar.
  const [fundoUrls, setFundoUrls] = useState<Record<string, string>>({});
  const fontsReady = useKitFonts(fontOptions);
  const savedKeys = useMemo(() => new Set(initial.palette.map((c) => c.chave)), [initial]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  const activeContas = contas.filter((c) => !c.archived);
  const conta = activeContas.find((c) => c.id === draft.watermark.conta_id) ?? null;

  // Imagem própria escolhida: a URL vem da lista de imagens de marca d'água do perfil.
  const images = useQuery({
    queryKey: marcaDaguaKey(perfil.id),
    queryFn: () => api.marcaDagua.list(perfil.id),
    enabled: draft.watermark.tipo === "imagem",
  });
  const chosenImage = images.data?.items.find((i) => i.id === draft.watermark.imagem_id);

  // Imagens de fundo do gancho e do card final (FR-005a): a mesma lista do perfil para os dois.
  const fundos = useQuery({
    queryKey: fundosKey(perfil.id),
    queryFn: () => api.fundos.list(perfil.id),
    enabled: draft.hook.fundo_tipo === "imagem" || draft.endCard.fundo_tipo === "imagem",
  });
  const fundoUrl = (tipo: "cor" | "imagem", id: string | null | undefined) => {
    if (tipo !== "imagem" || !id) return null;
    return fundos.data?.items.find((i) => i.id === id)?.urls.medium ?? fundoUrls[id] ?? null;
  };

  // Fundo da prévia: o pôster do último corte pronto do perfil (R7), quando houver.
  const cortes = useQuery({
    queryKey: [...cortesKey(perfil.id), "pronto"],
    queryFn: () => api.cortes.list(perfil.id, { status: "pronto", limit: 1 }),
    retry: false,
  });
  const poster = cortes.data?.items[0]?.posterUrl ?? null;

  function set<K extends "caption" | "hook" | "watermark" | "endCard">(section: K, patch: Partial<KitTokens[K]>) {
    setDraft((d) => ({ ...d, [section]: { ...d[section], ...patch } }));
  }

  async function save() {
    setApiError(null);
    const found = validateKit(draft);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      toast.error("Corrija os campos destacados antes de salvar.");
      focusFirstInvalid();
      return;
    }
    setSaving(true);
    try {
      await api.kit.put(perfil.id, {
        version: kit.version,
        ...draft,
        palette: draft.palette.map((c) => ({ ...c, nome: c.nome.trim() })),
        endCard: { ...draft.endCard, cta: draft.endCard.cta.trim() },
      });
      toast.success("Kit salvo.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: kitKey(perfil.id) }),
        queryClient.invalidateQueries({ queryKey: kitVersionsKey(perfil.id) }),
      ]);
    } catch (err) {
      const refused = kitErrorField(err);
      if (refused) {
        setErrors({ [refused.field]: refused.message });
        focusFirstInvalid();
      }
      setApiError(err);
    } finally {
      setSaving(false);
    }
  }

  // Aplicar das sugestões: os tokens SALVOS com só aquela lista trocada (nunca o rascunho, R-10); a
  // lista aplicada também entra no rascunho guardado.
  const iaSaveLista =
    (campo: "catchphrases" | "series"): IaOnSave<string[]> =>
    async (lista, ia) => {
      setApiError(null);
      await comRebase(rebase, dirty ? { ...draft, [campo]: lista } : null, async () => {
        await api.kit.put(perfil.id, { version: kit.version, ...kitTokens(kit), [campo]: lista, ia });
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: kitKey(perfil.id) }),
        queryClient.invalidateQueries({ queryKey: kitVersionsKey(perfil.id) }),
      ]);
    };
  const iaLista = { perfilId: perfil.id, alvo: { entityType: "kit" as const, entityId: null }, onReload };

  async function exportKit() {
    setExporting(true);
    try {
      const { blob, filename } = await api.kit.exportFile(perfil.id);
      // <a download> com object URL: é download, não carga de recurso, então a CSP não interfere.
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      toast.success(`Kit exportado: ${filename}`);
    } catch (err) {
      setApiError(err);
    } finally {
      setExporting(false);
    }
  }

  const err = (field: string) => errors[field];
  const clearError = (field: string) =>
    setErrors(({ [field]: _removed, ...rest }) => rest);
  const { caption, hook, watermark, endCard } = draft;
  const refusedField = kitErrorField(apiError);
  const apiField = refusedField ? kitFieldText(refusedField.field) : null;

  return (
    <Page>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          <Card className="gap-0 py-4 shadow-card">
            <CardContent className="flex flex-wrap items-center gap-3">
              <div className="mr-auto flex flex-wrap items-center gap-2 text-sm">
                {kit.persisted ? (
                  <Badge variant="secondary">Versão {kit.version}</Badge>
                ) : (
                  <Badge variant="outline">Kit padrão (ainda não salvo)</Badge>
                )}
                {kit.updatedAt && (
                  <span className="text-muted-foreground">
                    {kit.updatedBy?.name ?? "—"} · {formatDateTime(kit.updatedAt)}
                  </span>
                )}
                {dirty && <Badge className="bg-warning text-warning-foreground">Alterações não salvas</Badge>}
              </div>
              <Button type="button" variant="ghost" size="sm" asChild>
                <Link to={`/app/perfis/${perfil.id}/kit/historico`}>
                  <History aria-hidden="true" />
                  Histórico do kit
                </Link>
              </Button>
              <Button type="button" variant="outline" size="sm" disabled={exporting} aria-busy={exporting} onClick={() => void exportKit()}>
                {exporting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Download aria-hidden="true" />}
                Exportar kit (JSON)
              </Button>
              <Button type="button" size="sm" disabled={saving} aria-busy={saving} onClick={() => void save()}>
                {saving ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                Salvar kit
              </Button>
            </CardContent>
          </Card>

          {apiError !== null && (
            <div className="space-y-1">
              {apiField && <p className="text-sm font-medium text-destructive">Campo recusado: {apiField}</p>}
              <ApiErrorAlert error={apiError} onReload={onReload} />
            </div>
          )}

          <SectionCard title="Paleta" description="Cores com nome, usadas nos seletores de cor das outras seções.">
            <PaletteEditor
              palette={draft.palette}
              savedKeys={savedKeys}
              usage={(key) => paletteUsage(draft, key)}
              onChange={(palette) => setDraft((d) => ({ ...d, palette }))}
              onRekey={(from, to) => setDraft((d) => replaceColorKey(d, from, to))}
              errors={errors}
            />
          </SectionCard>

          <SectionCard title="Legenda" description="Os parâmetros que o gerador de cortes aplica na legenda.">
            <div className="grid gap-4 sm:grid-cols-2">
              <FontSelect label="Fonte" value={caption.fonte} options={fontOptions} onChange={(fonte) => set("caption", { fonte })} error={err("caption.fonte")} />
              <NumberField label="Tamanho" value={caption.tamanho} min={10} max={200} onChange={(tamanho) => set("caption", { tamanho })} error={err("caption.tamanho")} />
              <ColorTokenInput label="Cor do texto" value={caption.cor_texto} palette={draft.palette} onChange={(cor_texto) => set("caption", { cor_texto })} error={err("caption.cor_texto")} />
              <ColorTokenInput label="Cor de destaque" value={caption.cor_destaque} palette={draft.palette} onChange={(cor_destaque) => set("caption", { cor_destaque })} error={err("caption.cor_destaque")} />
              <ColorTokenInput label="Cor do contorno" value={caption.cor_contorno} palette={draft.palette} onChange={(cor_contorno) => set("caption", { cor_contorno })} error={err("caption.cor_contorno")} />
              <NumberField label="Espessura do contorno" value={caption.espessura_contorno} min={0} max={10} onChange={(espessura_contorno) => set("caption", { espessura_contorno })} error={err("caption.espessura_contorno")} />
              <ColorTokenInput label="Cor do fundo" value={caption.cor_fundo} palette={draft.palette} onChange={(cor_fundo) => set("caption", { cor_fundo })} error={err("caption.cor_fundo")} />
              <NumberField label="Opacidade do fundo" value={caption.opacidade_fundo} min={0} max={1} step={0.05} hint="De 0 (sem fundo) a 1" onChange={(opacidade_fundo) => set("caption", { opacidade_fundo })} error={err("caption.opacidade_fundo")} />
              <SelectField label="Estilo" value={caption.estilo} labels={legendaEstiloLabel} onChange={(estilo) => set("caption", { estilo })} error={err("caption.estilo")} />
              <SelectField label="Efeito" value={caption.efeito} labels={legendaEfeitoLabel} onChange={(efeito) => set("caption", { efeito })} error={err("caption.efeito")} />
              <SelectField label="Posição" value={caption.posicao} labels={legendaPosicaoLabel} onChange={(posicao) => set("caption", { posicao })} error={err("caption.posicao")} />
              <SwitchField label="Maiúsculas" checked={caption.maiusculas} onChange={(maiusculas) => set("caption", { maiusculas })} />
            </div>
          </SectionCard>

          <SectionCard
            title="Gancho"
            description="O cartão com o texto do gancho no início do corte."
            enabled={hook.ligado}
            onEnabledChange={(ligado) => set("hook", { ligado })}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <FontSelect label="Fonte" value={hook.fonte} options={fontOptions} onChange={(fonte) => set("hook", { fonte })} error={err("hook.fonte")} />
              <SelectField label="Tamanho" value={hook.tamanho} labels={ganchoTamanhoLabel} onChange={(tamanho) => set("hook", { tamanho })} error={err("hook.tamanho")} />
              <ColorTokenInput label="Cor do texto" value={hook.cor_texto} palette={draft.palette} onChange={(cor_texto) => set("hook", { cor_texto })} error={err("hook.cor_texto")} />
              <SelectField label="Tipo de fundo" value={hook.fundo_tipo} labels={fundoTipoLabel} onChange={(fundo_tipo) => set("hook", { fundo_tipo })} error={err("hook.fundo_tipo")} />
              <ColorTokenInput label="Cor do fundo" value={hook.cor_fundo} palette={draft.palette} onChange={(cor_fundo) => set("hook", { cor_fundo })} error={err("hook.cor_fundo")} />
              {hook.fundo_tipo === "imagem" ? (
                <NumberField label="Opacidade da camada" value={hook.opacidade_fundo} min={0} max={1} step={0.05} hint="A cor do fundo por cima da imagem, de 0 (só a imagem) a 1" onChange={(opacidade_fundo) => set("hook", { opacidade_fundo })} error={err("hook.opacidade_fundo")} />
              ) : (
                <NumberField label="Opacidade do fundo" value={hook.opacidade_fundo} min={0} max={1} step={0.05} hint="De 0 (sem fundo) a 1" onChange={(opacidade_fundo) => set("hook", { opacidade_fundo })} error={err("hook.opacidade_fundo")} />
              )}
              <ColorTokenInput label="Cor do contorno" value={hook.cor_contorno} palette={draft.palette} onChange={(cor_contorno) => set("hook", { cor_contorno })} error={err("hook.cor_contorno")} />
              <NumberField label="Espessura do contorno" value={hook.espessura_contorno} min={0} max={10} onChange={(espessura_contorno) => set("hook", { espessura_contorno })} error={err("hook.espessura_contorno")} />
              <SelectField label="Posição" value={hook.posicao} labels={ganchoPosicaoLabel} onChange={(posicao) => set("hook", { posicao })} error={err("hook.posicao")} />
              <NumberField label="Duração (s)" value={hook.duracao_s} min={1} max={10} step={0.5} hint="De 1 a 10 s, em passos de 0,5" onChange={(duracao_s) => set("hook", { duracao_s })} error={err("hook.duracao_s")} />
            </div>
            {hook.fundo_tipo === "imagem" && (
              <FundoImagePicker
                perfilId={perfil.id}
                value={hook.fundo_imagem_id ?? null}
                onChange={(image) => {
                  set("hook", { fundo_imagem_id: image.id });
                  clearError("hook.fundo_imagem_id");
                  setFundoUrls((u) => ({ ...u, [image.id]: image.urls.medium }));
                }}
                error={err("hook.fundo_imagem_id")}
              />
            )}
          </SectionCard>

          <SectionCard
            title="Marca d'água"
            description="Logo, imagem própria ou o @ da conta durante todo o corte."
            enabled={watermark.ligado}
            onEnabledChange={(ligado) => set("watermark", { ligado })}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField label="Tipo" value={watermark.tipo} labels={marcaTipoLabel} onChange={(tipo) => set("watermark", { tipo })} error={err("watermark.tipo")} />
              <SelectField label="Posição" value={watermark.posicao} labels={marcaPosicaoLabel} onChange={(posicao) => set("watermark", { posicao })} error={err("watermark.posicao")} />
            </div>
            {watermark.tipo === "logo" && !perfil.logo && (
              <p role="alert" className="text-sm text-destructive">
                O perfil ainda não tem logo. Envie o logo na aba Dados ou escolha outro tipo.
              </p>
            )}
            {watermark.tipo === "imagem" && (
              <WatermarkImagePicker
                perfilId={perfil.id}
                value={watermark.imagem_id ?? null}
                onChange={(image) => {
                  set("watermark", { imagem_id: image.id });
                  setWatermarkUrl(image.urls.medium);
                }}
                error={err("watermark.imagem_id")}
              />
            )}
            {watermark.tipo === "texto" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Conta do @" error={err("watermark.conta_id")} hint={activeContas.length === 0 ? "Cadastre uma conta na aba Contas." : undefined}>
                  {({ id, describedBy, invalid }) => (
                    <NativeSelect
                      id={id}
                      aria-invalid={invalid}
                      aria-describedby={describedBy}
                      value={watermark.conta_id ?? ""}
                      onChange={(e) => set("watermark", { conta_id: e.target.value || null })}
                    >
                      <option value="">Escolha a conta</option>
                      {activeContas.map((c) => (
                        <option key={c.id} value={c.id}>
                          @{c.handle} ({contaPlatformText(c)})
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
                <FontSelect label="Fonte do @" value={watermark.fonte} options={fontOptions} onChange={(fonte) => set("watermark", { fonte })} error={err("watermark.fonte")} />
                <ColorTokenInput label="Cor do @" value={watermark.cor_texto} palette={draft.palette} onChange={(cor_texto) => set("watermark", { cor_texto })} error={err("watermark.cor_texto")} />
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-3">
              <NumberField label="Escala (%)" value={watermark.escala_pct} min={5} max={40} hint="Da largura do vídeo, de 5 a 40" onChange={(escala_pct) => set("watermark", { escala_pct })} error={err("watermark.escala_pct")} />
              <NumberField label="Opacidade (%)" value={watermark.opacidade_pct} min={10} max={100} onChange={(opacidade_pct) => set("watermark", { opacidade_pct })} error={err("watermark.opacidade_pct")} />
              <NumberField label="Margem (%)" value={watermark.margem_pct} min={0} max={10} hint="Da largura, de 0 a 10" onChange={(margem_pct) => set("watermark", { margem_pct })} error={err("watermark.margem_pct")} />
            </div>
          </SectionCard>

          <SectionCard
            title="Card final"
            description="O CTA por cima dos últimos segundos (a duração do corte não muda)."
            enabled={endCard.ligado}
            onEnabledChange={(ligado) => set("endCard", { ligado })}
          >
            <Field label="CTA" error={err("endCard.cta")} hint={`${endCard.cta.length}/80`}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  value={endCard.cta}
                  maxLength={80}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  onChange={(e) => set("endCard", { cta: e.target.value })}
                />
              )}
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <FontSelect label="Fonte" value={endCard.fonte} options={fontOptions} onChange={(fonte) => set("endCard", { fonte })} error={err("endCard.fonte")} />
              <NumberField label="Duração (s)" value={endCard.duracao_s} min={1} max={5} step={0.5} hint="De 1 a 5 s, em passos de 0,5" onChange={(duracao_s) => set("endCard", { duracao_s })} error={err("endCard.duracao_s")} />
              <ColorTokenInput label="Cor do texto" value={endCard.cor_texto} palette={draft.palette} onChange={(cor_texto) => set("endCard", { cor_texto })} error={err("endCard.cor_texto")} />
              <SelectField label="Tipo de fundo" value={endCard.fundo_tipo} labels={fundoTipoLabel} onChange={(fundo_tipo) => set("endCard", { fundo_tipo })} error={err("endCard.fundo_tipo")} />
              <ColorTokenInput label="Cor do fundo" value={endCard.cor_fundo} palette={draft.palette} onChange={(cor_fundo) => set("endCard", { cor_fundo })} error={err("endCard.cor_fundo")} />
              {endCard.fundo_tipo === "imagem" && (
                <NumberField label="Opacidade da camada" value={endCard.opacidade_fundo} min={0} max={1} step={0.05} hint="A cor do fundo por cima da imagem, de 0 (só a imagem) a 1" onChange={(opacidade_fundo) => set("endCard", { opacidade_fundo })} error={err("endCard.opacidade_fundo")} />
              )}
              <SwitchField label="Mostrar logo" checked={endCard.mostrar_logo} onChange={(mostrar_logo) => set("endCard", { mostrar_logo })} />
            </div>
            {endCard.fundo_tipo === "imagem" && (
              <FundoImagePicker
                perfilId={perfil.id}
                value={endCard.fundo_imagem_id ?? null}
                onChange={(image) => {
                  set("endCard", { fundo_imagem_id: image.id });
                  clearError("endCard.fundo_imagem_id");
                  setFundoUrls((u) => ({ ...u, [image.id]: image.urls.medium }));
                }}
                error={err("endCard.fundo_imagem_id")}
              />
            )}
          </SectionCard>

          <SectionCard title="Bordões e séries" description="Textos de referência para roteiros e títulos; um por linha.">
            <div className="grid gap-4 sm:grid-cols-2">
              <IaSugestoes tipo="kit.bordoes" {...iaLista} value={draft.catchphrases} onSave={iaSaveLista("catchphrases")} campo="Bordões">
                {(botao) => (
                  <LinesField label="Bordões" action={botao} value={draft.catchphrases} max={120} onChange={(catchphrases) => setDraft((d) => ({ ...d, catchphrases }))} error={err("catchphrases")} />
                )}
              </IaSugestoes>
              <IaSugestoes tipo="kit.series" {...iaLista} value={draft.series} onSave={iaSaveLista("series")} campo="Séries">
                {(botao) => (
                  <LinesField label="Séries" action={botao} value={draft.series} max={60} onChange={(series) => setDraft((d) => ({ ...d, series }))} error={err("series")} />
                )}
              </IaSugestoes>
            </div>
          </SectionCard>
        </div>

        <aside aria-label="Prévia do kit" className="space-y-3 lg:sticky lg:top-20 lg:self-start">
          <div className="flex justify-center gap-1 rounded-full bg-muted p-1" role="group" aria-label="Momento da prévia">
            {(
              [
                ["inicio", "Início"],
                ["fim", "Fim (card final)"],
              ] as const
            ).map(([value, label]) => (
              <Button
                key={value}
                type="button"
                size="sm"
                variant={moment === value ? "default" : "ghost"}
                className="flex-1 rounded-full"
                aria-pressed={moment === value}
                onClick={() => setMoment(value)}
              >
                {label}
              </Button>
            ))}
          </div>
          <KitPreview
            tokens={draft}
            fontsReady={fontsReady}
            moment={moment}
            hookText={sampleHook || " "}
            logoUrl={perfil.logo?.urls.medium ?? null}
            watermarkImageUrl={chosenImage?.urls.medium ?? watermarkUrl}
            handle={conta?.handle ?? activeContas[0]?.handle ?? null}
            backgroundUrl={poster}
            hookImageUrl={fundoUrl(hook.fundo_tipo, hook.fundo_imagem_id)}
            endCardImageUrl={fundoUrl(endCard.fundo_tipo, endCard.fundo_imagem_id)}
          />
          <Field label="Texto de exemplo do gancho">
            {({ id }) => <Input id={id} value={sampleHook} maxLength={120} onChange={(e) => setSampleHook(e.target.value)} />}
          </Field>
        </aside>
      </div>
    </Page>
  );
}

// Depois do render com os erros, leva o foco ao primeiro campo recusado.
function focusFirstInvalid() {
  requestAnimationFrame(() => {
    const el = document.querySelector<HTMLElement>('[role="tabpanel"] [aria-invalid="true"]');
    el?.scrollIntoView({ block: "center" });
    el?.focus({ preventScroll: true });
  });
}

function SelectField<T extends string>({
  label,
  value,
  labels,
  onChange,
  error,
}: {
  label: string;
  value: T;
  labels: Record<T, string>;
  onChange: (value: T) => void;
  error?: string;
}) {
  return (
    <Field label={label} error={error}>
      {({ id, describedBy, invalid }) => (
        <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} value={value} onChange={(e) => onChange(e.target.value as T)}>
          {(Object.entries(labels) as [T, string][]).map(([v, text]) => (
            <option key={v} value={v}>
              {text}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );
}

function SwitchField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  const id = useId();
  return (
    <div className="flex items-center gap-2 self-end pb-2">
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}

// Lista de textos como uma linha por item (linhas vazias e espaços nas pontas são ignorados).
function LinesField({
  label,
  value,
  max,
  onChange,
  error,
  action,
}: {
  label: string;
  value: string[];
  max: number;
  onChange: (value: string[]) => void;
  error?: string;
  action?: ReactNode;
}) {
  const [text, setText] = useState(value.join("\n"));
  return (
    <Field label={label} action={action} error={error} hint={`Um por linha; até 20, com até ${max} caracteres cada.`}>
      {({ id, describedBy, invalid }) => (
        <Textarea
          id={id}
          rows={5}
          value={text}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          onChange={(e) => {
            setText(e.target.value);
            onChange(
              e.target.value
                .split("\n")
                .map((s) => s.trim())
                .filter(Boolean),
            );
          }}
        />
      )}
    </Field>
  );
}
