import { zodResolver } from "@hookform/resolvers/zod";
import type { Conta, CreateContaRequest, Perfil, UpdateContaRequest } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ExternalLink, FileClock, History, Loader2, MessageSquareQuote, Pencil, Plus, Save, X } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { PlatformIcon } from "../../components/PlatformIcon";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { ConexaoCard } from "../../components/publicacao/ConexaoCard";
import { api } from "../../lib/api";
import { useEhDono } from "../../lib/conteudos";
import { guiaContaPath } from "../../lib/guia";
import { studioContaPath } from "../../lib/studio";
import { INTERVALO_MAX } from "../../lib/postagem";
import { contaForm, isUrl, type ContaForm } from "../../lib/forms";
import {
  contaFieldLabel,
  contaPlatformText,
  contaStatusLabel,
  contaVersionsKey,
  formatContaValue,
  platformLabel,
} from "../../lib/perfis";

// Cor do status da conta na tabela.
const contaStatusBadge: Record<Conta["status"], string> = {
  planejada: "bg-info text-info-foreground",
  ativa: "bg-success text-success-foreground",
  pausada: "bg-warning text-warning-foreground",
  encerrada: "bg-secondary text-secondary-foreground",
};

type Panel = { kind: "edit" | "history"; conta: Conta };

interface ContasTabProps {
  perfil: Perfil;
  contas: Conta[];
  onChanged: () => Promise<void>;
  // Erro da API: o PerfilDetalhe mostra num Alert (com "Recarregar" no conflito de versão).
  onError: (err: unknown) => void;
  // Limpa o erro anterior antes de uma nova ação.
  onActionStart: () => void;
}

// Aba Contas do perfil (US2): lista, adicionar, editar, arquivar/restaurar e histórico por conta.
// O SociMan só registra as contas; nada é publicado nem alterado nas plataformas (FR-007).
// Sucesso vira toast; erro sobe para o Alert do PerfilDetalhe.
export function ContasTab({ perfil, contas, onChanged, onError, onActionStart }: ContasTabProps) {
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // O painel acompanha a conta recarregada (versão nova depois de salvar ou reverter).
  const panelConta = panel ? (contas.find((c) => c.id === panel.conta.id) ?? panel.conta) : null;

  async function changed(conta: Conta) {
    await Promise.all([onChanged(), queryClient.invalidateQueries({ queryKey: contaVersionsKey(conta.id) })]);
  }

  async function toggleArchive(conta: Conta) {
    onActionStart();
    setBusyId(conta.id);
    try {
      if (conta.archived) {
        await api.contas.restore(conta.id, conta.version);
        toast.success("Conta restaurada.");
      } else {
        await api.contas.archive(conta.id, conta.version);
        toast.success("Conta arquivada.");
      }
      await changed(conta);
    } catch (err) {
      onError(err);
    } finally {
      setBusyId(null);
    }
  }

  // Ações da linha: na coluna própria a partir de 640 px; abaixo disso, sob a conta.
  function rowActions(conta: Conta) {
    return (
      <>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            onActionStart();
            setPanel({ kind: "edit", conta });
          }}
        >
          <Pencil aria-hidden="true" />
          Editar
        </Button>
        <ConfirmButton
          variant="ghost"
          size="sm"
          label={conta.archived ? "Restaurar" : "Arquivar"}
          icon={conta.archived ? ArchiveRestore : Archive}
          busy={busyId === conta.id}
          disabled={busyId !== null}
          title={conta.archived ? `Restaurar @${conta.handle}?` : `Arquivar @${conta.handle}?`}
          description={
            conta.archived
              ? "A conta volta ao registro do perfil com o status que tinha."
              : "A conta sai do registro ativo do perfil. Nada muda na plataforma: o SociMan não encerra contas."
          }
          onConfirm={() => toggleArchive(conta)}
        />
        <Button type="button" variant="ghost" size="sm" onClick={() => setPanel({ kind: "history", conta })}>
          <History aria-hidden="true" />
          Histórico
        </Button>
        {/* spec 017: guia de comunicação da conta (complementa o do perfil) */}
        <Button asChild variant="ghost" size="sm">
          <Link to={guiaContaPath(conta.id)}>
            <MessageSquareQuote aria-hidden="true" />
            Guia de comunicação
          </Link>
        </Button>
        {/* spec 020: histórico importado do TikTok Studio (dono importa; membro só vê) */}
        {conta.platform === "tiktok" && (
          <Button asChild variant="ghost" size="sm">
            <Link to={studioContaPath(conta.id)}>
              <FileClock aria-hidden="true" />
              Histórico do Studio
            </Link>
          </Button>
        )}
      </>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle>
            <h2>Contas nas plataformas</h2>
          </CardTitle>
          <CardDescription>O SociMan só registra as contas; nada é publicado nem alterado nas plataformas.</CardDescription>
        </CardHeader>
        <CardContent>
          {contas.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma conta cadastrada.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase">Conta</TableHead>
                  <TableHead className="hidden text-xs uppercase md:table-cell">Link</TableHead>
                  <TableHead className="text-xs uppercase">Status</TableHead>
                  <TableHead className="hidden sm:table-cell">
                    <span className="sr-only">Ações</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contas.map((conta) => (
                  <TableRow key={conta.id} className={conta.archived ? "text-muted-foreground" : undefined}>
                    <TableCell>
                      <span className="flex items-center gap-3">
                        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                          <PlatformIcon platform={conta.platform} label={contaPlatformText(conta)} className="size-5" />
                        </span>
                        <span className="min-w-0">
                          <span className="block font-semibold">@{conta.handle}</span>
                          <span className="block text-xs text-muted-foreground">{contaPlatformText(conta)}</span>
                          <span className="block text-xs text-muted-foreground">Intervalo mínimo entre posts: {conta.intervaloMinMinutos} min</span>
                        </span>
                      </span>
                      <div className="mt-2 -ml-2 flex flex-wrap gap-1 sm:hidden">{rowActions(conta)}</div>
                    </TableCell>
                    <TableCell className="hidden max-w-xs md:table-cell">
                      <a
                        href={conta.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 break-all whitespace-normal hover:underline"
                      >
                        {conta.url}
                        <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
                      </a>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        <Badge className={contaStatusBadge[conta.status]}>{contaStatusLabel[conta.status]}</Badge>
                        {conta.archived && <Badge className="bg-dark text-dark-foreground">arquivada</Badge>}
                      </div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <div className="flex flex-wrap justify-end gap-1">{rowActions(conta)}</div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* spec 015: conexão das contas TikTok com o app da agência (botões só para o dono) */}
      {contas.some((c) => c.platform === "tiktok" && !c.archived) && (
        <Card className="shadow-card">
          <CardHeader>
            <CardTitle>
              <h2>Conexão com a TikTok</h2>
            </CardTitle>
            <CardDescription>Com a conta conectada, o SociMan cria o rascunho na TikTok no horário agendado; você finaliza e publica no app.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {contas
              .filter((c) => c.platform === "tiktok" && !c.archived)
              .map((c) => (
                <ConexaoCard key={c.id} conta={c} perfilId={perfil.id} />
              ))}
          </CardContent>
        </Card>
      )}

      {panel?.kind === "edit" && panelConta && (
        <EditContaCard
          key={`${panelConta.id}-${panelConta.version}`}
          conta={panelConta}
          onCancel={() => setPanel(null)}
          onSaved={async () => {
            setPanel(null);
            toast.success("Conta salva.");
            await changed(panelConta);
          }}
          onError={onError}
          onSubmitStart={onActionStart}
        />
      )}
      {panel?.kind === "history" && panelConta && (
        <ContaHistoryCard conta={panelConta} onClose={() => setPanel(null)} onReverted={() => changed(panelConta)} />
      )}

      <AddContaCard
        perfil={perfil}
        onCreated={async (conta) => {
          toast.success(`Conta @${conta.handle} adicionada.`);
          await onChanged();
        }}
        onError={onError}
        onSubmitStart={onActionStart}
      />
    </div>
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
              <Input id={id} value={platformLabel[platform]} readOnly aria-readonly="true" className="bg-muted text-muted-foreground" />
            ) : (
              <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("platform")}>
                {Object.entries(platformLabel).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
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
      <Field
        label="@ ou link"
        error={errors.handleOrUrl?.message}
        hint={
          platform === "outra"
            ? "Cole o link da conta; o @ é tirado dele."
            : "Digite o @ (o link é preenchido sozinho) ou cole o link da conta (o @ é tirado dele)."
        }
      >
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            autoComplete="off"
            spellCheck={false}
            placeholder={platform === "outra" ? "https://…" : "@meuperfil"}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field("handleOrUrl")}
          />
        )}
      </Field>
      <Field label="Status" error={errors.status?.message}>
        {({ id, describedBy, invalid }) => (
          <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("status")}>
            {Object.entries(contaStatusLabel).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
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
    <Card className="max-w-xl shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Nova conta</h2>
        </CardTitle>
        <CardDescription>Uma conta ativa por plataforma em cada perfil.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <ContaFields form={form} />
          <Button type="submit" disabled={isSubmitting} aria-busy={isSubmitting}>
            {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
            Adicionar conta
          </Button>
        </form>
      </CardContent>
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
  // spec 014 (Q3): intervalo mínimo entre posts da conta, 0..1.440 min; só o dono muda.
  const dono = useEhDono();
  const [intervalo, setIntervalo] = useState(String(conta.intervaloMinMinutos));
  const intervaloNum = Number(intervalo);
  const intervaloErro =
    intervalo.trim() === "" || !Number.isInteger(intervaloNum) || intervaloNum < 0 || intervaloNum > INTERVALO_MAX
      ? `De 0 a ${INTERVALO_MAX.toLocaleString("pt-BR")} minutos`
      : null;

  async function onSubmit(data: ContaForm) {
    if (dono && intervaloErro) return;
    onSubmitStart();
    // Só manda o que mudou; o @ é comparado já normalizado, como a API guarda.
    const changes: UpdateContaRequest = { version: conta.version };
    if (dono && intervaloNum !== conta.intervaloMinMinutos) changes.intervaloMinMinutos = intervaloNum;
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
    <Card className="max-w-xl shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>
            Editar @{conta.handle} ({contaPlatformText(conta)})
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <ContaFields form={form} platformLocked />
          <Field
            label="Intervalo mínimo entre posts (min)"
            error={dono ? (intervaloErro ?? undefined) : undefined}
            hint={
              dono
                ? "Agendar a menos disso de outro post desta conta mostra um aviso; a sequência pula o horário. 0 = só o mesmo minuto conflita."
                : "Só um dono muda este valor."
            }
          >
            {({ id, describedBy, invalid }) =>
              !dono ? (
                <p id={id} aria-describedby={describedBy} className="text-sm font-medium">
                  {conta.intervaloMinMinutos} min
                </p>
              ) : (
              <Input
                id={id}
                type="number"
                inputMode="numeric"
                min={0}
                max={INTERVALO_MAX}
                step={1}
                value={intervalo}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                className="w-32"
                onChange={(e) => setIntervalo(e.target.value)}
              />
              )
            }
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={isSubmitting} aria-busy={isSubmitting}>
              {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancelar
            </Button>
          </div>
        </form>
      </CardContent>
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
    <Card className="shadow-card">
      <CardHeader>
        <HistoryHeading>{`Histórico de @${conta.handle} (${contaPlatformText(conta)})`}</HistoryHeading>
        <CardAction className="flex gap-1">
          <Button asChild variant="link" size="sm">
            <Link to={`/app/contas/${conta.id}/historico`}>Abrir em página própria</Link>
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            <X aria-hidden="true" />
            Fechar
          </Button>
        </CardAction>
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
            labels={contaFieldLabel}
            formatValue={formatContaValue}
            onRevert={async (toVersion) => {
              await api.contas.revert(conta.id, conta.version, toVersion);
              await onReverted();
            }}
            onReload={onReverted}
          />
        )}
      </CardContent>
    </Card>
  );
}
