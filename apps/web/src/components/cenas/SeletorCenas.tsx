/*
 * Bloco "Cenas" do vídeo próprio (spec 010, US3; FR-012): quais cenas do perfil entraram neste vídeo.
 * Ligar uma cena a marca como `usada`; tirar o último vínculo a devolve a `pronta`. Só cenas prontas
 * ou usadas, não arquivadas, do mesmo perfil. O vínculo não aprova nem agenda nada (princípio I).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard, Film, Loader2, PencilLine, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { conteudoCenasKey, semRetry404, statusCenaLabel, statusCenaTone, useCenasAgencia, type CenaResumo } from "@/lib/cenas";
import { api } from "@/lib/api";
import { invalidarConteudos } from "@/lib/conteudos";
import { EmptyState } from "@/components/shell";

export function SeletorCenas({
  conteudo,
}: {
  conteudo: { id: string; version: number; archived: boolean; perfil: { id: string }; cenas?: CenaResumo[] | null };
}) {
  const ligadas = useQuery({
    queryKey: conteudoCenasKey(conteudo.id),
    queryFn: () => api.cenas.doConteudo(conteudo.id).then((r) => r.items),
    // O detalhe do conteúdo já traz as cenas; a rota própria só serve de reserva.
    enabled: conteudo.cenas == null,
    retry: semRetry404,
  });
  const itens = conteudo.cenas ?? ligadas.data ?? [];
  const [aberto, setAberto] = useState(false);

  return (
    <Card className="gap-3 shadow-card" aria-labelledby="cenas-do-video">
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <h2 id="cenas-do-video" className="flex items-center gap-2">
            <Clapperboard className="size-4 text-muted-foreground" aria-hidden="true" />
            Cenas
          </h2>
          {!conteudo.archived && (
            <Button type="button" size="sm" variant="outline" onClick={() => setAberto(true)}>
              <PencilLine aria-hidden="true" />
              Escolher cenas
            </Button>
          )}
        </CardTitle>
        <CardDescription>As cenas do Flow que entraram neste vídeo. Ficam marcadas como usadas.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {ligadas.isError && <ApiErrorAlert error={ligadas.error} />}
        {itens.length === 0 ? (
          <EmptyState titulo="Nenhuma cena ligada." className="py-4" />
        ) : (
          <>
            <ul aria-label="Cenas do vídeo" className="space-y-2">
              {itens.map((c) => (
                <li key={c.id} className="flex items-center gap-2 text-sm">
                  <Film className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <Link to={`/app/cenas/${c.id}`} className="min-w-0 truncate font-medium underline-offset-2 hover:underline">
                    {c.nome}
                  </Link>
                  <Badge className={statusCenaTone[c.status]}>{statusCenaLabel[c.status]}</Badge>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">Vídeo com cenas geradas por IA: marque o selo de conteúdo de IA ao postar.</p>
          </>
        )}
      </CardContent>
      {aberto && <EscolherDialog conteudo={conteudo} atuais={itens} onClose={() => setAberto(false)} />}
    </Card>
  );
}

function EscolherDialog({
  conteudo,
  atuais,
  onClose,
}: {
  conteudo: { id: string; version: number; perfil: { id: string } };
  atuais: CenaResumo[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [texto, setTexto] = useState("");
  const [q, setQ] = useState("");
  const [marcadas, setMarcadas] = useState<Set<string>>(() => new Set(atuais.map((c) => c.id)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const t = window.setTimeout(() => setQ(texto.trim()), 250);
    return () => window.clearTimeout(t);
  }, [texto]);
  const cenas = useCenasAgencia("todos", { q: q || undefined });
  // Só pronta e usada entram (rascunho não tem prompt congelado).
  const opcoes = useMemo(() => {
    const vindas = (cenas.data?.pages.flatMap((p) => p.items) ?? []).filter((c) => c.status !== "rascunho" && !c.arquivada);
    const extra = atuais.filter((a) => !vindas.some((v) => v.id === a.id));
    return [...extra, ...vindas];
  }, [cenas.data, atuais]);

  function alternar(id: string, on: boolean) {
    setMarcadas((cur) => {
      const next = new Set(cur);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function salvar() {
    setError(null);
    setBusy(true);
    try {
      await api.cenas.definirDoConteudo(conteudo.id, conteudo.version, [...marcadas]);
      toast.success("Cenas do vídeo salvas.");
      await Promise.all([
        invalidarConteudos(queryClient, conteudo.id),
        queryClient.invalidateQueries({ queryKey: conteudoCenasKey(conteudo.id) }),
        queryClient.invalidateQueries({ queryKey: ["cenas"] }),
        queryClient.invalidateQueries({ queryKey: ["cena"] }),
      ]);
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Cenas deste vídeo</DialogTitle>
          <DialogDescription>Marque as cenas prontas que entraram no vídeo. Tirar uma cena a devolve a pronta se ela não estiver em outro vídeo.</DialogDescription>
        </DialogHeader>
        <Input type="search" aria-label="Buscar cenas" placeholder="Buscar por nome, ação, fala ou produto" value={texto} onChange={(e) => setTexto(e.target.value)} />
        {cenas.isError && <ApiErrorAlert error={cenas.error} />}
        {cenas.isPending && <p className="text-sm text-muted-foreground">Carregando…</p>}
        {cenas.data && opcoes.length === 0 && <EmptyState titulo="Nenhuma cena pronta encontrada." descricao="Marque a cena como pronta antes." className="py-4" />}
        <ul aria-label="Cenas prontas do perfil" className="max-h-[50vh] space-y-1 overflow-y-auto">
          {opcoes.map((c) => (
            <li key={c.id}>
              <label className="flex cursor-pointer items-center gap-3 rounded-md p-2 text-sm hover:bg-muted/50">
                <Checkbox checked={marcadas.has(c.id)} onCheckedChange={(v) => alternar(c.id, v === true)} aria-label={c.nome} />
                <span className="min-w-0 flex-1 truncate">{c.nome}</span>
                <Badge className={statusCenaTone[c.status]}>{statusCenaLabel[c.status]}</Badge>
              </label>
            </li>
          ))}
        </ul>
        {cenas.hasNextPage && (
          <Button type="button" variant="ghost" size="sm" disabled={cenas.isFetchingNextPage} onClick={() => void cenas.fetchNextPage()}>
            Carregar mais
          </Button>
        )}
        {error !== null && <ApiErrorAlert error={error} onReload={() => void invalidarConteudos(queryClient, conteudo.id)} />}
        <DialogFooter>
          <Button type="button" variant="ghost" disabled={busy} onClick={onClose}>
            Cancelar
          </Button>
          <Button type="button" disabled={busy} aria-busy={busy} onClick={() => void salvar()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar cenas
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
