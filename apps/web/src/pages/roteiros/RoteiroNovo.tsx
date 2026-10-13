/*
 * /app/estudio/videos/novo (spec 011, US1, T022; FR-051): "Novo vídeo" começa pelo perfil do vídeo (o
 * vídeo final vira um conteúdo desse perfil; a conta é escolhida depois, ao agendar, na 014). Depois:
 * o nome, o brief, os produtos aprovados (um ou vários, na ordem), o avatar (opcional) e a voz (vazio =
 * a voz padrão do avatar). As listas são as da agência (029), com as do perfil do vídeo primeiro.
 * Criar não planeja: o "Planejar com IA" fica no roteiro.
 */
import { ArrowDown, ArrowLeft, ArrowUp, Loader2, Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Page, usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { metaDetalhe, perfilNomeDe, rotaEstudio, TETO_TEXTO, useAssetsOpcoes, usePerfisTodos, useProdutosOpcoes } from "@/lib/estudio";
import { LIM } from "@/lib/roteiros";
import { useVozesAprovadas } from "@/lib/vozes";

interface ProdutoEscolhido {
  produtoId: string;
  nome: string;
}

export default function RoteiroNovo() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [perfilId, setPerfilId] = useState(params.get("perfil") ?? "");
  const [nome, setNome] = useState("");
  const [brief, setBrief] = useState("");
  const [avatarId, setAvatarId] = useState("");
  const [vozId, setVozId] = useState("");
  const [produtos, setProdutos] = useState<ProdutoEscolhido[]>([]);
  const [novoProduto, setNovoProduto] = useState("");
  const [erros, setErros] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  usePageMeta({ title: "Novo vídeo", ...metaDetalhe("videos", perfilId || null) });

  const perfis = usePerfisTodos();
  const ativos = (perfis.data ?? []).filter((p) => !p.archived);
  const aprovados = useProdutosOpcoes("aprovados", perfilId || null);
  const avatares = useAssetsOpcoes("avatar", perfilId || null);
  const vozes = useVozesAprovadas(perfilId || null);
  const nomeComPerfil = (n: string, item: { perfilId?: string | null; perfilNome?: string | null }) => `${n} · ${perfilNomeDe(item, perfis.data)}`;

  function adicionarProduto() {
    const p = aprovados.itens?.find((x) => x.id === novoProduto);
    if (!p || produtos.some((x) => x.produtoId === p.id) || produtos.length >= LIM.produtos) return;
    setProdutos([...produtos, { produtoId: p.id, nome: p.nomeComercial ?? p.name }]);
    setNovoProduto("");
  }

  function mover(i: number, d: -1 | 1) {
    const j = i + d;
    if (j < 0 || j >= produtos.length) return;
    const c = [...produtos];
    [c[i], c[j]] = [c[j]!, c[i]!];
    setProdutos(c);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!perfilId) errs.perfil = "Escolha o perfil do vídeo";
    if (!nome.trim()) errs.nome = "Dê um nome ao vídeo";
    if (produtos.length === 0) errs.produtos = "Escolha pelo menos um produto aprovado";
    setErros(errs);
    if (Object.keys(errs).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.roteiros.criar(perfilId, {
        nome: nome.trim(),
        brief: brief.trim(),
        avatarId: avatarId || null,
        vozId: vozId || null,
        produtos: produtos.map((p) => ({ produtoId: p.produtoId })),
      });
      toast.success("Vídeo criado. Agora peça o plano com a IA.");
      void navigate(`/app/roteiros/${r.id}`, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page>
      <Button type="button" variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground" asChild>
        <Link to={rotaEstudio("videos", perfilId || null)}>
          <ArrowLeft aria-hidden="true" />
          Voltar para os vídeos
        </Link>
      </Button>
      <h1 className="text-xl font-bold">Novo vídeo</h1>
      <Card className="shadow-card">
        <CardContent>
          <form onSubmit={(e) => void submit(e)} className="space-y-5" noValidate data-testid="roteiro-novo">
            <Field label="Perfil do vídeo" error={erros.perfil} hint="O vídeo final vira um conteúdo deste perfil; a conta é escolhida ao agendar.">
              {({ id, describedBy, invalid }) => (
                <NativeSelect id={id} value={perfilId} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setPerfilId(e.target.value)}>
                  <option value="">Escolha o perfil…</option>
                  {ativos.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Nome do vídeo" error={erros.nome} hint={`${nome.length}/${LIM.nome}`}>
              {({ id, describedBy, invalid }) => (
                <Input id={id} value={nome} maxLength={LIM.nome} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setNome(e.target.value)} />
              )}
            </Field>
            <Field label="Brief" hint="O que o vídeo deve mostrar e o tom da venda. A IA escreve as frases e propõe as cenas a partir daqui.">
              {({ id, describedBy }) => (
                <Textarea id={id} rows={4} value={brief} maxLength={LIM.brief} aria-describedby={describedBy} onChange={(e) => setBrief(e.target.value)} />
              )}
            </Field>

            <fieldset className="space-y-3" data-testid="roteiro-produtos">
              <legend className="text-sm font-medium">Produtos (aprovados, na ordem do vídeo)</legend>
              {produtos.length > 0 && (
                <ol className="space-y-1.5">
                  {produtos.map((p, i) => (
                    <li key={p.produtoId} className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm">
                      <span className="w-5 text-xs text-muted-foreground tabular-nums">{i + 1}.</span>
                      <span className="min-w-0 flex-1 truncate">{p.nome}</span>
                      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Subir ${p.nome}`} disabled={i === 0} onClick={() => mover(i, -1)}>
                        <ArrowUp aria-hidden="true" />
                      </Button>
                      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Descer ${p.nome}`} disabled={i === produtos.length - 1} onClick={() => mover(i, 1)}>
                        <ArrowDown aria-hidden="true" />
                      </Button>
                      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Tirar ${p.nome}`} onClick={() => setProdutos(produtos.filter((x) => x.produtoId !== p.produtoId))}>
                        <X aria-hidden="true" />
                      </Button>
                    </li>
                  ))}
                </ol>
              )}
              <div className="flex flex-wrap items-end gap-2">
                <Field label="Produto aprovado" className="min-w-56 flex-1" error={erros.produtos} hint={aprovados.truncado ? TETO_TEXTO : undefined}>
                  {({ id, describedBy, invalid }) => (
                    <NativeSelect id={id} value={novoProduto} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setNovoProduto(e.target.value)}>
                      <option value="">Escolha um produto…</option>
                      {(aprovados.itens ?? [])
                        .filter((p) => !produtos.some((x) => x.produtoId === p.id))
                        .map((p) => (
                          <option key={p.id} value={p.id}>
                            {nomeComPerfil(p.nomeComercial ?? p.name, p)}
                          </option>
                        ))}
                    </NativeSelect>
                  )}
                </Field>
                <Button type="button" variant="outline" disabled={!novoProduto || produtos.length >= LIM.produtos} onClick={adicionarProduto}>
                  <Plus aria-hidden="true" />
                  Adicionar produto
                </Button>
              </div>
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Avatar" hint={avatares.truncado ? TETO_TEXTO : "Opcional: sem avatar, o vídeo é só de produto."}>
                {({ id, describedBy }) => (
                  <NativeSelect id={id} value={avatarId} aria-describedby={describedBy} onChange={(e) => setAvatarId(e.target.value)}>
                    <option value="">Sem avatar</option>
                    {(avatares.itens ?? []).map((a) => (
                      <option key={a.id} value={a.id}>
                        {nomeComPerfil(a.name, a)}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Field label="Voz" hint={vozes.truncado ? TETO_TEXTO : "Vazio: a voz padrão do avatar."}>
                {({ id, describedBy }) => (
                  <NativeSelect id={id} value={vozId} aria-describedby={describedBy} onChange={(e) => setVozId(e.target.value)}>
                    <option value="">Voz padrão do avatar</option>
                    {(vozes.itens ?? []).map((v) => (
                      <option key={v.id} value={v.id}>
                        {nomeComPerfil(v.name, v)}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            </div>

            {error !== null && <ApiErrorAlert error={error} />}
            <Button type="submit" disabled={busy} aria-busy={busy}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
              Criar vídeo
            </Button>
          </form>
        </CardContent>
      </Card>
    </Page>
  );
}
