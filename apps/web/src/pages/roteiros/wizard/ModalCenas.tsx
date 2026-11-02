/*
 * O modal de cenas (spec 031, US4, T042; FR-019..024, R7, R9): o portão do texto no wizard. Para
 * cada posição do plano, a cena proposta (miniatura, nome, onde já foi usada), o nível ("sem custo"
 * no reuso total, "refaz as imagens" no reuso do plano, ou "criar nova") e o motivo da IA. O
 * operador troca a decisão (`PUT …/posicoes/{ordem}/cena`), escolhe outra cena da biblioteca (outro
 * produto só pelo plano, com aviso), conversa sobre uma posição ("Não aprovo" com alvo `posicao`) e
 * "Confirmar cenas" aprova o portão do texto. No avançado, o mesmo bloco troca as cenas depois do
 * texto (`avancado: true`), sem o "Confirmar cenas" (o avançado tem o "Aprovar texto" da 011).
 */
import { CheckCircle2, ImageOff, Library, Loader2, MessageSquare, Sparkles, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useCenasOpcoes } from "@/lib/estudio";
import type { Roteiro, RoteiroPosicao } from "@/lib/roteiros";
import { cn } from "@/lib/utils";
import {
  ajusteAberto,
  duracaoPosicao,
  duracaoTexto,
  nivelPossivel,
  reusoDescricao,
  reusoLabel,
  reusoTone,
  type RoteiroPosicaoReuso,
} from "@/lib/videoGuiado";
import type { CenaResumo } from "@sociman/contract";
import type { EtapaProps } from "../etapas/comum";
import { NaoAprovo } from "./NaoAprovo";

// Depois do texto, o avançado ainda troca as cenas (a API recusa onde não dá: 409 `etapa_errada`).
const SEM_TROCA = new Set(["rascunho", "planejando", "finalizando", "pronto"]);

export function ModalCenas({ roteiro: r, rodar, travado, avancado = false }: EtapaProps & { avancado?: boolean }) {
  const cenas = useCenasOpcoes(r.perfilId);
  const [busy, setBusy] = useState(false);
  const ajustando = ajusteAberto(r);
  const editavel = !travado && (avancado ? !SEM_TROCA.has(r.status) : r.status === "aguardando_texto");
  const porId = new Map((cenas.itens ?? []).map((c) => [c.id, c]));
  const custo = r.posicoes.filter((p) => p.reuso !== "total").length;

  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-card p-3 sm:p-4" aria-labelledby="modal-cenas-titulo" data-testid="modal-cenas">
      <div className="flex flex-col gap-1">
        <h3 id="modal-cenas-titulo" className="text-base font-semibold">
          Cenas do vídeo
        </h3>
        <p className="text-sm text-muted-foreground">
          {avancado
            ? "Troque a cena de uma posição. Depois do texto aprovado, a troca refaz os quadros e os clipes dela."
            : custo === 0
              ? "Todas as cenas vêm da biblioteca como estão: nada é gerado de novo."
              : "Confira de onde vem cada cena. Troque o que quiser e confirme para a IA gerar a narração."}
        </p>
      </div>

      <ol className="flex flex-col gap-3" aria-label="Cenas por posição">
        {r.posicoes.map((p) => (
          <PosicaoCena key={p.ordem} roteiro={r} posicao={p} rodar={rodar} editavel={editavel} ajustando={ajustando} avancado={avancado} resumo={porId.get(p.cena.id)} cenas={cenas} />
        ))}
      </ol>

      {!avancado && editavel && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/60 bg-warning/5 p-3" data-testid="aprovar-texto">
          <p className="min-w-0 flex-1 text-sm">{ajustando ? "Espere a IA terminar a cena pedida." : "Tudo certo? Confirme as cenas para a IA gerar a narração."}</p>
          <Button
            type="button"
            disabled={busy || ajustando}
            aria-busy={busy}
            onClick={async () => {
              setBusy(true);
              await rodar(() => api.roteiros.aprovar(r.id, r.version, "texto"), "Cenas confirmadas. A narração vem a seguir.");
              setBusy(false);
            }}
          >
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
            Confirmar cenas
          </Button>
        </div>
      )}
    </section>
  );
}

type CenasOpcoes = ReturnType<typeof useCenasOpcoes>;

function PosicaoCena({
  roteiro: r,
  posicao: p,
  rodar,
  editavel,
  ajustando,
  avancado,
  resumo,
  cenas,
}: {
  roteiro: Roteiro;
  posicao: RoteiroPosicao;
  rodar: EtapaProps["rodar"];
  editavel: boolean;
  ajustando: boolean;
  avancado: boolean;
  resumo: CenaResumo | undefined;
  cenas: CenasOpcoes;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [conversando, setConversando] = useState(false);
  const [escolhendo, setEscolhendo] = useState(false);
  const n = p.ordem + 1;
  const reuso: RoteiroPosicaoReuso = p.reuso ?? "nova";
  const thumb = p.quadros?.find((q) => q.imageUrl)?.imageUrl ?? p.cena.keyframeUrl ?? resumo?.thumbUrl ?? null;
  const usos = resumo?.usos ?? 0;
  const outroProduto = r.avisos.some((a) => a.code === "cena_outro_produto" && a.ordem === p.ordem);
  const livre = editavel && !ajustando && busy === null;

  async function definir(novo: RoteiroPosicaoReuso, cenaId: string | null, ok: string) {
    setBusy(novo);
    const feito = await rodar(() => api.roteiros.definirCena(r.id, p.ordem, { reuso: novo, cenaId, avancado, version: r.version }), ok);
    setBusy(null);
    // com erro, o diálogo também fecha: o aviso da API aparece na página
    setEscolhendo(false);
    return feito;
  }

  return (
    <li className="flex flex-col gap-3 rounded-lg border p-3" data-testid={`modal-cena-${n}`} data-reuso={reuso}>
      <div className="flex min-w-0 gap-3">
        <div className="aspect-[9/16] w-16 shrink-0 overflow-hidden rounded-md border bg-muted sm:w-20">
          {thumb ? (
            <img src={thumb} alt={`Cena ${n}: ${p.cena.nome}`} className="size-full object-cover" />
          ) : (
            <span className="flex size-full items-center justify-center text-muted-foreground">
              <ImageOff className="size-4" aria-hidden="true" />
            </span>
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <h4 className="text-sm font-semibold">Cena {n}</h4>
            <Badge className={reusoTone[reuso]} data-testid="nivel">
              {reusoLabel[reuso]}
            </Badge>
            <span className="text-xs text-muted-foreground tabular-nums">{duracaoTexto(duracaoPosicao(r, p))}</span>
          </div>
          <p className="text-sm break-words">
            <Link to={`/app/cenas/${p.cena.id}`} className="underline-offset-2 hover:underline">
              {p.cena.nome}
            </Link>
          </p>
          <p className="text-xs text-muted-foreground" data-testid="usos">
            {usos === 0 ? "Ainda não foi usada em nenhum vídeo." : `Já usada em ${usos} ${usos === 1 ? "vídeo" : "vídeos"}.`}
          </p>
          <p className="text-xs text-muted-foreground">{reusoDescricao[reuso]}</p>
          {p.motivo && (
            <p className="text-sm break-words" data-testid="motivo">
              <span className="text-muted-foreground">Motivo: </span>
              {p.motivo}
            </p>
          )}
          {outroProduto && (
            <p className="flex items-start gap-1.5 text-xs text-warning-foreground" role="status" data-testid="aviso-outro-produto">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
              Veio de uma cena de outro produto: confira os quadros.
            </p>
          )}
        </div>
      </div>

      {p.geracoesAbertas.some((g) => g.passo === "roteiro.ajuste") && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />A IA está criando a cena…
        </p>
      )}

      {editavel && (
        <div className="flex flex-wrap gap-2">
          {reuso !== "nova" && (
            <Button type="button" variant="outline" size="sm" disabled={!livre} aria-busy={busy === "nova"} onClick={() => void definir("nova", null, `A IA vai criar uma cena nova para a posição ${n}.`)}>
              {busy === "nova" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
              Criar nova
            </Button>
          )}
          <Button type="button" variant="outline" size="sm" disabled={!livre} onClick={() => setEscolhendo(true)}>
            <Library aria-hidden="true" />
            Escolher da biblioteca
          </Button>
          <Button type="button" variant={conversando ? "secondary" : "ghost"} size="sm" disabled={!editavel} aria-expanded={conversando} onClick={() => setConversando((v) => !v)}>
            <MessageSquare aria-hidden="true" />
            Conversar sobre esta cena
          </Button>
        </div>
      )}

      {conversando && editavel && <NaoAprovo roteiro={r} alvo={{ tipo: "posicao", ordem: p.ordem }} rotulo={`a cena ${n}`} onFechar={() => setConversando(false)} />}

      <Biblioteca
        aberto={escolhendo}
        onFechar={() => setEscolhendo(false)}
        roteiro={r}
        posicao={p}
        cenas={cenas}
        busy={busy}
        onEscolher={(c, nivel) =>
          definir(nivel, c.id, nivel === "total" ? `Cena ${n}: ${c.nome}, sem custo.` : `Cena ${n}: o plano de ${c.nome}; as imagens são refeitas.`)
        }
      />
    </li>
  );
}

function Biblioteca({
  aberto,
  onFechar,
  roteiro: r,
  posicao: p,
  cenas,
  busy,
  onEscolher,
}: {
  aberto: boolean;
  onFechar: () => void;
  roteiro: Roteiro;
  posicao: RoteiroPosicao;
  cenas: CenasOpcoes;
  busy: string | null;
  onEscolher: (c: CenaResumo, nivel: "total" | "plano") => Promise<unknown>;
}) {
  const [busca, setBusca] = useState("");
  const n = p.ordem + 1;
  const q = busca.trim().toLowerCase();
  const itens = (cenas.itens ?? []).filter((c) => !c.arquivada && c.id !== p.cena.id && (q === "" || c.nome.toLowerCase().includes(q)));

  const escolher = (c: CenaResumo, nivel: "total" | "plano") => onEscolher(c, nivel);

  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && onFechar()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl" data-testid={`biblioteca-cena-${n}`}>
        <DialogHeader>
          <DialogTitle>Outra cena para a posição {n}</DialogTitle>
          <DialogDescription>
            "Sem custo" usa a cena como está (mesmo avatar, cenário e produto). "Refaz as imagens" usa só a ação e o movimento, numa cena nova derivada.
          </DialogDescription>
        </DialogHeader>
        <Input type="search" aria-label="Buscar cena pelo nome" placeholder="Buscar pelo nome" value={busca} onChange={(e) => setBusca(e.target.value)} />
        {cenas.isPending && <p className="text-sm text-muted-foreground">Carregando…</p>}
        {cenas.isError && <ApiErrorAlert error={cenas.error} />}
        {cenas.data && itens.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma cena na biblioteca.</p>}
        <ul className="flex flex-col gap-2" aria-label="Cenas da biblioteca">
          {itens.map((c) => {
            const nivel = nivelPossivel(r, c);
            return (
              <li key={c.id} className="flex min-w-0 gap-3 rounded-lg border p-2" data-testid="opcao-cena">
                <div className="aspect-[9/16] w-12 shrink-0 overflow-hidden rounded border bg-muted">
                  {c.thumbUrl && <img src={c.thumbUrl} alt="" className="size-full object-cover" />}
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <p className="text-sm font-medium break-words">{c.nome}</p>
                  <p className="text-xs break-words text-muted-foreground">
                    {[c.perfilNome ?? "Sem perfil base", c.avatar?.nome, c.produtoNome, c.usos > 0 ? `usada em ${c.usos}` : null].filter(Boolean).join(" · ")}
                  </p>
                  {nivel.diferencas.length > 0 && <p className="text-xs text-muted-foreground">Diferente: {nivel.diferencas.join(", ")}.</p>}
                  {nivel.outroProduto && (
                    <p className="flex items-start gap-1.5 text-xs text-warning-foreground" data-testid="aviso-outro-produto">
                      <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
                      Mostra outro produto: só pelo plano, e confira os quadros.
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    {nivel.podeTotal && (
                      <Button type="button" size="xs" disabled={busy !== null} aria-busy={busy === "total"} onClick={() => void escolher(c, "total")} aria-label={`Usar ${c.nome} sem custo`}>
                        Sem custo
                      </Button>
                    )}
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      className={cn(nivel.outroProduto && "border-warning")}
                      disabled={busy !== null}
                      aria-busy={busy === "plano"}
                      onClick={() => void escolher(c, "plano")}
                      aria-label={`Usar o plano de ${c.nome} (refaz as imagens)`}
                    >
                      Refaz as imagens
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
