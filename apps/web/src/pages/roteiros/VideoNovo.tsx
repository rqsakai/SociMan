/*
 * /app/estudio/videos/novo (spec 031, US1, T021; FR-001..007, R10): o "Novo vídeo" guiado. Seis
 * blocos, um por vez: tipo de vídeo, perfil, avatar e voz, cenário, produto e duração (da grade).
 * Os itens vêm da biblioteca da agência (029), de qualquer perfil base; o perfil do bloco 2 é o
 * perfil base do vídeo (guia, proibidas e padrões). Voltar a um bloco mantém as outras escolhas;
 * trocar o perfil não desmarca nada (só avisa que o guia muda); trocar o avatar refaz a voz
 * pré-escolhida, se ela não foi trocada à mão. No fim, o resumo das 6 escolhas e "Criar vídeo",
 * que abre o roteiro com o chat de perguntas (US2).
 */
import { ArrowLeft, ArrowRight, Info, Loader2, Plus, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Page, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { BlocoEscolha, type ItemEscolha } from "@/components/video-guiado/BlocoEscolha";
import { api } from "@/lib/api";
import { metaDetalhe, perfilNomeDe, rotaEstudio, TETO_TEXTO, useAssetsOpcoes, usePerfisTodos } from "@/lib/estudio";
import { LIM } from "@/lib/roteiros";
import { cn } from "@/lib/utils";
import { BLOCOS, duracaoTexto, TIPOS_VIDEO, useGrade, useProdutosBloco } from "@/lib/videoGuiado";
import { useVoz, useVozesAprovadas } from "@/lib/vozes";

const RESUMO = BLOCOS.length;

export default function VideoNovo() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [passo, setPasso] = useState(0);
  const [alcancado, setAlcancado] = useState(0);
  const [tipo, setTipo] = useState<string | null>("avatar_pov");
  const [perfilId, setPerfilId] = useState<string | null>(params.get("perfil"));
  const [avatarId, setAvatarId] = useState<string | null>(null);
  const [vozId, setVozId] = useState<string | null>(null);
  const [vozManual, setVozManual] = useState(false);
  const [cenarioId, setCenarioId] = useState<string | null>(null);
  const [produtoId, setProdutoId] = useState<string | null>(null);
  const [duracaoS, setDuracaoS] = useState<number | null>(null);
  const [nome, setNome] = useState("");
  const [perfilTrocado, setPerfilTrocado] = useState(false);
  const [desmarcados, setDesmarcados] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  usePageMeta({ title: "Novo vídeo", ...metaDetalhe("videos", perfilId) });

  const perfis = usePerfisTodos();
  const ativos = (perfis.data ?? []).filter((p) => !p.archived);
  const avatares = useAssetsOpcoes("avatar", perfilId);
  const cenariosTodos = useAssetsOpcoes("cenario", perfilId);
  const vozes = useVozesAprovadas(perfilId);
  const produtos = useProdutosBloco(perfilId);
  const grade = useGrade();
  // A voz padrão e o consentimento vêm no resumo do avatar (`vozId`, `revogado`); só a voz escolhida
  // é lida (o áudio da referência): nada de uma leitura por item da lista.
  const voz = useVoz(vozId ?? "");

  // O avatar com o consentimento revogado não gera nada novo: fica de fora, no contador.
  const avatarItens = avatares.itens?.filter((a) => !a.revogado);
  const avataresFora = (avatares.itens?.length ?? 0) - (avatarItens?.length ?? 0);
  const avatarSel = avatares.itens?.find((a) => a.id === avatarId);
  // O cenário só serve com a imagem da cena do cadastro padronizado (025, `temCena`).
  const cenarios = cenariosTodos.itens?.filter((c) => c.temCena);
  const cenariosFora = (cenariosTodos.itens?.length ?? 0) - (cenarios?.length ?? 0);
  const vozPadrao = avatarSel?.vozId ?? null;
  const avatarRevogado = avatarSel?.revogado === true;
  const vozPadraoAprovada = vozPadrao !== null && (vozes.itens ?? []).some((v) => v.id === vozPadrao);

  // A voz pré-escolhida segue o avatar enquanto o operador não troca à mão (FR-003, FR-006).
  useEffect(() => {
    if (vozManual || !avatarSel || !vozes.itens) return;
    setVozId(vozPadraoAprovada ? vozPadrao : null);
  }, [avatarSel, vozes.itens, vozManual, vozPadrao, vozPadraoAprovada]);

  // Uma escolha que deixou de valer (arquivada, produto fora de aprovado) é desmarcada e avisada.
  useEffect(() => {
    const fora: string[] = [];
    if (avatarId && avatarItens && !avatarItens.some((a) => a.id === avatarId)) {
      fora.push("o avatar");
      setAvatarId(null);
    }
    if (cenarioId && cenarios && !cenarios.some((c) => c.id === cenarioId)) {
      fora.push("o cenário");
      setCenarioId(null);
    }
    if (produtoId && produtos.aprovados && !produtos.aprovados.some((p) => p.id === produtoId)) {
      fora.push("o produto");
      setProdutoId(null);
    }
    if (vozId && vozes.itens && !vozes.itens.some((v) => v.id === vozId)) {
      fora.push("a voz");
      setVozId(null);
    }
    if (fora.length > 0) setDesmarcados(fora);
  }, [avatarId, avatarItens, cenarioId, cenarios, produtoId, produtos.aprovados, vozId, vozes.itens]);

  const prontos = [
    tipo !== null,
    perfilId !== null && ativos.some((p) => p.id === perfilId),
    avatarId !== null && vozId !== null && !avatarRevogado,
    cenarioId !== null,
    produtoId !== null,
    duracaoS !== null,
  ];
  const tudoPronto = prontos.every(Boolean);

  function ir(n: number) {
    setPasso(n);
    setAlcancado((a) => Math.max(a, n));
    setError(null);
  }

  const nomeDe = {
    tipo: TIPOS_VIDEO.find((t) => t.id === tipo)?.titulo,
    perfil: ativos.find((p) => p.id === perfilId)?.name,
    avatar: avatares.itens?.find((a) => a.id === avatarId)?.name,
    voz: vozes.itens?.find((v) => v.id === vozId)?.name,
    cenario: cenarios?.find((c) => c.id === cenarioId)?.name,
    produto: (() => {
      const p = produtos.aprovados?.find((x) => x.id === produtoId);
      return p ? (p.nomeComercial ?? p.name) : undefined;
    })(),
    duracao: duracaoS !== null ? duracaoTexto(duracaoS) : undefined,
  };
  const valores = [nomeDe.tipo, nomeDe.perfil, nomeDe.avatar && `${nomeDe.avatar}${nomeDe.voz ? ` · voz ${nomeDe.voz}` : ""}`, nomeDe.cenario, nomeDe.produto, nomeDe.duracao];

  async function criar() {
    if (!tudoPronto) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.roteiros.criarGuiado({
        perfilId: perfilId!,
        tipoVideo: "avatar_pov",
        avatarId: avatarId!,
        vozId,
        cenarioId: cenarioId!,
        produtoId: produtoId!,
        duracaoS: duracaoS!,
        nome: nome.trim() || null,
      });
      toast.success("Vídeo criado. Agora responda às perguntas da IA.");
      void navigate(`/app/roteiros/${r.id}`, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const nomeComPerfil = (item: { perfilId?: string | null; perfilNome?: string | null }) => perfilNomeDe(item, perfis.data);

  return (
    <Page>
      <Button type="button" variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground" asChild>
        <Link to={rotaEstudio("videos", perfilId)}>
          <ArrowLeft aria-hidden="true" />
          Voltar para os vídeos
        </Link>
      </Button>
      <h1 className="text-xl font-bold">Novo vídeo</h1>

      <nav aria-label="Blocos do novo vídeo">
        <ol className="flex flex-wrap gap-2" data-testid="blocos-video">
          {[...BLOCOS, "Resumo"].map((rotulo, i) => {
            const atual = i === passo;
            return (
              <li key={rotulo}>
                <Button
                  type="button"
                  size="sm"
                  variant={atual ? "default" : "outline"}
                  aria-current={atual ? "step" : undefined}
                  disabled={i > alcancado}
                  onClick={() => ir(i)}
                  className="max-w-56"
                >
                  <span className="truncate">
                    {i + 1}. {rotulo}
                    {i < RESUMO && valores[i] && !atual && <span className="font-normal text-muted-foreground">: {valores[i]}</span>}
                  </span>
                </Button>
              </li>
            );
          })}
        </ol>
      </nav>

      {perfilTrocado && (
        <Alert data-testid="aviso-perfil">
          <Info aria-hidden="true" />
          <AlertTitle>Perfil trocado</AlertTitle>
          <AlertDescription>
            As outras escolhas continuam. O guia de comunicação e as palavras proibidas de {nomeDe.perfil ?? "o novo perfil"} passam a valer para este vídeo.
          </AlertDescription>
        </Alert>
      )}
      {desmarcados.length > 0 && (
        <Alert data-testid="aviso-desmarcados">
          <TriangleAlert className="text-warning" aria-hidden="true" />
          <AlertTitle>Escolha desmarcada</AlertTitle>
          <AlertDescription>Deixou de valer e foi desmarcado: {desmarcados.join(", ")}. Escolha de novo.</AlertDescription>
        </Alert>
      )}

      <Card className="shadow-card">
        <CardContent className="flex flex-col gap-5" data-testid={passo < RESUMO ? `bloco-${passo + 1}` : "bloco-resumo"}>
          {passo === 0 && (
            <BlocoEscolha
              rotulo="1. Tipo de vídeo"
              variante="texto"
              descricao="Os outros tipos chegam em breve."
              itens={TIPOS_VIDEO.map((t): ItemEscolha => ({ id: t.id, titulo: t.titulo, subtitulo: t.subtitulo, desabilitado: t.emBreve, motivo: t.emBreve ? "Em breve" : undefined }))}
              valor={tipo}
              onChange={setTipo}
            />
          )}

          {passo === 1 && (
            <BlocoEscolha
              rotulo="2. Perfil"
              variante="texto"
              descricao="O perfil base do vídeo: o guia de comunicação, as palavras proibidas e os padrões. O vídeo final vira um conteúdo deste perfil."
              carregando={perfis.isPending}
              itens={ativos.map((p) => ({ id: p.id, titulo: p.name }))}
              valor={perfilId}
              onChange={(id) => {
                if (perfilId !== null && id !== perfilId && alcancado > 1) setPerfilTrocado(true);
                setPerfilId(id);
              }}
              vazio={{ titulo: "Nenhum perfil ativo", descricao: "Cadastre um perfil para criar vídeos.", acao: "Abrir perfis", href: "/app/perfis" }}
            />
          )}

          {passo === 2 && (
            <>
              <BlocoEscolha
                rotulo="3. Avatar"
                descricao={avatares.truncado ? TETO_TEXTO : "Os avatares da biblioteca da agência, os do perfil do vídeo primeiro."}
                carregando={avatares.isPending}
                itens={(avatarItens ?? []).map((a) => ({ id: a.id, titulo: a.name, subtitulo: nomeComPerfil(a), thumbUrl: a.thumbUrl }))}
                valor={avatarId}
                onChange={(id) => {
                  if (id === avatarId) return;
                  setAvatarId(id);
                  if (!vozManual) setVozId(null);
                }}
                fora={{ quantidade: avataresFora, motivo: avataresFora === 1 ? "consentimento revogado" : "consentimentos revogados" }}
                vazio={{ titulo: "Nenhum avatar na biblioteca", descricao: "Cadastre um avatar no AI Studio.", acao: "Abrir avatares", href: rotaEstudio("avatares") }}
              />
              {avatarRevogado && (
                <Alert variant="destructive" data-testid="avatar-revogado">
                  <TriangleAlert aria-hidden="true" />
                  <AlertTitle>Consentimento revogado</AlertTitle>
                  <AlertDescription>Este avatar não pode gerar nada novo. Escolha outro.</AlertDescription>
                </Alert>
              )}
              {avatarId !== null && (
                <BlocoEscolha
                  rotulo="Voz"
                  variante="voz"
                  descricao={
                    vozes.truncado
                      ? TETO_TEXTO
                      : vozPadraoAprovada
                          ? "A voz padrão do avatar já vem escolhida; troque se quiser."
                          : "O avatar não tem voz padrão aprovada: escolha uma voz aprovada."
                  }
                  carregando={vozes.isPending}
                  itens={(vozes.itens ?? []).map((v) => ({
                    id: v.id,
                    titulo: v.name,
                    subtitulo: v.id === vozPadrao ? "Voz padrão do avatar" : nomeComPerfil(v),
                    audio: v.id === vozId ? (voz.data?.referencia ?? null) : null,
                  }))}
                  valor={vozId}
                  onChange={(id) => {
                    setVozId(id);
                    setVozManual(true);
                  }}
                  onRenovarAudio={() => void voz.refetch()}
                  vazio={{
                    titulo: "Nenhuma voz aprovada na agência",
                    descricao: "O vídeo precisa de uma voz aprovada para a narração.",
                    acao: "Cadastrar uma voz",
                    href: rotaEstudio("vozes"),
                  }}
                />
              )}
            </>
          )}

          {passo === 3 && (
            <BlocoEscolha
              rotulo="4. Cenário"
              descricao={cenariosTodos.truncado ? TETO_TEXTO : "Só os cenários com a imagem da cena do cadastro padronizado."}
              carregando={cenariosTodos.isPending}
              itens={(cenarios ?? []).map((c) => ({ id: c.id, titulo: c.name, subtitulo: nomeComPerfil(c), thumbUrl: c.thumbUrl }))}
              valor={cenarioId}
              onChange={setCenarioId}
              fora={{ quantidade: cenariosFora, motivo: "sem a imagem da cena" }}
              vazio={{ titulo: "Nenhum cenário pronto", descricao: "Cadastre um cenário com a imagem da cena no AI Studio.", acao: "Abrir cenários", href: rotaEstudio("cenarios") }}
            />
          )}

          {passo === 4 && (
            <BlocoEscolha
              rotulo="5. Produto"
              descricao={produtos.truncado ? TETO_TEXTO : "Só os produtos aprovados do catálogo."}
              carregando={produtos.isPending}
              itens={(produtos.aprovados ?? []).map((p) => ({ id: p.id, titulo: p.nomeComercial ?? p.name, subtitulo: nomeComPerfil(p), thumbUrl: p.thumbUrl }))}
              valor={produtoId}
              onChange={setProdutoId}
              fora={{ quantidade: produtos.fora, motivo: produtos.fora === 1 ? "não aprovado" : "não aprovados" }}
              vazio={{ titulo: "Nenhum produto aprovado", descricao: "Cadastre e aprove um produto no AI Studio.", acao: "Abrir produtos", href: rotaEstudio("produtos") }}
            />
          )}

          {passo === 5 && (
            <BlocoEscolha
              rotulo="6. Duração"
              variante="texto"
              descricao={grade.data ? `Na grade de trechos de ${grade.data.trechoBaseS} s, que o gerador de vídeo cumpre bem.` : undefined}
              carregando={grade.isPending}
              itens={(grade.data?.opcoes ?? []).map((s) => ({
                id: String(s),
                titulo: duracaoTexto(s),
                subtitulo: grade.data ? `${s / grade.data.trechoBaseS} ${s / grade.data.trechoBaseS === 1 ? "trecho" : "trechos"}` : undefined,
              }))}
              valor={duracaoS !== null ? String(duracaoS) : null}
              onChange={(id) => setDuracaoS(Number(id))}
            />
          )}
          {passo === 5 && grade.isError && <ApiErrorAlert error={grade.error} />}

          {passo === RESUMO && (
            <section className="flex flex-col gap-4" aria-labelledby="resumo-titulo">
              <h2 id="resumo-titulo" className="text-sm font-medium">
                Resumo
              </h2>
              <dl className="grid gap-2 text-sm sm:grid-cols-[auto_1fr_auto] sm:items-center sm:gap-x-4" data-testid="resumo-escolhas">
                {BLOCOS.map((rotulo, i) => (
                  <div key={rotulo} className="contents" data-testid={`resumo-${i + 1}`}>
                    <dt className="text-muted-foreground">{rotulo}</dt>
                    <dd className={cn("min-w-0 break-words", !valores[i] && "text-destructive")}>{valores[i] ?? "Falta escolher"}</dd>
                    <dd>
                      <Button type="button" variant="link" size="sm" className="h-auto p-0" onClick={() => ir(i)} aria-label={`Trocar ${rotulo.toLowerCase()}`}>
                        Trocar
                      </Button>
                    </dd>
                  </div>
                ))}
              </dl>
              <Field label="Nome do vídeo (opcional)" hint={`Vazio: o nome do produto e a data. ${nome.length}/${LIM.nome}`}>
                {({ id, describedBy }) => <Input id={id} value={nome} maxLength={LIM.nome} aria-describedby={describedBy} onChange={(e) => setNome(e.target.value)} />}
              </Field>
              {error !== null && <ApiErrorAlert error={error} />}
            </section>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
            <Button type="button" variant="outline" disabled={passo === 0} onClick={() => ir(passo - 1)}>
              <ArrowLeft aria-hidden="true" />
              Voltar
            </Button>
            {passo < RESUMO ? (
              <Button type="button" disabled={!prontos[passo]} onClick={() => ir(passo + 1)}>
                Continuar
                <ArrowRight aria-hidden="true" />
              </Button>
            ) : (
              <Button type="button" disabled={!tudoPronto || busy} aria-busy={busy} onClick={() => void criar()}>
                {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
                Criar vídeo
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </Page>
  );
}
