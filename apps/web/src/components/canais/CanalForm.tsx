/*
 * "Adicionar canal" (spec 006, US1; T030): colar o link, o @ ou o ID → prévia (nome, avatar,
 * inscritos, vídeos e o custo da consulta em unidades da cota) → perfis → salvar.
 *
 * <CanalForm open onOpenChange onCreated />
 *   - canal já cadastrado (inclusive arquivado): "Este canal já está cadastrado" com o link para ele;
 *   - YouTube sem chave ou com chave inválida: aviso vindo de GET /api/integracoes (T073).
 * O status de direito começa "Sem acordo" e só o dono muda, no detalhe do canal.
 */
import { ApiError } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, ExternalLink, Loader2, Save, Search, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatCount, type CanalCandidato } from "@/lib/canais";
import { integracoesQuery, youtubeAviso } from "@/lib/integracoes";
import { usePerfisAtivos } from "@/lib/usePerfis";
import { DireitoBadge } from "./DireitoBadge";

interface Preview {
  candidato: CanalCandidato;
  custo: number;
  existente: { id: string } | null;
}

export function CanalForm({
  open,
  onOpenChange,
  perfilIdInicial,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  perfilIdInicial?: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const perfis = usePerfisAtivos();
  const integracoes = useQuery(integracoesQuery);
  const aviso = youtubeAviso(integracoes.data);
  const [entrada, setEntrada] = useState("");
  const [entradaError, setEntradaError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [perfilIds, setPerfilIds] = useState<string[]>(perfilIdInicial ? [perfilIdInicial] : []);
  const [busy, setBusy] = useState<"resolver" | "salvar" | null>(null);
  const [error, setError] = useState<unknown>(null);

  function reset() {
    setEntrada("");
    setEntradaError(null);
    setPreview(null);
    setPerfilIds(perfilIdInicial ? [perfilIdInicial] : []);
    setError(null);
  }

  async function resolver(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPreview(null);
    const text = entrada.trim();
    if (!text) return setEntradaError("Cole o link, o @ ou o ID do canal");
    setEntradaError(null);
    setBusy("resolver");
    try {
      setPreview(await api.canais.resolver(text));
    } catch (err) {
      if (err instanceof ApiError && (err.code === "invalid_channel_input" || err.code === "canal_not_found")) setEntradaError(err.message);
      else setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function salvar() {
    if (!preview) return;
    setError(null);
    setBusy("salvar");
    try {
      const { canal } = await api.canais.create({ youtubeChannelId: preview.candidato.youtubeChannelId, perfilIds });
      toast.success(`Canal "${canal.title}" cadastrado. A busca dos vídeos começa sozinha.`);
      await queryClient.invalidateQueries({ queryKey: ["canais"] });
      onOpenChange(false);
      reset();
      void navigate(`/app/fontes/${canal.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "canal_exists" && typeof err.details.id === "string") {
        setPreview({ ...preview, existente: { id: err.details.id } });
      } else setError(err);
    } finally {
      setBusy(null);
    }
  }

  const togglePerfil = (id: string) => setPerfilIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  const c = preview?.candidato;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Adicionar canal</DialogTitle>
          <DialogDescription>Cole o link do canal no YouTube, o @ ou o ID (UC…). Nada é gravado antes de salvar.</DialogDescription>
        </DialogHeader>

        {aviso && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{aviso.titulo}</AlertTitle>
            <AlertDescription>{aviso.texto}</AlertDescription>
          </Alert>
        )}

        <form onSubmit={(e) => void resolver(e)} className="flex flex-wrap items-end gap-2" noValidate>
          <Field label="Link, @ ou ID do canal" error={entradaError ?? undefined} className="min-w-0 flex-1">
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                autoFocus
                autoComplete="off"
                placeholder="https://www.youtube.com/@canal"
                value={entrada}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setEntrada(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" variant="outline" disabled={busy !== null} aria-busy={busy === "resolver"}>
            {busy === "resolver" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Search aria-hidden="true" />}
            Buscar canal
          </Button>
        </form>

        {c && preview && (
          <section aria-label="Prévia do canal" className="space-y-4 rounded-lg border p-4">
            <div className="flex items-center gap-3">
              {c.avatarUrl ? (
                <img src={c.avatarUrl} alt="" className="size-14 rounded-full bg-muted object-cover" />
              ) : (
                <span className="tone-dark flex size-14 items-center justify-center rounded-full" aria-hidden="true">
                  <Users className="size-6" />
                </span>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-base font-semibold">{c.title}</p>
                <p className="truncate text-sm text-muted-foreground">{c.handle ? `@${c.handle.replace(/^@/, "")}` : c.youtubeChannelId}</p>
                <p className="text-sm">
                  <strong>{formatCount(c.subscribers)}</strong> inscritos · <strong>{formatCount(c.videoCount)}</strong> vídeos
                </p>
              </div>
              <DireitoBadge direito="sem_acordo" />
            </div>
            <p className="text-xs text-muted-foreground">
              Esta consulta usou {preview.custo} {preview.custo === 1 ? "unidade" : "unidades"} da cota diária do YouTube.
            </p>

            {preview.existente ? (
              <Alert>
                <CircleAlert aria-hidden="true" />
                <AlertTitle>Este canal já está cadastrado</AlertTitle>
                <AlertDescription>
                  <Button variant="outline" size="sm" className="mt-1" asChild>
                    <Link to={`/app/fontes/${preview.existente.id}`} onClick={() => onOpenChange(false)}>
                      <ExternalLink aria-hidden="true" />
                      Abrir o canal cadastrado
                    </Link>
                  </Button>
                </AlertDescription>
              </Alert>
            ) : (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">Perfis que usam este canal</legend>
                {perfis.data?.length === 0 && <p className="text-sm text-muted-foreground">Nenhum perfil ativo.</p>}
                <div className="grid gap-2 sm:grid-cols-2">
                  {perfis.data?.map((p) => (
                    <label key={p.id} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm has-[:checked]:border-primary">
                      <input type="checkbox" className="size-4 accent-primary" checked={perfilIds.includes(p.id)} onChange={() => togglePerfil(p.id)} />
                      <span className="truncate">{p.name}</span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">O direito começa como "Sem acordo"; só o dono muda, no detalhe do canal.</p>
              </fieldset>
            )}
          </section>
        )}

        {error !== null && <ApiErrorAlert error={error} />}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="button" disabled={!preview || Boolean(preview.existente) || busy !== null} aria-busy={busy === "salvar"} onClick={() => void salvar()}>
            {busy === "salvar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar canal
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
