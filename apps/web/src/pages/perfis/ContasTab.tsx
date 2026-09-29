import { zodResolver } from "@hookform/resolvers/zod";
import type { Conta, CreateContaRequest, Perfil, UpdateContaRequest } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, Save } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { Card } from "../../components/layout";
import { PlatformIcon } from "../../components/PlatformIcon";
import { Alert, Button, Field, Input, Select, Textarea } from "../../components/ui";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { contaForm, isUrl, type ContaForm } from "../../lib/forms";
import {
  contaFieldLabel,
  contaPlatformText,
  contaStatusLabel,
  contaVersionsKey,
  errorText,
  formatContaValue,
  platformLabel,
} from "../../lib/perfis";
import type { Feedback } from "./PerfilDetalhe";

type Panel = { kind: "edit" | "history"; conta: Conta };

interface ContasTabProps {
  perfil: Perfil;
  contas: Conta[];
  onChanged: () => Promise<void>;
  onError: (err: unknown) => void;
  setFeedback: (feedback: Feedback | null) => void;
}

// Aba Contas do perfil (US2): lista, adicionar, editar, arquivar/restaurar e histórico por conta.
// O SociMan só registra as contas; nada é publicado nem alterado nas plataformas (FR-007).
export function ContasTab({ perfil, contas, onChanged, onError, setFeedback }: ContasTabProps) {
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // O painel acompanha a conta recarregada (versão nova depois de salvar ou reverter).
  const panelConta = panel ? (contas.find((c) => c.id === panel.conta.id) ?? panel.conta) : null;

  async function changed(conta: Conta) {
    await Promise.all([onChanged(), queryClient.invalidateQueries({ queryKey: contaVersionsKey(conta.id) })]);
  }

  async function toggleArchive(conta: Conta) {
    setFeedback(null);
    setBusyId(conta.id);
    try {
      if (conta.archived) {
        await api.contas.restore(conta.id, conta.version);
        setFeedback({ tone: "success", text: "Conta restaurada." });
      } else {
        await api.contas.archive(conta.id, conta.version);
        setFeedback({ tone: "success", text: "Conta arquivada." });
      }
      await changed(conta);
    } catch (err) {
      onError(err);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="mb-4 text-lg font-medium">Contas nas plataformas</h2>
        {contas.length === 0 ? (
          <p className="text-sm text-muted">Nenhuma conta cadastrada.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2 pr-4 font-medium">Plataforma</th>
                  <th className="py-2 pr-4 font-medium">@</th>
                  <th className="py-2 pr-4 font-medium">Link</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 font-medium">
                    <span className="sr-only">Ações</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {contas.map((conta) => (
                  <tr key={conta.id} className={`border-b border-border last:border-0 ${conta.archived ? "text-muted" : ""}`}>
                    <td className="py-2 pr-4">
                      <span className="flex items-center gap-2">
                        <PlatformIcon platform={conta.platform} label={contaPlatformText(conta)} />
                        {contaPlatformText(conta)}
                      </span>
                    </td>
                    <td className="py-2 pr-4">@{conta.handle}</td>
                    <td className="py-2 pr-4">
                      <a
                        href={conta.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 break-all hover:underline"
                      >
                        {conta.url}
                        <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
                      </a>
                    </td>
                    <td className="py-2 pr-4">
                      {contaStatusLabel[conta.status]}
                      {conta.archived && " · arquivada"}
                    </td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-1">
                        <RowAction
                          onClick={() => {
                            setFeedback(null);
                            setPanel({ kind: "edit", conta });
                          }}
                        >
                          Editar
                        </RowAction>
                        <RowAction disabled={busyId !== null} onClick={() => void toggleArchive(conta)}>
                          {conta.archived ? "Restaurar" : "Arquivar"}
                        </RowAction>
                        <RowAction onClick={() => setPanel({ kind: "history", conta })}>Histórico</RowAction>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {panel?.kind === "edit" && panelConta && (
        <EditContaCard
          key={`${panelConta.id}-${panelConta.version}`}
          conta={panelConta}
          onCancel={() => setPanel(null)}
          onSaved={async () => {
            setPanel(null);
            setFeedback({ tone: "success", text: "Conta salva." });
            await changed(panelConta);
          }}
          onError={onError}
          onSubmitStart={() => setFeedback(null)}
        />
      )}
      {panel?.kind === "history" && panelConta && (
        <ContaHistoryCard conta={panelConta} onClose={() => setPanel(null)} onReverted={() => changed(panelConta)} />
      )}

      <AddContaCard
        perfil={perfil}
        onCreated={async (conta) => {
          setFeedback({ tone: "success", text: `Conta @${conta.handle} adicionada.` });
          await onChanged();
        }}
        onError={onError}
        onSubmitStart={() => setFeedback(null)}
      />
    </div>
  );
}

function RowAction({ children, ...props }: { children: ReactNode; disabled?: boolean; onClick: () => void }) {
  return (
    <Button type="button" variant="ghost" className="!w-auto !px-2 !py-1 whitespace-nowrap" {...props}>
      {children}
    </Button>
  );
}

// Campos comuns de adicionar e editar. Na edição a plataforma é fixa (a API não a muda).
function ContaFields({
  form,
  platformLocked,
}: {
  form: ReturnType<typeof useForm<ContaForm>>;
  platformLocked?: boolean;
}) {
  const {
    register: field,
    watch,
    formState: { errors },
  } = form;
  const platform = watch("platform");
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Plataforma" error={errors.platform?.message}>
          {({ id, describedBy, invalid }) =>
            // Campo desabilitado sairia do formulário; fixo, a plataforma vem dos defaultValues.
            platformLocked ? (
              <Input id={id} value={platformLabel[platform]} readOnly aria-readonly="true" className="bg-bg text-muted" />
            ) : (
              <Select id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("platform")}>
                {Object.entries(platformLabel).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )
          }
        </Field>
        {platform === "outra" && (
          <Field label="Nome da plataforma" error={errors.platformName?.message}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("platformName")} />
            )}
          </Field>
        )}
      </div>
      <Field label="@ ou link" error={errors.handleOrUrl?.message}>
        {({ id, describedBy, invalid }) => (
          <>
            <Input
              id={id}
              autoComplete="off"
              spellCheck={false}
              placeholder={platform === "outra" ? "https://…" : "@meuperfil"}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("handleOrUrl")}
            />
            <p className="text-xs text-muted">
              {platform === "outra"
                ? "Cole o link da conta; o @ é tirado dele."
                : "Digite o @ (o link é preenchido sozinho) ou cole o link da conta (o @ é tirado dele)."}
            </p>
          </>
        )}
      </Field>
      <Field label="Status" error={errors.status?.message}>
        {({ id, describedBy, invalid }) => (
          <Select id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("status")}>
            {Object.entries(contaStatusLabel).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Observação" error={errors.notes?.message}>
        {({ id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-invalid={invalid} aria-describedby={describedBy} {...field("notes")} />
        )}
      </Field>
    </>
  );
}

function AddContaCard({
  perfil,
  onCreated,
  onError,
  onSubmitStart,
}: {
  perfil: Perfil;
  onCreated: (conta: Conta) => Promise<void>;
  onError: (err: unknown) => void;
  onSubmitStart: () => void;
}) {
  const form = useForm<ContaForm>({
    resolver: zodResolver(contaForm),
    defaultValues: { platform: "tiktok", platformName: "", handleOrUrl: "", status: "planejada", notes: "" },
  });
  const {
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = form;

  async function onSubmit(data: ContaForm) {
    onSubmitStart();
    const body: CreateContaRequest = {
      platform: data.platform,
      platformName: data.platform === "outra" ? data.platformName : "",
      status: data.status,
      notes: data.notes,
      ...(isUrl(data.handleOrUrl) ? { url: data.handleOrUrl } : { handle: data.handleOrUrl }),
    };
    try {
      const { conta } = await api.contas.create(perfil.id, body);
      reset();
      await onCreated(conta);
    } catch (err) {
      onError(err);
    }
  }

  return (
    <Card className="max-w-xl">
      <h2 className="mb-4 text-lg font-medium">Nova conta</h2>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <ContaFields form={form} />
        <Button type="submit" className="!w-auto" loading={isSubmitting}>
          {!isSubmitting && <Plus className="size-4" aria-hidden="true" />}
          Adicionar conta
        </Button>
      </form>
    </Card>
  );
}

function EditContaCard({
  conta,
  onCancel,
  onSaved,
  onError,
  onSubmitStart,
}: {
  conta: Conta;
  onCancel: () => void;
  onSaved: () => Promise<void>;
  onError: (err: unknown) => void;
  onSubmitStart: () => void;
}) {
  const form = useForm<ContaForm>({
    resolver: zodResolver(contaForm),
    defaultValues: {
      platform: conta.platform,
      platformName: conta.platformName,
      handleOrUrl: conta.platform === "outra" ? conta.url : `@${conta.handle}`,
      status: conta.status,
      notes: conta.notes,
    },
  });
  const {
    handleSubmit,
    formState: { isSubmitting },
  } = form;

  async function onSubmit(data: ContaForm) {
    onSubmitStart();
    // Só manda o que mudou; o @ é comparado já normalizado, como a API guarda.
    const changes: UpdateContaRequest = { version: conta.version };
    if (isUrl(data.handleOrUrl)) {
      if (data.handleOrUrl !== conta.url) changes.url = data.handleOrUrl;
    } else if (data.handleOrUrl.replace(/\s+/g, "").replace(/^@/, "").toLowerCase() !== conta.handle) {
      changes.handle = data.handleOrUrl;
    }
    if (conta.platform === "outra" && data.platformName !== conta.platformName) changes.platformName = data.platformName;
    if (data.status !== conta.status) changes.status = data.status;
    if (data.notes !== conta.notes) changes.notes = data.notes;
    if (Object.keys(changes).length === 1) {
      onCancel();
      return;
    }
    try {
      await api.contas.update(conta.id, changes);
      await onSaved();
    } catch (err) {
      onError(err);
    }
  }

  return (
    <Card className="max-w-xl">
      <h2 className="mb-4 text-lg font-medium">
        Editar @{conta.handle} ({contaPlatformText(conta)})
      </h2>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <ContaFields form={form} platformLocked />
        <div className="flex gap-2">
          <Button type="submit" className="!w-auto" loading={isSubmitting}>
            {!isSubmitting && <Save className="size-4" aria-hidden="true" />}
            Salvar
          </Button>
          <Button type="button" variant="ghost" className="!w-auto" onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ContaHistoryCard({
  conta,
  onClose,
  onReverted,
}: {
  conta: Conta;
  onClose: () => void;
  onReverted: () => Promise<void>;
}) {
  const versions = useQuery({ queryKey: contaVersionsKey(conta.id), queryFn: () => api.contas.versions(conta.id) });
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <HistoryHeading>{`Histórico de @${conta.handle} (${contaPlatformText(conta)})`}</HistoryHeading>
        <div className="flex gap-2 text-sm">
          <Link to={`/app/contas/${conta.id}/historico`} className="px-2 py-1 text-muted hover:text-text hover:underline">
            Abrir em página própria
          </Link>
          <Button type="button" variant="ghost" className="!w-auto !px-2 !py-1" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </div>
      {versions.isPending && <p aria-live="polite">Carregando…</p>}
      {versions.isError && <Alert tone="error">{errorText(versions.error)}</Alert>}
      {versions.data && (
        <VersionHistory
          versions={versions.data.items}
          labels={contaFieldLabel}
          formatValue={formatContaValue}
          onRevert={async (toVersion) => {
            await api.contas.revert(conta.id, conta.version, toVersion);
            await onReverted();
          }}
        />
      )}
    </Card>
  );
}
