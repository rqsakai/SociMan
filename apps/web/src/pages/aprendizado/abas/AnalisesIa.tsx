/*
 * Aba "Análises da IA" (spec 023, US2; FR-030 a FR-033). O dono pede (com o custo estimado antes) e a
 * trilha do agendador executa: pendente → processando → pronta | erro, com polling de 5 s. Cada
 * hipótese cita os posts (link), o n, o contraste com os piores e o grau "a conferir", nunca
 * "comprovado". O dono pode transformar uma hipótese em recomendação de padrão (gancho, duração ou
 * horário), que entra na aba Recomendações como aberta. O membro vê as análises prontas, sem custo e
 * sem pedir.
 */
import { CircleAlert, ListPlus, Loader2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { PedidoAnalise } from "@/components/aprendizado/PedidoAnalise";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  analiseEmCurso,
  aprendizadoPath,
  estadoAnaliseLabel,
  formatUsd,
  medidaAprendizadoLabel,
  tipoRecomendacaoLabel,
  TIPOS_PADRAO,
  useAnalisesIa,
  useInvalidarAprendizado,
  type AprendizadoAnaliseIa,
  type AprendizadoHipotese,
  type MedidaAprendizado,
  type TipoPadrao,
} from "@/lib/aprendizado";
import { useEhDono } from "@/lib/conteudos";
import { formatNumero } from "@/lib/metricas";
import { formatDateTime } from "@/lib/tz";
import type { AbaProps } from "../Aprendizado";

const linkVideo = (id: string) => `/app/metricas/videos/${id}`;

const erroLabel: Record<string, string> = {
  hd_indisponivel: "O HD de dados não estava montado: a análise com quadros não pôde rodar. Peça de novo sem quadros ou com o HD montado.",
  sem_posts: "Não havia posts entregues para analisar.",
};

export function AnalisesIa({ perfil, contas, estado }: AbaProps) {
  const dono = useEhDono();
  const lista = useAnalisesIa(perfil.id);
  const invalidar = useInvalidarAprendizado();
  const emCurso = lista.data?.items.some(analiseEmCurso) ?? false;
  const rotuloConta = (id: string | null | undefined) => {
    const c = id ? contas.find((x) => x.id === id) : null;
    return c ? `@${c.handle.replace(/^@/, "")}` : "perfil inteiro";
  };

  return (
    <div className="flex min-w-0 flex-col gap-6">
      {dono && (
        <HeaderCard title="Pedir análise dos melhores" description="A IA compara os melhores posts com os piores que também saíram do zero e propõe hipóteses a conferir.">
          <div className="pb-2">
            <PedidoAnalise perfilId={perfil.id} contaId={estado.filtro.contaId} medida={estado.filtro.medida} bloqueado={emCurso} onPedido={() => invalidar(perfil.id)} />
          </div>
        </HeaderCard>
      )}
      <HeaderCard title="Análises" tone="dark" description="Guardadas: reabrir não chama a IA de novo.">
        <div className="pb-2">
          {lista.isError ? (
            <ApiErrorAlert error={lista.error} />
          ) : lista.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : lista.data.items.length === 0 ? (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
              Nenhuma análise da IA ainda.{dono ? " Peça uma acima." : ""}
            </p>
          ) : (
            <ul className="flex flex-col gap-4" aria-label="Análises da IA">
              {lista.data.items.map((a) => (
                <AnaliseItem key={a.id} a={a} contaRotulo={rotuloConta(a.contaId)} dono={dono} perfilId={perfil.id} onMudou={() => invalidar(perfil.id)} />
              ))}
            </ul>
          )}
        </div>
      </HeaderCard>
    </div>
  );
}

function AnaliseItem({ a, contaRotulo, dono, perfilId, onMudou }: { a: AprendizadoAnaliseIa; contaRotulo: string; dono: boolean; perfilId: string; onMudou: () => Promise<unknown> }) {
  // o título curto do post (a API manda os dos melhores e comparáveis, sem as anônimas); sem ele, o
  // grupo do post ("melhor 2", "comparável 1")
  const titulos = new Map((a.posts ?? []).map((p) => [p.videoId, p.tituloCurto]));
  const posts = new Map<string, string>([
    ...a.melhores.map((id, i) => [id, titulos.get(id) || `melhor ${i + 1}`] as const),
    ...a.comparaveis.map((id, i) => [id, titulos.get(id) || `comparável ${i + 1}`] as const),
  ]);
  return (
    <li className="flex flex-col gap-3 rounded-lg border p-3" aria-label={`Análise de ${formatDateTime(a.createdAt)}`} data-estado={a.estado}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant={a.estado === "pronta" ? "default" : a.estado === "erro" ? "destructive" : "secondary"}>
            {analiseEmCurso(a) && <Loader2 className="animate-spin" aria-hidden="true" />}
            {estadoAnaliseLabel[a.estado]}
          </Badge>
          <span>
            {formatNumero(a.n)} melhores · {contaRotulo} · {medidaAprendizadoLabel[a.medida as MedidaAprendizado] ?? a.medida}
            {a.comQuadros ? " · com quadros" : " · só texto"}
          </span>
        </p>
        <p className="text-xs text-muted-foreground">
          {formatDateTime(a.createdAt)}
          {a.custoUsd !== null && a.custoUsd !== undefined ? ` · custo ${formatUsd(a.custoUsd)}` : a.custoEstimadoUsd !== null && a.custoEstimadoUsd !== undefined ? ` · estimado ${formatUsd(a.custoEstimadoUsd)}` : ""}
        </p>
      </div>
      {a.videosSemArquivo > 0 && <p className="text-xs text-muted-foreground">{formatNumero(a.videosSemArquivo)} vídeos sem arquivo entraram só com texto.</p>}
      {a.estado === "erro" && (
        <p className="flex items-start gap-2 text-sm text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {(a.erroCode && erroLabel[a.erroCode]) ?? `A análise falhou (${a.erroCode ?? "erro"}). Ela fica no registro do assistente e pode ser pedida de novo.`}
        </p>
      )}
      {a.estado === "pronta" && (a.hipoteses?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">A IA não propôs hipóteses para este conjunto.</p>}
      {a.estado === "pronta" && a.hipoteses && a.hipoteses.length > 0 && (
        <ol className="flex flex-col gap-3" aria-label="Hipóteses">
          {a.hipoteses.map((h, i) => (
            <Hipotese key={i} h={h} indice={i} analiseId={a.id} posts={posts} dono={dono} perfilId={perfilId} onMudou={onMudou} />
          ))}
        </ol>
      )}
    </li>
  );
}

function Hipotese({
  h,
  indice,
  analiseId,
  posts,
  dono,
  perfilId,
  onMudou,
}: {
  h: AprendizadoHipotese;
  indice: number;
  analiseId: string;
  posts: Map<string, string>;
  dono: boolean;
  perfilId: string;
  onMudou: () => Promise<unknown>;
}) {
  const navigate = useNavigate();
  const [aberto, setAberto] = useState(false);
  const [tipo, setTipo] = useState<TipoPadrao>("padrao_gancho");
  const [texto, setTexto] = useState(h.texto.slice(0, 120));
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);

  async function recomendar() {
    setBusy(true);
    setErro(null);
    try {
      await api.aprendizado.analises.recomendarHipotese(analiseId, indice, { tipo, texto: texto.trim() });
      toast.success("A hipótese virou uma recomendação aberta.", { action: { label: "Ver", onClick: () => navigate(aprendizadoPath(perfilId, "recomendacoes")) } });
      setAberto(false);
      await onMudou();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-col gap-1.5 rounded-md bg-muted/40 p-3" data-hipotese={indice}>
      <p className="text-sm">
        <span className="font-medium">{h.texto}</span> <Badge variant="outline">a conferir</Badge>
      </p>
      {h.contraste && <p className="text-xs text-muted-foreground">Contraste com os piores: {h.contraste}</p>}
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="text-muted-foreground">n = {formatNumero(h.n)} · posts:</span>
        {h.postsIds.map((id) => (
          <Link key={id} to={linkVideo(id)} className="underline-offset-2 hover:underline">
            {posts.get(id) ?? "post"}
          </Link>
        ))}
      </p>
      {dono && !aberto && (
        <div>
          <Button type="button" size="sm" variant="outline" onClick={() => setAberto(true)}>
            <ListPlus aria-hidden="true" />
            Transformar em recomendação
          </Button>
        </div>
      )}
      {dono && aberto && (
        <div className="flex flex-col gap-2 rounded-md border bg-card p-2" role="group" aria-label="Transformar em recomendação">
          <div className="grid gap-2 sm:grid-cols-[12rem_1fr]">
            <Field label="Tipo de padrão">
              {({ id }) => (
                <NativeSelect id={id} value={tipo} onChange={(e) => setTipo(e.target.value as TipoPadrao)}>
                  {TIPOS_PADRAO.map((t) => (
                    <option key={t} value={t}>
                      {tipoRecomendacaoLabel[t]}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Texto curto do padrão" hint="Até 120 caracteres; é o que o assistente lê.">
              {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} maxLength={120} value={texto} onChange={(e) => setTexto(e.target.value)} />}
            </Field>
          </div>
          {erro !== null && <ApiErrorAlert error={erro} />}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" disabled={busy || !texto.trim()} aria-busy={busy} onClick={() => void recomendar()}>
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              Criar recomendação
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setAberto(false)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
