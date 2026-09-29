import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, type User } from "@sociman/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock, Mail, Save, UserPlus } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { AppLayout } from "../components/AppLayout";
import { Card, PageHeader } from "../components/layout";
import { Alert, Button, Field, Input, Select } from "../components/ui";
import { api } from "../lib/api";
import {
  createUserForm,
  editUserForm,
  setPasswordForm,
  type CreateUserForm,
  type EditUserForm,
  type SetPasswordForm,
} from "../lib/forms";
import { useAppConfig } from "../lib/useAppConfig";
import { roleLabel } from "../lib/users";

type Feedback = { tone: "success" | "error" | "info"; text: string };
type Panel = { kind: "edit" | "password"; user: User };

const EMAIL_NOT_SENT =
  "O e-mail de verificação não foi enviado. Use “Reenviar verificação” quando o envio voltar.";

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "last_owner") {
      return "Não é possível rebaixar nem desativar o último dono ativo.";
    }
    return err.message;
  }
  return "Não foi possível concluir a operação. Tente de novo.";
}

// /app/usuarios (só dono): lista, cria, edita, ativa/desativa, define senha
// provisória e reenvia a verificação.
export default function Users() {
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.users.list(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["users"] });

  const toggleActive = useMutation({
    mutationFn: (user: User) => api.users.update(user.id, { isActive: !user.isActive }),
    onMutate: () => setFeedback(null),
    onSuccess: ({ user }) => {
      setFeedback({
        tone: "success",
        text: user.isActive
          ? `Acesso de ${user.name} reativado.`
          : `Acesso de ${user.name} desativado. As sessões foram encerradas.`,
      });
      void refresh();
    },
    onError: (err) => setFeedback({ tone: "error", text: errorText(err) }),
  });

  const resendVerification = useMutation({
    mutationFn: (user: User) => api.users.resendVerification(user.id),
    onMutate: () => setFeedback(null),
    onSuccess: ({ emailSent }, user) =>
      setFeedback(
        emailSent
          ? { tone: "success", text: `Enviamos um novo link de verificação para ${user.email}.` }
          : { tone: "info", text: EMAIL_NOT_SENT },
      ),
    onError: (err) => setFeedback({ tone: "error", text: errorText(err) }),
  });

  const busy = toggleActive.isPending || resendVerification.isPending;

  function done(message: Feedback) {
    setPanel(null);
    setFeedback(message);
    void refresh();
  }

  return (
    <AppLayout>
      <PageHeader title="Usuários" description="Quem tem acesso ao SociMan e com qual papel." />
      <div className="space-y-6">
        {feedback && <Alert tone={feedback.tone}>{feedback.text}</Alert>}

        {panel?.kind === "edit" && (
          <EditUserCard
            key={panel.user.id}
            user={panel.user}
            onCancel={() => setPanel(null)}
            onDone={done}
            onError={(err) => setFeedback({ tone: "error", text: errorText(err) })}
          />
        )}
        {panel?.kind === "password" && (
          <SetPasswordCard
            key={panel.user.id}
            user={panel.user}
            onCancel={() => setPanel(null)}
            onDone={done}
            onError={(err) => setFeedback({ tone: "error", text: errorText(err) })}
          />
        )}

        <Card>
          <h2 className="mb-4 text-lg font-medium">Usuários cadastrados</h2>
          {isPending && <p aria-live="polite">Carregando…</p>}
          {isError && <p className="text-sm text-danger">Não foi possível carregar os usuários.</p>}
          {data && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-muted">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Nome</th>
                    <th className="py-2 pr-4 font-medium">E-mail</th>
                    <th className="py-2 pr-4 font-medium">Papel</th>
                    <th className="py-2 pr-4 font-medium">Situação</th>
                    <th className="py-2 pr-4 font-medium">Verificado</th>
                    <th className="py-2 font-medium">
                      <span className="sr-only">Ações</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((user) => (
                    <tr key={user.id} className="border-b border-border last:border-0">
                      <td className="py-2 pr-4">{user.name}</td>
                      <td className="py-2 pr-4">{user.email}</td>
                      <td className="py-2 pr-4">{roleLabel[user.role]}</td>
                      <td className="py-2 pr-4">{user.isActive ? "Ativo" : "Inativo"}</td>
                      <td className="py-2 pr-4">{user.emailVerified ? "Sim" : "Não"}</td>
                      <td className="py-2">
                        <div className="flex flex-wrap gap-1">
                          <RowAction onClick={() => setPanel({ kind: "edit", user })}>Editar</RowAction>
                          <RowAction disabled={busy} onClick={() => toggleActive.mutate(user)}>
                            {user.isActive ? "Desativar" : "Ativar"}
                          </RowAction>
                          <RowAction onClick={() => setPanel({ kind: "password", user })}>
                            Definir senha provisória
                          </RowAction>
                          {!user.emailVerified && (
                            <RowAction disabled={busy} onClick={() => resendVerification.mutate(user)}>
                              Reenviar verificação
                            </RowAction>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <CreateUserCard
          onCreated={({ user, emailSent }) =>
            done(
              emailSent !== false
                ? { tone: "success", text: `Usuário criado. Enviamos o link de verificação para ${user.email}.` }
                : { tone: "info", text: `Usuário criado. ${EMAIL_NOT_SENT}` },
            )
          }
          onError={(err) => setFeedback({ tone: "error", text: errorText(err) })}
          onSubmitStart={() => setFeedback(null)}
        />
      </div>
    </AppLayout>
  );
}

function RowAction({ children, ...props }: { children: ReactNode; disabled?: boolean; onClick: () => void }) {
  return (
    <Button type="button" variant="ghost" className="!w-auto !px-2 !py-1 whitespace-nowrap" {...props}>
      {children}
    </Button>
  );
}

function CreateUserCard({
  onCreated,
  onError,
  onSubmitStart,
}: {
  onCreated: (result: { user: User; emailSent: boolean | null }) => void;
  onError: (err: unknown) => void;
  onSubmitStart: () => void;
}) {
  const { passwordMinLength, passwordMaxLength } = useAppConfig();
  const resolver = useMemo(
    () => zodResolver(createUserForm({ passwordMinLength, passwordMaxLength })),
    [passwordMinLength, passwordMaxLength],
  );
  const {
    register: field,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateUserForm>({ resolver, defaultValues: { role: "membro" } });

  async function onSubmit(data: CreateUserForm) {
    onSubmitStart();
    try {
      const result = await api.users.create(data);
      reset();
      onCreated(result);
    } catch (err) {
      onError(err);
    }
  }

  return (
    <Card className="max-w-md">
      <h2 className="mb-4 text-lg font-medium">Novo usuário</h2>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Field label="Nome" error={errors.name?.message}>
          {({ id, describedBy, invalid }) => (
            <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("name")} />
          )}
        </Field>
        <Field label="E-mail" error={errors.email?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="email"
              icon={Mail}
              autoComplete="off"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("email")}
            />
          )}
        </Field>
        <Field label="Papel" error={errors.role?.message}>
          {({ id, describedBy, invalid }) => (
            <Select id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("role")}>
              <option value="membro">{roleLabel.membro}</option>
              <option value="dono">{roleLabel.dono}</option>
            </Select>
          )}
        </Field>
        <Field label="Senha provisória" error={errors.provisionalPassword?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="password"
              icon={Lock}
              autoComplete="new-password"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("provisionalPassword")}
            />
          )}
        </Field>
        <Button type="submit" loading={isSubmitting}>
          {!isSubmitting && <UserPlus className="size-4" aria-hidden="true" />}
          Criar usuário
        </Button>
      </form>
    </Card>
  );
}

interface PanelProps {
  user: User;
  onCancel: () => void;
  onDone: (feedback: Feedback) => void;
  onError: (err: unknown) => void;
}

function EditUserCard({ user, onCancel, onDone, onError }: PanelProps) {
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<EditUserForm>({
    resolver: zodResolver(editUserForm),
    defaultValues: { name: user.name, email: user.email, role: user.role },
  });

  async function onSubmit(data: EditUserForm) {
    // Só manda o que mudou: trocar o e-mail tem efeitos colaterais (nova
    // verificação e sessões encerradas).
    const changes: { name?: string; email?: string; role?: User["role"] } = {};
    if (data.name !== user.name) changes.name = data.name;
    if (data.email !== user.email) changes.email = data.email;
    if (data.role !== user.role) changes.role = data.role;
    if (Object.keys(changes).length === 0) {
      onCancel();
      return;
    }
    try {
      const result = await api.users.update(user.id, changes);
      if (changes.email && result.emailSent === false) {
        onDone({ tone: "info", text: `Alterações salvas. ${EMAIL_NOT_SENT}` });
      } else if (changes.email) {
        onDone({
          tone: "success",
          text: `Alterações salvas. Enviamos o link de verificação para ${result.user.email}.`,
        });
      } else {
        onDone({ tone: "success", text: "Alterações salvas." });
      }
    } catch (err) {
      onError(err);
    }
  }

  return (
    <Card className="max-w-md">
      <h2 className="mb-4 text-lg font-medium">Editar {user.name}</h2>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Field label="Nome" error={errors.name?.message}>
          {({ id, describedBy, invalid }) => (
            <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("name")} />
          )}
        </Field>
        <Field label="E-mail" error={errors.email?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="email"
              icon={Mail}
              autoComplete="off"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("email")}
            />
          )}
        </Field>
        <Field label="Papel" error={errors.role?.message}>
          {({ id, describedBy, invalid }) => (
            <Select id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("role")}>
              <option value="membro">{roleLabel.membro}</option>
              <option value="dono">{roleLabel.dono}</option>
            </Select>
          )}
        </Field>
        <div className="flex gap-2">
          <Button type="submit" loading={isSubmitting}>
            {!isSubmitting && <Save className="size-4" aria-hidden="true" />}
            Salvar
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </form>
    </Card>
  );
}

function SetPasswordCard({ user, onCancel, onDone, onError }: PanelProps) {
  const { passwordMinLength, passwordMaxLength } = useAppConfig();
  const resolver = useMemo(
    () => zodResolver(setPasswordForm({ passwordMinLength, passwordMaxLength })),
    [passwordMinLength, passwordMaxLength],
  );
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SetPasswordForm>({ resolver });

  async function onSubmit(data: SetPasswordForm) {
    try {
      await api.users.setPassword(user.id, data);
      onDone({
        tone: "success",
        text: `Senha provisória definida para ${user.name}. As sessões foram encerradas e a troca será pedida no próximo login.`,
      });
    } catch (err) {
      onError(err);
    }
  }

  return (
    <Card className="max-w-md">
      <h2 className="mb-4 text-lg font-medium">Senha provisória de {user.name}</h2>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Field label="Nova senha provisória" error={errors.provisionalPassword?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="password"
              icon={Lock}
              autoComplete="new-password"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("provisionalPassword")}
            />
          )}
        </Field>
        <div className="flex gap-2">
          <Button type="submit" loading={isSubmitting}>
            {!isSubmitting && <KeyRound className="size-4" aria-hidden="true" />}
            Definir senha
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </form>
    </Card>
  );
}
