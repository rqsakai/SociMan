import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, type User } from "@sociman/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, MailCheck, MoreHorizontal, Pencil, Power, Save, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { DataTable, dataTableColumns, FilterBar } from "@/components/data-table";
import { HeaderCard, Page } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageHeading } from "../components/PageHeading";
import { api } from "../lib/api";
import { useFiltroUrl } from "../lib/filtros";
import { formatDate } from "../lib/tz";
import {
  createUserForm,
  editUserForm,
  setPasswordForm,
  type CreateUserForm,
  type EditUserForm,
  type SetPasswordForm,
} from "../lib/forms";
import { initials } from "../lib/perfis";
import { useAppConfig } from "../lib/useAppConfig";
import { roleLabel } from "../lib/users";

// Sucesso vira toast; o aviso de e-mail não enviado também (tom "info"); erro fica num <Alert>.
type Feedback = { tone: "success" | "info"; text: string };
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

function notify({ tone, text }: Feedback) {
  if (tone === "success") toast.success(text);
  else toast.info(text, { duration: 10_000 });
}

const normalizar = (t: string) => t.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

interface RowActions {
  busy: boolean;
  onEdit: (user: User) => void;
  onPassword: (user: User) => void;
  onToggleActive: (user: User) => void;
  onResend: (user: User) => void;
}

function userColumns(actions: RowActions) {
  const col = dataTableColumns<User>();
  return col.columns([
    // nome + e-mail no mesmo accessor: a busca acha os dois; a ordem segue o nome
    col.accessor((u) => `${u.name} ${u.email}`, {
      id: "name",
      header: "Usuário",
      cell: (c) => {
        const user = c.row.original;
        return (
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="tone-dark grid size-9 shrink-0 place-items-center rounded-full text-xs font-semibold"
            >
              {initials(user.name)}
            </span>
            <div className="min-w-0">
              <p className="truncate font-semibold">{user.name}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </div>
          </div>
        );
      },
    }),
    col.accessor((u) => roleLabel[u.role], { id: "role", header: "Papel" }),
    col.accessor((u) => (u.isActive ? "Ativo" : "Inativo"), {
      id: "situacao",
      header: "Situação",
      cell: (c) =>
        c.row.original.isActive ? (
          <Badge className="bg-success text-success-foreground uppercase">Ativo</Badge>
        ) : (
          <Badge className="bg-dark text-dark-foreground uppercase">Inativo</Badge>
        ),
    }),
    col.accessor((u) => (u.emailVerified ? "Sim" : "Não"), {
      id: "verificado",
      header: "Verificado",
      meta: { className: "hidden sm:table-cell" },
    }),
    col.accessor("createdAt", {
      header: "Criado em",
      enableGlobalFilter: false,
      cell: (c) => formatDate(c.getValue()),
      meta: { className: "hidden md:table-cell" },
    }),
    col.display({
      id: "acoes",
      header: () => <span className="sr-only">Ações</span>,
      meta: { className: "text-right" },
      cell: (c) => {
        const user = c.row.original;
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={`Ações de ${user.name}`} disabled={actions.busy}>
                <MoreHorizontal aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => actions.onEdit(user)}>
                <Pencil aria-hidden="true" />
                Editar
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => actions.onPassword(user)}>
                <KeyRound aria-hidden="true" />
                Definir senha provisória
              </DropdownMenuItem>
              {!user.emailVerified && (
                <DropdownMenuItem onSelect={() => actions.onResend(user)}>
                  <MailCheck aria-hidden="true" />
                  Reenviar verificação
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant={user.isActive ? "destructive" : "default"}
                onSelect={() => actions.onToggleActive(user)}
              >
                <Power aria-hidden="true" />
                {user.isActive ? "Desativar" : "Ativar"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    }),
  ]);
}

// /app/usuarios (só dono): lista, cria, edita, ativa/desativa, define senha
// provisória e reenvia a verificação.
export default function Users() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);

  const { data, isPending, isError, error: loadError } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.users.list(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["users"] });

  const toggleActive = useMutation({
    mutationFn: (user: User) => api.users.update(user.id, { isActive: !user.isActive }),
    onMutate: () => setError(null),
    onSuccess: ({ user }) => {
      notify({
        tone: "success",
        text: user.isActive
          ? `Acesso de ${user.name} reativado.`
          : `Acesso de ${user.name} desativado. As sessões foram encerradas.`,
      });
      void refresh();
    },
    onError: (err) => setError(errorText(err)),
  });

  const resendVerification = useMutation({
    mutationFn: (user: User) => api.users.resendVerification(user.id),
    onMutate: () => setError(null),
    onSuccess: ({ emailSent }, user) =>
      notify(
        emailSent
          ? { tone: "success", text: `Enviamos um novo link de verificação para ${user.email}.` }
          : { tone: "info", text: EMAIL_NOT_SENT },
      ),
    onError: (err) => setError(errorText(err)),
  });

  // busca local (a lista vem inteira) com o texto na URL (spec 024): nome ou e-mail, sem acento
  const [filtro, setFiltro] = useFiltroUrl();
  const q = filtro.get("q") ?? "";
  const linhas = useMemo(() => {
    const termo = normalizar(q.trim());
    return termo ? data?.items.filter((u) => normalizar(`${u.name} ${u.email}`).includes(termo)) : data?.items;
  }, [data, q]);

  const busy = toggleActive.isPending || resendVerification.isPending;
  const columns = useMemo(
    () =>
      userColumns({
        busy,
        onEdit: (user) => setPanel({ kind: "edit", user }),
        onPassword: (user) => setPanel({ kind: "password", user }),
        onToggleActive: (user) => toggleActive.mutate(user),
        onResend: (user) => resendVerification.mutate(user),
      }),
    // os `mutate` do TanStack Query são estáveis
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [busy],
  );

  function done(message: Feedback) {
    setPanel(null);
    setError(null);
    notify(message);
    void refresh();
  }

  return (
    <Page>
      <PageHeading title="Usuários" description="Quem tem acesso ao SociMan e com qual papel." />
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <HeaderCard title="Usuários cadastrados" description="Donos gerenciam usuários; membros usam o app.">
          {isError && (
            <Alert variant="destructive" className="mb-3">
              <AlertDescription>{errorText(loadError)}</AlertDescription>
            </Alert>
          )}
          <DataTable
            label="Usuários"
            columns={columns}
            data={linhas}
            loading={isPending}
            getRowId={(u) => u.id}
            emptyMessage={q ? "Nenhum usuário com esta busca." : undefined}
            toolbar={
              <FilterBar
                busca={{ valor: q, onChange: (v) => setFiltro({ q: v || null }, { replace: true }), placeholder: "Nome ou e-mail" }}
                ativos={q ? [{ chave: "q", rotulo: "Busca", valor: q, limpar: () => setFiltro({ q: null }) }] : []}
              />
            }
            // o mais novo primeiro: quem acabou de ser criado aparece na primeira página
            initialSorting={[{ id: "createdAt", desc: true }]}
          />
        </HeaderCard>

        <CreateUserCard
          onCreated={({ user, emailSent }) =>
            done(
              emailSent !== false
                ? { tone: "success", text: `Usuário criado. Enviamos o link de verificação para ${user.email}.` }
                : { tone: "info", text: `Usuário criado. ${EMAIL_NOT_SENT}` },
            )
          }
          onError={(err) => setError(errorText(err))}
          onSubmitStart={() => setError(null)}
        />
      </div>

      <Dialog open={panel !== null} onOpenChange={(open) => !open && setPanel(null)}>
        <DialogContent className="sm:max-w-md">
          {panel?.kind === "edit" && (
            <EditUserDialog key={panel.user.id} user={panel.user} onCancel={() => setPanel(null)} onDone={done} />
          )}
          {panel?.kind === "password" && (
            <SetPasswordDialog key={panel.user.id} user={panel.user} onCancel={() => setPanel(null)} onDone={done} />
          )}
        </DialogContent>
      </Dialog>
    </Page>
  );
}

function SubmitButton({ submitting, icon: Icon, children }: { submitting: boolean; icon: typeof Save; children: string }) {
  return (
    <Button type="submit" disabled={submitting} aria-busy={submitting}>
      {submitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Icon aria-hidden="true" />}
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
    // xl:mt-6: ao lado do HeaderCard, o topo do cartão alinha com o do cartão vizinho (abaixo da faixa)
    <Card className="shadow-card xl:mt-6">
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-bold">Novo usuário</h2>
        </CardTitle>
        <CardDescription>Entra com a senha provisória e troca no primeiro acesso.</CardDescription>
      </CardHeader>
      <CardContent>
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
                autoComplete="off"
                aria-invalid={invalid}
                aria-describedby={describedBy}
                {...field("email")}
              />
            )}
          </Field>
          <Field label="Papel" error={errors.role?.message}>
            {({ id, describedBy, invalid }) => (
              <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("role")}>
                <option value="membro">{roleLabel.membro}</option>
                <option value="dono">{roleLabel.dono}</option>
              </NativeSelect>
            )}
          </Field>
          <Field label="Senha provisória" error={errors.provisionalPassword?.message}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                type="password"
                autoComplete="new-password"
                aria-invalid={invalid}
                aria-describedby={describedBy}
                {...field("provisionalPassword")}
              />
            )}
          </Field>
          <SubmitButton submitting={isSubmitting} icon={UserPlus}>
            Criar usuário
          </SubmitButton>
        </form>
      </CardContent>
    </Card>
  );
}

interface PanelProps {
  user: User;
  onCancel: () => void;
  onDone: (feedback: Feedback) => void;
}

function EditUserDialog({ user, onCancel, onDone }: PanelProps) {
  const [error, setError] = useState<string | null>(null);
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
    setError(null);
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
      setError(errorText(err));
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Editar {user.name}</DialogTitle>
        <DialogDescription>Trocar o e-mail pede nova verificação e encerra as sessões.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
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
              autoComplete="off"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("email")}
            />
          )}
        </Field>
        <Field label="Papel" error={errors.role?.message}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("role")}>
              <option value="membro">{roleLabel.membro}</option>
              <option value="dono">{roleLabel.dono}</option>
            </NativeSelect>
          )}
        </Field>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancelar
          </Button>
          <SubmitButton submitting={isSubmitting} icon={Save}>
            Salvar
          </SubmitButton>
        </DialogFooter>
      </form>
    </>
  );
}

function SetPasswordDialog({ user, onCancel, onDone }: PanelProps) {
  const [error, setError] = useState<string | null>(null);
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
    setError(null);
    try {
      await api.users.setPassword(user.id, data);
      onDone({
        tone: "success",
        text: `Senha provisória definida para ${user.name}. As sessões foram encerradas e a troca será pedida no próximo login.`,
      });
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Senha provisória de {user.name}</DialogTitle>
        <DialogDescription>As sessões são encerradas e a troca é pedida no próximo login.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Field label="Nova senha provisória" error={errors.provisionalPassword?.message}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              {...field("provisionalPassword")}
            />
          )}
        </Field>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancelar
          </Button>
          <SubmitButton submitting={isSubmitting} icon={KeyRound}>
            Definir senha
          </SubmitButton>
        </DialogFooter>
      </form>
    </>
  );
}
