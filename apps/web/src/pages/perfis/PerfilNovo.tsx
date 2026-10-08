import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, Page, usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "../../lib/api";
import { createPerfilForm, type CreatePerfilForm } from "../../lib/forms";
import { languageLabel, perfilStatusLabel } from "../../lib/perfis";

const SLUG_DEBOUNCE_MS = 300;

// /app/perfis/novo: o identificador (slug) é sugerido pela API enquanto se digita o nome e só
// pode ser ajustado aqui, antes de criar (FR-002a).
export default function PerfilNovo() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  usePageMeta({ title: "Novo perfil", breadcrumbs: [{ label: "Perfis", to: "/app/perfis" }] });
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
      toast.success(`Perfil ${perfil.name} criado.`);
      navigate(`/app/perfis/${perfil.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "slug_in_use") {
        setFieldError("slug", { message: err.message });
      } else {
        setError(err);
      }
    }
  }

  return (
    <Page>
      <PageHeading title="Novo perfil" description="Uma marca da agência; as contas nas plataformas entram depois." />
      <HeaderCard title="Dados do perfil" description="Nome, nicho, descrição, idioma e status.">
        <form onSubmit={(e) => void onFormSubmit(e)} className="max-w-2xl space-y-4" noValidate>
          {error !== null && <ApiErrorAlert error={error} />}
          <Field label="Nome" error={errors.name?.message}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} {...field("name")} />
            )}
          </Field>
          <Field
            label="Identificador"
            error={errors.slug?.message}
            hint="Sugerido a partir do nome. Depois de criado, não muda."
          >
            {({ id, describedBy, invalid }) => (
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
                <NativeSelect id={id} aria-invalid={invalid} aria-describedby={describedBy} {...field("language")}>
                  {Object.entries(languageLabel).map(([value, label]) => (
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
          <div className="flex gap-2">
            <Button type="submit" disabled={isSubmitting} aria-busy={isSubmitting}>
              {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
              Criar perfil
            </Button>
            <Button type="button" variant="ghost" onClick={() => navigate("/app/perfis")}>
              Cancelar
            </Button>
          </div>
        </form>
      </HeaderCard>
    </Page>
  );
}
