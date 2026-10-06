import { zodResolver } from "@hookform/resolvers/zod";
import type { Perfil, UpdatePerfilRequest } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, Loader2, Save } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ImageUpload } from "../../components/ImageUpload";
import { ProfileAvatar } from "../../components/ProfileAvatar";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { IaAssist } from "../../components/ia/IaAssist";
import { api } from "../../lib/api";
import { editPerfilForm, type EditPerfilForm } from "../../lib/forms";
import { comRebase, useFormRebase, type IaOnSave } from "../../lib/ia";
import {
  formatPerfilValue,
  languageLabel,
  perfilFieldLabel,
  perfilKey,
  perfilStatusLabel,
  perfilVersionsKey,
} from "../../lib/perfis";
import { ContasTab } from "./ContasTab";
import { CortesTab } from "./tabs/CortesTab";
import { FontesTab } from "./tabs/FontesTab";
import { MarcaTab } from "./tabs/MarcaTab";
import { AssetsTab } from "./tabs/AssetsTab";
import { PadroesCorteTab } from "./tabs/PadroesCorteTab";
import { GuiaTab } from "./tabs/GuiaTab";
import { CenasTab } from "./tabs/CenasTab";

const tabs = [
  { id: "dados", label: "Dados" },
  { id: "contas", label: "Contas" },
  { id: "marca", label: "Marca" },
  { id: "guia", label: "Guia" },
  { id: "fontes", label: "Fontes" },
  { id: "cortes", label: "Cortes" },
  { id: "padroes", label: "Padrões de corte" },
  { id: "assets", label: "Assets" },
  { id: "cenas", label: "Cenas" },
  { id: "historico", label: "Histórico" },
] as const;
type TabId = (typeof tabs)[number]["id"];

// /app/perfis/:id: cabeçalho "profile" (banner, logo e abas em pílula), abas Dados, Contas, Marca,
// Guia, Fontes, Cortes e Histórico, e as ações Arquivar/Restaurar. A aba fica na URL (?aba=contas) para o voltar do
// navegador e o link direto funcionarem. Sucesso vira toast; erro da API fica num Alert.
export default function PerfilDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab: TabId = tabs.some((t) => t.id === params.get("aba")) ? (params.get("aba") as TabId) : "dados";
  const [error, setError] = useState<unknown>(null);
  const [archiving, setArchiving] = useState(false);

  const detail = useQuery({ queryKey: perfilKey(id), queryFn: () => api.perfis.get(id) });
  usePageMeta({ title: detail.data?.perfil.name ?? "Perfil", breadcrumbs: [{ label: "Perfis", to: "/app/perfis" }] });

  // Qualquer mutação do perfil ou das contas muda a lista, o detalhe e o histórico.
  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: perfilKey(id) }),
      queryClient.invalidateQueries({ queryKey: perfilVersionsKey(id) }),
      queryClient.invalidateQueries({ queryKey: ["perfis"] }),
    ]);
  }

  async function reload() {
    setError(null);
    await refresh();
  }

  function selectTab(next: string) {
    setError(null);
    setParams(next === "dados" ? {} : { aba: next }, { replace: true });
  }

  if (detail.isPending) {
    return (
      <div className="space-y-4" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-44 w-full rounded-xl" />
        <Skeleton className="mx-4 h-24 rounded-xl" />
      </div>
    );
  }
  if (detail.isError) {
    return (
      <div className="space-y-4">
        <BackLink />
        <ApiErrorAlert error={detail.error} />
      </div>
    );
  }

  const { perfil, contas } = detail.data;
  const activeContas = contas.filter((c) => !c.archived && c.status === "ativa").length;

  async function toggleArchive() {
    setError(null);
    setArchiving(true);
    try {
      if (perfil.archived) {
        await api.perfis.restore(perfil.id, perfil.version);
        toast.success("Perfil restaurado.");
      } else {
        await api.perfis.archive(perfil.id, perfil.version);
        if (activeContas > 0) {
          toast.info(
            "Perfil arquivado. As contas ativas continuam ativas nas plataformas: o SociMan não publica nem encerra nada fora dele.",
            { duration: 10_000 },
          );
        } else {
          toast.success("Perfil arquivado.");
        }
      }
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setArchiving(false);
    }
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <Tabs value={tab} onValueChange={selectTab} className="gap-6">
        <PerfilHeader
          perfil={perfil}
          tabs={
            <TabsList aria-label="Seções do perfil" className="h-10 max-w-full justify-start overflow-x-auto rounded-full bg-muted p-1 [scrollbar-width:none]">
              {tabs.map((t) => (
                <TabsTrigger key={t.id} value={t.id} className="rounded-full px-4 data-[state=active]:shadow-sm">
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
          }
          actions={
            <ConfirmButton
              label={perfil.archived ? "Restaurar" : "Arquivar"}
              icon={perfil.archived ? ArchiveRestore : Archive}
              busy={archiving}
              title={perfil.archived ? `Restaurar ${perfil.name}?` : `Arquivar ${perfil.name}?`}
              description={
                perfil.archived
                  ? "O perfil volta para a lista padrão."
                  : activeContas > 0
                    ? "O perfil sai da lista padrão. As contas ativas continuam ativas nas plataformas: o SociMan não publica nem encerra nada fora dele."
                    : "O perfil sai da lista padrão e pode ser restaurado depois."
              }
              onConfirm={toggleArchive}
            />
          }
        />

        {error !== null && <ApiErrorAlert error={error} onReload={() => void reload()} />}

        <TabsContent value="dados">
          <DadosTab
            key={`${perfil.id}-${perfil.version}`}
            perfil={perfil}
            onSaved={async (text) => {
              toast.success(text);
              await refresh();
            }}
            onError={setError}
            onSubmitStart={() => setError(null)}
            onRefresh={refresh}
          />
        </TabsContent>
        <TabsContent value="contas">
          <ContasTab perfil={perfil} contas={contas} onChanged={refresh} onError={setError} onActionStart={() => setError(null)} />
        </TabsContent>
        <TabsContent value="marca">
          <MarcaTab perfil={perfil} contas={contas} />
        </TabsContent>
        <TabsContent value="guia">
          <GuiaTab perfil={perfil} contas={contas} />
        </TabsContent>
        <TabsContent value="fontes">
          <FontesTab perfil={perfil} />
        </TabsContent>
        <TabsContent value="cortes">
          <CortesTab perfil={perfil} />
        </TabsContent>
        <TabsContent value="padroes">
          <PadroesCorteTab perfil={perfil} contas={contas} />
        </TabsContent>
        <TabsContent value="assets">
          <AssetsTab perfil={perfil} />
        </TabsContent>
        <TabsContent value="cenas">
          <CenasTab perfil={perfil} />
        </TabsContent>
        <TabsContent value="historico">
          <PerfilHistorico perfil={perfil} onReverted={refresh} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/app/perfis" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" aria-hidden="true" />
      Perfis
    </Link>
  );
}

// Cabeçalho no estilo "profile": banner largo (a imagem do perfil ou um degradê) e um cartão
// branco sobreposto com o logo, o nome, o status, as abas em pílula e a ação principal.
function PerfilHeader({ perfil, tabs, actions }: { perfil: Perfil; tabs: ReactNode; actions: ReactNode }) {
  return (
    <div>
      <div className="relative h-36 overflow-hidden rounded-xl bg-sidebar-gradient shadow-card sm:h-48">
        {perfil.banner && (
          <img src={perfil.banner.urls.medium} alt={`Banner de ${perfil.name}`} className="size-full object-cover" />
        )}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/40 to-dark/50" aria-hidden="true" />
      </div>
      <div className="relative mx-3 -mt-12 rounded-xl bg-card p-4 shadow-card sm:mx-6 sm:-mt-16">
        <div className="flex flex-wrap items-center gap-4">
          <ProfileAvatar name={perfil.name} logo={perfil.logo} size="lg" className="ring-4 ring-card" />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-bold sm:text-2xl">{perfil.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span className="font-mono text-xs">{perfil.slug}</span>
              <Badge variant="secondary">{perfilStatusLabel[perfil.status]}</Badge>
              {perfil.archived && <Badge className="bg-dark text-dark-foreground">Arquivado</Badge>}
            </div>
          </div>
          <div className="flex w-full flex-wrap items-center gap-3 lg:w-auto">
            {tabs}
            {actions}
          </div>
        </div>
      </div>
    </div>
  );
}

const perfilValues = (perfil: Perfil): EditPerfilForm => ({
  name: perfil.name,
  niche: perfil.niche,
  bio: perfil.bio,
  language: perfil.language,
  status: perfil.status,
});

function DadosTab({
  perfil,
  onSaved,
  onError,
  onSubmitStart,
  onRefresh,
}: {
  perfil: Perfil;
  onSaved: (text: string) => Promise<void>;
  onError: (err: unknown) => void;
  onSubmitStart: () => void;
  onRefresh: () => Promise<void>;
}) {
  // O formulário remonta pela `key` com a versão; o Aplicar da IA salva só a descrição e guarda o
  // que estava sujo nos outros campos para voltar por cima dos dados novos (spec 008, R-9).
  const rebase = useFormRebase<Partial<EditPerfilForm>>(`perfil:${perfil.id}`);
  const {
    register: field,
    handleSubmit,
    getValues,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<EditPerfilForm>({
    resolver: zodResolver(editPerfilForm),
    defaultValues: { ...perfilValues(perfil), ...rebase.retomado },
  });

  const iaSaveBio: IaOnSave<string> = async (valor, ia) => {
    const salvos = perfilValues(perfil);
    const sujos = Object.fromEntries(
      Object.entries(getValues()).filter(([k, v]) => k !== "bio" && v !== salvos[k as keyof EditPerfilForm]),
    ) as Partial<EditPerfilForm>;
    await comRebase(rebase, Object.keys(sujos).length > 0 ? sujos : null, async () => {
      await api.perfis.update(perfil.id, { version: perfil.version, bio: valor, ia });
    });
    await onRefresh();
  };

  async function onSubmit(data: EditPerfilForm) {
    onSubmitStart();
    // Só manda o que mudou, com a versão lida (controle otimista, FR-015).
    const changes: UpdatePerfilRequest = { version: perfil.version };
    if (data.name !== perfil.name) changes.name = data.name;
    if (data.niche !== perfil.niche) changes.niche = data.niche;
    if (data.bio !== perfil.bio) changes.bio = data.bio;
    if (data.language !== perfil.language) changes.language = data.language;
    if (data.status !== perfil.status) changes.status = data.status;
    if (Object.keys(changes).length === 1) {
      await onSaved("Nada para salvar.");
      return;
    }
    try {
      await api.perfis.update(perfil.id, changes);
      await onSaved("Alterações salvas.");
    } catch (err) {
      onError(err);
    }
  }

  const languages = languageLabel[perfil.language] ? languageLabel : { ...languageLabel, [perfil.language]: perfil.language };

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle>
            <h2>Dados do perfil</h2>
          </CardTitle>
          <CardDescription>Nome, nicho, descrição, idioma e status.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <Field label="Nome" error={errors.name?.message}>
              {({ id, describedBy, invalid }) => (
                <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("name")} />
              )}
            </Field>
            <Field label="Identificador" hint="O identificador é fixo desde a criação.">
              {({ id, describedBy }) => (
                <Input
                  id={id}
                  value={perfil.slug}
                  readOnly
                  aria-readonly="true"
                  aria-describedby={describedBy}
                  className="bg-muted font-mono text-muted-foreground"
                />
              )}
            </Field>
            <Field label="Nicho" error={errors.niche?.message}>
              {({ id, describedBy, invalid }) => (
                <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("niche")} />
              )}
            </Field>
            <IaAssist
              tipo="perfil.bio"
              perfilId={perfil.id}
              alvo={{ entityType: "perfil", entityId: perfil.id }}
              value={watch("bio")}
              onSave={iaSaveBio}
              campo="Descrição"
              disabled={perfil.archived}
              onReload={() => void onRefresh()}
            >
              {(botao) => (
                <Field label="Descrição" action={botao} error={errors.bio?.message}>
                  {({ id, describedBy, invalid }) => (
                    <Textarea id={id} rows={5} aria-invalid={invalid} aria-describedby={describedBy} {...field("bio")} />
                  )}
                </Field>
              )}
            </IaAssist>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Idioma" error={errors.language?.message}>
                {({ id, describedBy, invalid }) => (
                  <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("language")}>
                    {Object.entries(languages).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Field label="Status" error={errors.status?.message}>
                {({ id, describedBy, invalid }) => (
                  <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("status")}>
                    {Object.entries(perfilStatusLabel).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            </div>
            <Button type="submit" disabled={isSubmitting} aria-busy={isSubmitting}>
              {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle>
            <h2>Imagens</h2>
          </CardTitle>
          <CardDescription>Logo e banner do perfil.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <ImageUpload kind="logo" perfil={perfil} onChanged={() => void onSaved("Logo atualizado.")} />
          <ImageUpload kind="banner" perfil={perfil} onChanged={() => void onSaved("Banner atualizado.")} />
        </CardContent>
      </Card>
    </div>
  );
}

function PerfilHistorico({ perfil, onReverted }: { perfil: Perfil; onReverted: () => Promise<void> }) {
  const versions = useQuery({ queryKey: perfilVersionsKey(perfil.id), queryFn: () => api.perfis.versions(perfil.id) });

  return (
    <Card className="shadow-card">
      <CardHeader>
        <HistoryHeading>Histórico do perfil</HistoryHeading>
        <CardDescription>Da versão mais recente para a mais antiga. Reverter cria uma versão nova; nada é apagado.</CardDescription>
      </CardHeader>
      <CardContent>
        {versions.isPending && (
          <p aria-live="polite" className="text-sm text-muted-foreground">
            Carregando…
          </p>
        )}
        {versions.isError && <ApiErrorAlert error={versions.error} />}
        {versions.data && (
          <VersionHistory
            versions={versions.data.items}
            labels={perfilFieldLabel}
            formatValue={formatPerfilValue}
            onRevert={async (toVersion) => {
              await api.perfis.revert(perfil.id, perfil.version, toVersion);
              await onReverted();
            }}
            onReload={onReverted}
          />
        )}
      </CardContent>
    </Card>
  );
}
