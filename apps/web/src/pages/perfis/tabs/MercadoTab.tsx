/*
 * Aba Mercado do perfil (spec 026, US4; `?aba=mercado`): as categorias do nicho (até 5, da
 * taxonomia observada; só o dono edita), as lojas seguidas, "Acompanhar por link" (qualquer
 * humano) e a lista de acompanhamentos com pausar / reativar / encerrar. O aviso do dia mostra
 * quantos acompanhamentos automáticos nasceram (relacionados de lojas seguidas e categorias).
 */
import type { Perfil } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Link2, Loader2, Save, Store, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { InteressesTabela } from "@/components/mercado/InteressesTabela";
import { EmptyState, HeaderCard, Page } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useEhDono } from "@/lib/conteudos";
import { invalidarInteresses, useCategoriasMercado, useInteressesPerfil, usePerfilConfigMercado, type MercadoInteresse } from "@/lib/mercado";

export function MercadoTab({ perfil }: { perfil: Perfil }) {
  return (
    <Page>
      <div className="grid gap-6 lg:grid-cols-2">
        <Nicho perfil={perfil} />
        <AcompanharPorLink perfil={perfil} />
      </div>
      <Acompanhamentos perfil={perfil} />
    </Page>
  );
}

function Nicho({ perfil }: { perfil: Perfil }) {
  const ehDono = useEhDono();
  const queryClient = useQueryClient();
  const config = usePerfilConfigMercado(perfil.id);
  const categorias = useCategoriasMercado();
  const c = config.data;
  const [ids, setIds] = useState<string[]>([]);
  const [max, setMax] = useState("10");
  const [avisar, setAvisar] = useState(true);
  const [escolha, setEscolha] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!c) return;
    setIds(c.categoriaIds);
    setMax(String(c.maxRelacionadosDia));
    setAvisar(c.avisarNovoEmAlta);
  }, [c]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!c) return;
    setBusy(true);
    setError(null);
    try {
      await api.mercado.perfilConfigSalvar(perfil.id, { version: c.version, categoriaIds: ids, maxRelacionadosDia: Number(max) || 0, avisarNovoEmAlta: avisar });
      toast.success("Nicho salvo. Os rankings dessas categorias entram na fila de hoje.");
      await invalidarInteresses(queryClient);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function deixarDeSeguir(lojaId: string) {
    if (!c) return;
    setError(null);
    try {
      await api.mercado.lojaDeixarDeSeguir(perfil.id, lojaId, c.version);
      toast.success("Loja deixou de ser seguida.");
      await invalidarInteresses(queryClient);
    } catch (err) {
      setError(err);
    }
  }

  const nomes = new Map((categorias.data?.itens ?? []).map((k) => [k.id, k.caminho]));
  const sugeridas = (categorias.data?.itens ?? []).filter((k) => !ids.includes(k.id));
  const maximo = c?.maximoCategorias ?? 5;

  return (
    <HeaderCard title="Nicho no TikTok Shop" description={`Até ${maximo} categorias da taxonomia observada na rede. Os rankings delas são coletados todo dia e os primeiros 30 viram acompanhamentos.`}>
      {config.isError && <ApiErrorAlert error={config.error} />}
      {c && (
        <form onSubmit={(e) => void salvar(e)} className="space-y-4">
          <div>
            <p className="text-sm font-medium">Categorias do nicho</p>
            {ids.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhuma categoria escolhida.</p>
            ) : (
              <ul className="mt-1 flex flex-wrap gap-1" aria-label="Categorias escolhidas">
                {ids.map((id) => (
                  <li key={id}>
                    <Badge variant="secondary" className="gap-1">
                      {nomes.get(id) ?? c.categorias.find((k) => k.id === id)?.caminho ?? id}
                      {ehDono && (
                        <button type="button" aria-label={`Remover categoria ${nomes.get(id) ?? id}`} className="rounded-full hover:text-destructive" onClick={() => setIds(ids.filter((x) => x !== id))}>
                          <X className="size-3" aria-hidden="true" />
                        </button>
                      )}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {ehDono && (
            <>
              <div className="flex flex-wrap items-end gap-2">
                <Field label="Adicionar categoria" className="min-w-0 flex-1">
                  {({ id }) => (
                    <NativeSelect id={id} value={escolha} onChange={(e) => setEscolha(e.target.value)} disabled={ids.length >= maximo || sugeridas.length === 0}>
                      <option value="">{sugeridas.length === 0 ? "A taxonomia chega com a primeira coleta" : "Escolha…"}</option>
                      {sugeridas.map((k) => (
                        <option key={k.id} value={k.id}>
                          {k.caminho} ({k.nProdutos})
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
                <Button type="button" variant="outline" size="sm" disabled={!escolha || ids.length >= maximo} onClick={() => { setIds([...ids, escolha]); setEscolha(""); }}>
                  Adicionar
                </Button>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Acompanhamentos automáticos por dia" hint="0 a 50; produtos novos de lojas seguidas e das categorias">
                  {({ id }) => <Input id={id} type="number" min={0} max={50} value={max} onChange={(e) => setMax(e.target.value)} />}
                </Field>
                <label className="flex items-center gap-2 self-end pb-2 text-sm">
                  <Switch checked={avisar} onCheckedChange={setAvisar} aria-label="Avisar quando um produto novo entra em alta" />
                  Avisar "novo em alta"
                </label>
              </div>
              {error !== null && <ApiErrorAlert error={error} onReload={() => void config.refetch()} />}
              <Button type="submit" disabled={busy} aria-busy={busy}>
                {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                Salvar nicho
              </Button>
            </>
          )}
          <div>
            <p className="text-sm font-medium">Lojas seguidas</p>
            {c.lojasSeguidas.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhuma. Siga uma loja pela aba Lojas do mercado ou pelo detalhe do produto.</p>
            ) : (
              <ul className="mt-1 flex flex-wrap gap-1" aria-label="Lojas seguidas">
                {c.lojasSeguidas.map((lj) => (
                  <li key={lj.id}>
                    <Badge variant="outline" className="gap-1">
                      <Store className="size-3" aria-hidden="true" />
                      {lj.nome}
                      {lj.oficial ? " · oficial" : ""}
                      <button type="button" aria-label={`Deixar de seguir ${lj.nome}`} className="rounded-full hover:text-destructive" onClick={() => void deixarDeSeguir(lj.id)}>
                        <X className="size-3" aria-hidden="true" />
                      </button>
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-xs text-muted-foreground" data-testid="relacionados-hoje">
            Acompanhamentos automáticos hoje: {c.relacionadosHoje} de {c.maxRelacionadosDia}.
          </p>
        </form>
      )}
    </HeaderCard>
  );
}

function AcompanharPorLink({ perfil }: { perfil: Perfil }) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [nota, setNota] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const i = await api.mercado.perfilInteresseCriar(perfil.id, { url: url.trim(), nota: nota.trim() });
      toast.success(`Acompanhando ${i.produto?.titulo ?? i.produto?.redeProdutoId ?? "o produto"}: duas fotos por dia a partir de hoje.`);
      setUrl("");
      setNota("");
      await invalidarInteresses(queryClient);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <HeaderCard title="Acompanhar por link" description="Cole o link de um produto do TikTok Shop. Ele entra no lago hoje e recebe duas fotos por dia; a ficha completa chega na primeira visita do coletor.">
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <Field label="Link do produto">{({ id }) => <Input id={id} type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…/product/7291…" required />}</Field>
        <Field label="Nota (opcional)">{({ id }) => <Input id={id} value={nota} onChange={(e) => setNota(e.target.value)} maxLength={2000} />}</Field>
        {error !== null && <ApiErrorAlert error={error} />}
        <Button type="submit" disabled={busy || url.trim() === ""} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Link2 aria-hidden="true" />}
          Acompanhar
        </Button>
      </form>
    </HeaderCard>
  );
}

function Acompanhamentos({ perfil }: { perfil: Perfil }) {
  const [origem, setOrigem] = useState("");
  const [situacao, setSituacao] = useState("");
  const lista = useInteressesPerfil(perfil.id, {
    ...(origem ? { origem: origem as MercadoInteresse["origem"] } : {}),
    ...(situacao ? { situacao: situacao as MercadoInteresse["situacao"] } : {}),
  });
  return (
    <HeaderCard
      title="Acompanhamentos"
      description={lista.data ? `${lista.data.total} acompanhamento${lista.data.total === 1 ? "" : "s"} (os de vitrine valem para todos os perfis)` : "Carregando…"}
      actions={
        <div className="flex flex-wrap gap-2">
          <Field label="Origem" className="w-44">
            {({ id }) => (
              <NativeSelect id={id} value={origem} onChange={(e) => setOrigem(e.target.value)}>
                <option value="">Todas</option>
                <option value="manual">Manual (link)</option>
                <option value="vitrine">Vitrine do dono</option>
                <option value="ranking">Ranking</option>
                <option value="loja">Loja seguida</option>
                <option value="categoria">Categoria do nicho</option>
              </NativeSelect>
            )}
          </Field>
          <Field label="Situação" className="w-36">
            {({ id }) => (
              <NativeSelect id={id} value={situacao} onChange={(e) => setSituacao(e.target.value)}>
                <option value="">Todas</option>
                <option value="ativo">Ativo</option>
                <option value="pausado">Pausado</option>
                <option value="encerrado">Encerrado</option>
              </NativeSelect>
            )}
          </Field>
        </div>
      }
    >
      {lista.isError && <ApiErrorAlert error={lista.error} />}
      <InteressesTabela itens={lista.data?.itens} loading={lista.isPending} empty={<EmptyState titulo="Nada acompanhado ainda" descricao="Cole um link, escolha as categorias do nicho ou siga uma loja: o SociMan passa a fotografar esses produtos todo dia." />} />
    </HeaderCard>
  );
}
