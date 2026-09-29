import { zodResolver } from "@hookform/resolvers/zod";
import type { Perfil, UpdatePerfilRequest } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, RefreshCw, Save } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AppLayout } from "../../components/AppLayout";
import { ImageUpload } from "../../components/ImageUpload";
import { Card } from "../../components/layout";
import { ProfileAvatar } from "../../components/ProfileAvatar";
import { Alert, Button, Field, Input, Select, Textarea } from "../../components/ui";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { editPerfilForm, type EditPerfilForm } from "../../lib/forms";
import {
  errorText,
  formatPerfilValue,
  isVersionConflict,
  languageLabel,
  perfilFieldLabel,
  perfilKey,
  perfilStatusLabel,
  perfilVersionsKey,
} from "../../lib/perfis";
import { ContasTab } from "./ContasTab";

export type Feedback = { tone: "success" | "error" | "info"; text: string; conflict?: boolean };

const tabs = [
  { id: "dados", label: "Dados" },
  { id: "contas", label: "Contas" },
  { id: "historico", label: "Histórico" },
] as const;
type TabId = (typeof tabs)[number]["id"];

// /app/perfis/:id: abas Dados, Contas e Histórico, e as ações Arquivar/Restaurar. A aba fica na
// URL (?aba=contas) para o voltar do navegador e o link direto funcionarem.
export default function PerfilDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab: TabId = tabs.some((t) => t.id === params.get("aba")) ? (params.get("aba") as TabId) : "dados";
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [archiving, setArchiving] = useState(false);

  const detail = useQuery({ queryKey: perfilKey(id), queryFn: () => api.perfis.get(id) });

  // Qualquer mutação do perfil ou das contas muda a lista, o detalhe e o histórico.
  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: perfilKey(id) }),
      queryClient.invalidateQueries({ queryKey: perfilVersionsKey(id) }),
      queryClient.invalidateQueries({ queryKey: ["perfis"] }),
    ]);
  }

  function report(err: unknown) {
    setFeedback({ tone: "error", text: errorText(err), conflict: isVersionConflict(err) });
  }

  async function reload() {
    setFeedback(null);
    await refresh();
  }

  function selectTab(next: TabId) {
    setFeedback(null);
    setParams(next === "dados" ? {} : { aba: next }, { replace: true });
  }

  if (detail.isPending) {
    return (
      <AppLayout>
        <p aria-live="polite">Carregando…</p>
      </AppLayout>
    );
  }
  if (detail.isError) {
    return (
      <AppLayout>
        <Alert tone="error">{errorText(detail.error)}</Alert>
        <BackLink />
      </AppLayout>
    );
  }

  const { perfil, contas } = detail.data;
  const activeContas = contas.filter((c) => !c.archived && c.status === "ativa").length;

  async function toggleArchive() {
    setFeedback(null);
    setArchiving(true);
    try {
      if (perfil.archived) {
        await api.perfis.restore(perfil.id, perfil.version);
        setFeedback({ tone: "success", text: "Perfil restaurado." });
      } else {
        await api.perfis.archive(perfil.id, perfil.version);
        setFeedback({
          tone: activeContas > 0 ? "info" : "success",
          text:
            activeContas > 0
              ? "Perfil arquivado. As contas ativas continuam ativas nas plataformas: o SociMan não publica nem encerra nada fora dele."
              : "Perfil arquivado.",
        });
      }
      await refresh();
    } catch (err) {
      report(err);
    } finally {
      setArchiving(false);
    }
  }

  return (
    <AppLayout>
      <BackLink />
      <PerfilHeader
        perfil={perfil}
        actions={
          <Button type="button" variant="ghost" className="!w-auto border border-border" loading={archiving} onClick={() => void toggleArchive()}>
            {!archiving && (perfil.archived ? <ArchiveRestore className="size-4" aria-hidden="true" /> : <Archive className="size-4" aria-hidden="true" />)}
            {perfil.archived ? "Restaurar" : "Arquivar"}
          </Button>
        }
      />

      {feedback && (
        <div className="mb-4">
          <Alert tone={feedback.tone}>
            {feedback.text}
            {feedback.conflict && (
              <Button type="button" variant="ghost" className="!w-auto !px-2 !py-1 ml-2 underline" onClick={() => void reload()}>
                <RefreshCw className="size-4" aria-hidden="true" />
                Recarregar
              </Button>
            )}
          </Alert>
        </div>
      )}

      <div role="tablist" aria-label="Seções do perfil" className="mb-4 flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`aba-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`painel-${t.id}`}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === t.id ? "border-primary text-primary" : "border-transparent text-muted hover:text-text"}`}
            onClick={() => selectTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`painel-${tab}`} aria-labelledby={`aba-${tab}`}>
        {tab === "dados" && (
          <DadosTab
            key={`${perfil.id}-${perfil.version}`}
            perfil={perfil}
            onSaved={async (text) => {
              setFeedback({ tone: "success", text });
              await refresh();
            }}
            onError={report}
            onSubmitStart={() => setFeedback(null)}
          />
        )}
        {tab === "contas" && <ContasTab perfil={perfil} contas={contas} onChanged={refresh} onError={report} setFeedback={setFeedback} />}
        {tab === "historico" && <PerfilHistorico perfil={perfil} onReverted={refresh} />}
      </div>
    </AppLayout>
  );
}

function BackLink() {
  return (
    <Link to="/app/perfis" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
      <ArrowLeft className="size-4" aria-hidden="true" />
      Perfis
    </Link>
  );
}

function PerfilHeader({ perfil, actions }: { perfil: Perfil; actions: ReactNode }) {
  return (
    <div className="mb-6 space-y-4">
      {perfil.banner && (
        <img
          src={perfil.banner.urls.medium}
          alt={`Banner de ${perfil.name}`}
          className="aspect-[4/1] w-full rounded-panel border border-border object-cover"
        />
      )}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <ProfileAvatar name={perfil.name} logo={perfil.logo} size="lg" />
          <div>
            <h1 className="text-2xl font-semibold">{perfil.name}</h1>
            <p className="mt-1 text-sm text-muted">
              {perfil.slug} · {perfilStatusLabel[perfil.status]}
              {perfil.archived && " · Arquivado"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
    </div>
  );
}

function DadosTab({
  perfil,
  onSaved,
  onError,
  onSubmitStart,
}: {
  perfil: Perfil;
  onSaved: (text: string) => Promise<void>;
  onError: (err: unknown) => void;
  onSubmitStart: () => void;
}) {
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<EditPerfilForm>({
    resolver: zodResolver(editPerfilForm),
    defaultValues: {
      name: perfil.name,
      niche: perfil.niche,
      bio: perfil.bio,
      language: perfil.language,
      status: perfil.status,
    },
  });

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
      <Card>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <Field label="Nome" error={errors.name?.message}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("name")} />
            )}
          </Field>
          <Field label="Identificador">
            {({ id }) => (
              <>
                <Input id={id} value={perfil.slug} readOnly aria-readonly="true" className="bg-bg text-muted" />
                <p className="text-xs text-muted">O identificador é fixo desde a criação.</p>
              </>
            )}
          </Field>
          <Field label="Nicho" error={errors.niche?.message}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("niche")} />
            )}
          </Field>
          <Field label="Descrição" error={errors.bio?.message}>
            {({ id, describedBy, invalid }) => (
              <Textarea id={id} rows={5} aria-invalid={invalid} aria-describedby={describedBy} {...field("bio")} />
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Idioma" error={errors.language?.message}>
              {({ id, describedBy, invalid }) => (
                <Select id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("language")}>
                  {Object.entries(languages).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Status" error={errors.status?.message}>
              {({ id, describedBy, invalid }) => (
                <Select id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("status")}>
                  {Object.entries(perfilStatusLabel).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Button type="submit" className="!w-auto" loading={isSubmitting}>
            {!isSubmitting && <Save className="size-4" aria-hidden="true" />}
            Salvar
          </Button>
        </form>
      </Card>
      <Card className="space-y-6">
        <ImageUpload kind="logo" perfil={perfil} onChanged={() => void onSaved("Logo atualizado.")} />
        <ImageUpload kind="banner" perfil={perfil} onChanged={() => void onSaved("Banner atualizado.")} />
      </Card>
    </div>
  );
}

function PerfilHistorico({ perfil, onReverted }: { perfil: Perfil; onReverted: () => Promise<void> }) {
  const versions = useQuery({ queryKey: perfilVersionsKey(perfil.id), queryFn: () => api.perfis.versions(perfil.id) });

  return (
    <Card>
      <HistoryHeading>Histórico do perfil</HistoryHeading>
      {versions.isPending && <p aria-live="polite">Carregando…</p>}
      {versions.isError && <Alert tone="error">{errorText(versions.error)}</Alert>}
      {versions.data && (
        <VersionHistory
          versions={versions.data.items}
          labels={perfilFieldLabel}
          formatValue={formatPerfilValue}
          onRevert={async (toVersion) => {
            await api.perfis.revert(perfil.id, perfil.version, toVersion);
            await onReverted();
          }}
        />
      )}
    </Card>
  );
}
