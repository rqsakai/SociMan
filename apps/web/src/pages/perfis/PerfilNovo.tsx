import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { AppLayout } from "../../components/AppLayout";
import { Card, PageHeader } from "../../components/layout";
import { Alert, Button, Field, Input, Select, Textarea } from "../../components/ui";
import { api } from "../../lib/api";
import { createPerfilForm, type CreatePerfilForm } from "../../lib/forms";
import { errorText, languageLabel, perfilStatusLabel } from "../../lib/perfis";

const SLUG_DEBOUNCE_MS = 300;

// /app/perfis/novo: o identificador (slug) é sugerido pela API enquanto se digita o nome e só
// pode ser ajustado aqui, antes de criar (FR-002a).
export default function PerfilNovo() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const slugEdited = useRef(false);
  const {
    register: field,
    handleSubmit,
    watch,
    getValues,
    setValue,
    setError: setFieldError,
    formState: { errors, isSubmitting },
  } = useForm<CreatePerfilForm>({
    resolver: zodResolver(createPerfilForm),
    defaultValues: { name: "", slug: "", niche: "", bio: "", language: "pt-BR", status: "em_preparacao" },
  });

  const name = watch("name");
  useEffect(() => {
    if (slugEdited.current) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setValue("slug", "");
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      api.perfis
        .slugSuggestion(trimmed)
        .then(({ slug }) => {
          if (!cancelled && !slugEdited.current) setValue("slug", slug, { shouldValidate: false });
        })
        .catch(() => undefined); // sem sugestão, o campo continua editável
    }, SLUG_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [name, setValue]);

  const slugField = field("slug");

  // Quem digita o nome e envia na hora não espera o debounce: busca a sugestão antes de validar.
  async function onFormSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = getValues("name").trim();
    if (!slugEdited.current && trimmed) {
      const suggestion = await api.perfis.slugSuggestion(trimmed).catch(() => null);
      if (suggestion) setValue("slug", suggestion.slug);
    }
    await handleSubmit(onSubmit)();
  }

  async function onSubmit(data: CreatePerfilForm) {
    setError(null);
    try {
      const { perfil } = await api.perfis.create(data);
      await queryClient.invalidateQueries({ queryKey: ["perfis"] });
      navigate(`/app/perfis/${perfil.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "slug_in_use") {
        setFieldError("slug", { message: err.message });
      } else {
        setError(errorText(err));
      }
    }
  }

  return (
    <AppLayout>
      <PageHeader title="Novo perfil" description="Uma marca da agência; as contas nas plataformas entram depois." />
      <Card className="max-w-xl">
        <form onSubmit={(e) => void onFormSubmit(e)} className="space-y-4" noValidate>
          {error && <Alert tone="error">{error}</Alert>}
          <Field label="Nome" error={errors.name?.message}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("name")} />
            )}
          </Field>
          <Field label="Identificador" error={errors.slug?.message}>
            {({ id, describedBy, invalid }) => (
              <>
                <Input
                  id={id}
                  autoComplete="off"
                  spellCheck={false}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  {...slugField}
                  onChange={(e) => {
                    slugEdited.current = e.target.value !== "";
                    void slugField.onChange(e);
                  }}
                />
                <p className="text-xs text-muted">Sugerido a partir do nome. Depois de criado, não muda.</p>
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
              <Textarea id={id} rows={4} aria-invalid={invalid} aria-describedby={describedBy} {...field("bio")} />
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Idioma" error={errors.language?.message}>
              {({ id, describedBy, invalid }) => (
                <Select id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("language")}>
                  {Object.entries(languageLabel).map(([value, label]) => (
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
          <div className="flex gap-2">
            <Button type="submit" loading={isSubmitting}>
              {!isSubmitting && <Plus className="size-4" aria-hidden="true" />}
              Criar perfil
            </Button>
            <Button type="button" variant="ghost" onClick={() => navigate("/app/perfis")}>
              Cancelar
            </Button>
          </div>
        </form>
      </Card>
    </AppLayout>
  );
}
