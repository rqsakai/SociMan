/*
 * Aba "Recomendações" (spec 023, US3 e US6; FR-034 a FR-039, FR-053).
 *
 * - Abertas: calculadas na leitura por regras fixas (FR-035) ou vindas de uma hipótese da IA; o dono
 *   aceita ou rejeita. Nenhuma nasce de amostra pequena, "não separável", "puxado por 1 post" ou conta
 *   travada (a API já filtra).
 * - Decididas: aceitas e rejeitadas, com motivo, autor e data, "superada" quando o tema foi juntado ou
 *   arquivado, e a reversão (só dono). Reverter um "fixar" não tira a hashtag do guia: o link leva lá.
 * - Preferências: o que vale hoje (perfil + conta), editável e com histórico; e os interruptores
 *   "classificação automática" e "usar desempenho no assistente" (só no perfil).
 * Aceitar nunca agenda, aprova nem publica (princípio I): a janela de horário vira só uma dica.
 */
import { History, Loader2, Undo2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { CartaoRecomendacao } from "@/components/aprendizado/CartaoRecomendacao";
import { formatarValor, HistoricoDialog } from "@/components/aprendizado/HistoricoDialog";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import {
  tipoRecomendacaoLabel,
  useInvalidarAprendizado,
  usePreferencias,
  usePreferenciasVersions,
  useRecomendacoes,
  useTemas,
  type AprendizadoDecisao,
  type AprendizadoPreferencias,
} from "@/lib/aprendizado";
import { useEhDono } from "@/lib/conteudos";
import { guiaContaPath, guiaPerfilPath } from "@/lib/guia";
import { formatNumero } from "@/lib/metricas";
import { formatDateTime } from "@/lib/tz";
import type { AbaProps } from "../Aprendizado";

const estadoDecisaoLabel: Record<string, string> = { aceita: "Aceita", rejeitada: "Rejeitada", aberta: "Aberta" };

export function Recomendacoes({ perfil, contas, estado }: AbaProps) {
  const dono = useEhDono();
  const { filtro } = estado;
  const recs = useRecomendacoes(perfil.id, filtro);
  const temas = useTemas(perfil.id, true);
  const nomeTema = (id: string) => temas.data?.items.find((t) => t.id === id)?.nome ?? "tema arquivado";
  const invalidar = useInvalidarAprendizado();
  const atualizar = () => invalidar(perfil.id);
  const rotuloConta = (id: string | null | undefined) => {
    const c = id ? contas.find((x) => x.id === id) : null;
    return c ? `@${c.handle.replace(/^@/, "")}` : null;
  };

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <HeaderCard
        title="Recomendações abertas"
        description={recs.data ? `${formatNumero(recs.data.abertas.length)} para decidir` : "Carregando…"}
      >
        <div className="pb-2">
          {recs.isError ? (
            <ApiErrorAlert error={recs.error} />
          ) : recs.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : recs.data.abertas.length === 0 ? (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
              Nenhuma recomendação agora. Elas só aparecem com confiança moderada ou forte, separáveis de outros fatores e fora de conta com distribuição travada.
            </p>
          ) : (
            <ul className="flex flex-col gap-3" aria-label="Recomendações abertas">
              {recs.data.abertas.map((r) => (
                <CartaoRecomendacao key={r.chave} rec={r} perfilId={perfil.id} medida={filtro.medida} contaRotulo={rotuloConta(r.escopo.contaId)} dono={dono} onDecidido={atualizar} />
              ))}
            </ul>
          )}
        </div>
      </HeaderCard>

      {recs.data && recs.data.decididas.length > 0 && (
        <HeaderCard title="Decididas" tone="dark" description="O que o dono já aceitou ou rejeitou. Reverter fica no histórico.">
          <ul className="divide-y pb-2" aria-label="Recomendações decididas">
            {recs.data.decididas.map((d) => (
              <Decidida key={d.id} d={d} perfilId={perfil.id} dono={dono} nomeTema={nomeTema} onMudou={atualizar} />
            ))}
          </ul>
        </HeaderCard>
      )}

      <Preferencias perfilId={perfil.id} contaId={filtro.contaId} contaRotulo={rotuloConta(filtro.contaId)} dono={dono} onMudou={atualizar} />
    </div>
  );
}

function Decidida({ d, perfilId, dono, nomeTema, onMudou }: { d: AprendizadoDecisao; perfilId: string; dono: boolean; nomeTema: (id: string) => string; onMudou: () => Promise<unknown> }) {
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  // a chave é "<tipo>:<escopo>[:<contaId>]:<alvo>"; tema pelo nome, hashtag como está, padrão pelo texto
  const ultimo = d.chave.split(":").pop() ?? "";
  const alvo = d.texto ?? (d.tipo.startsWith("tema_") ? nomeTema(ultimo) : ultimo);
  const linkGuia = d.tipo === "hashtag_fixar" ? (d.escopo.tipo === "conta" && d.escopo.contaId ? guiaContaPath(d.escopo.contaId) : guiaPerfilPath(perfilId)) : null;

  async function reverter() {
    setBusy(true);
    setErro(null);
    try {
      const out = await api.aprendizado.reverterDecisao(d.id, d.version);
      if (out.aviso) toast.info(out.aviso, { duration: 10_000 });
      else toast.success("Decisão revertida.");
      await onMudou();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-col gap-1 py-3" aria-label={`Decisão ${tipoRecomendacaoLabel[d.tipo] ?? d.tipo}: ${alvo}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant={d.estado === "aceita" ? "default" : "outline"}>{estadoDecisaoLabel[d.estado] ?? d.estado}</Badge>
            <span className="font-medium break-words">
              {tipoRecomendacaoLabel[d.tipo] ?? d.tipo}: {alvo}
            </span>
            {d.superada && <Badge variant="outline">superada</Badge>}
            {d.revertidaEm && <Badge variant="outline">revertida em {formatDateTime(d.revertidaEm)}</Badge>}
          </p>
          {d.motivo && <p className="text-xs text-muted-foreground">Motivo: {d.motivo}</p>}
          <p className="text-xs text-muted-foreground">
            {d.decididoPor?.name ?? "dono"}
            {d.decididoEm ? ` · ${formatDateTime(d.decididoEm)}` : ""}
          </p>
          {linkGuia && d.estado === "aceita" && (
            <Link to={linkGuia} className="text-xs underline">
              Ver no guia de comunicação
            </Link>
          )}
        </div>
        {dono && d.estado !== "aberta" && !d.revertidaEm && (
          <ConfirmButton
            size="sm"
            label="Reverter"
            icon={Undo2}
            busy={busy}
            title="Reverter esta decisão?"
            description={
              linkGuia && d.estado === "aceita"
                ? "A decisão volta ao estado anterior. A hashtag fixada continua no guia: para tirá-la, reverta o guia de comunicação."
                : "A decisão e as preferências criadas por ela voltam ao estado anterior. A reversão fica no histórico."
            }
            onConfirm={reverter}
          />
        )}
      </div>
      {erro !== null && <ApiErrorAlert error={erro} onReload={() => void onMudou()} />}
    </li>
  );
}

// ---------------------------------------------------------------------------------------------
// Preferências

const prefLabels: Record<string, string> = {
  temas: "Temas",
  hashtags_evitar: "Hashtags a evitar",
  padroes: "Padrões",
  classificacao_auto: "Classificação automática",
  usar_desempenho: "Usar desempenho no assistente",
};

function Preferencias({ perfilId, contaId, contaRotulo, dono, onMudou }: { perfilId: string; contaId?: string; contaRotulo: string | null; dono: boolean; onMudou: () => Promise<unknown> }) {
  const prefs = usePreferencias(perfilId, contaId);
  const temas = useTemas(perfilId, true);
  const [historico, setHistorico] = useState<"perfil" | "conta" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<unknown>(null);
  const nomeTema = (id: string) => temas.data?.items.find((t) => t.id === id)?.nome ?? "tema arquivado";

  async function patch(nivel: "perfil" | "conta", atual: AprendizadoPreferencias, body: Record<string, unknown>, chave: string, ok: string) {
    setBusy(chave);
    setErro(null);
    try {
      await api.aprendizado.preferencias.patch(perfilId, { version: atual.version, ...body }, nivel === "conta" ? contaId : undefined);
      toast.success(ok);
      await onMudou();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(null);
    }
  }

  if (prefs.isError) return <ApiErrorAlert error={prefs.error} />;
  if (prefs.isPending) return <Skeleton className="h-40 w-full" />;
  const { perfil: pp, conta: pc } = prefs.data;
  const niveis: { nivel: "perfil" | "conta"; p: AprendizadoPreferencias; rotulo: string }[] = [
    { nivel: "perfil", p: pp, rotulo: "Perfil" },
    ...(contaId && pc ? [{ nivel: "conta" as const, p: pc, rotulo: contaRotulo ?? "Conta" }] : []),
  ];

  return (
    <HeaderCard title="Preferências" tone="dark" description="O que o dono aceitou e vale hoje. Orienta o Descobrir, o Mercado e o assistente de textos.">
      <div className="flex flex-col gap-5 pb-2">
        <div className="flex flex-col gap-3 rounded-lg bg-muted/40 p-3" role="group" aria-label="Controles do perfil">
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>
              <span className="font-medium">Classificação automática</span>
              <span className="block text-xs text-muted-foreground">O agendador classifica os posts novos com a IA (até 50 por dia). Pausar não apaga nada.</span>
            </span>
            <Switch
              aria-label="Classificação automática"
              checked={pp.classificacaoAuto}
              disabled={!dono || busy !== null}
              onCheckedChange={(on) => void patch("perfil", pp, { classificacaoAuto: on }, "auto", on ? "Classificação automática ligada." : "Classificação automática pausada.")}
            />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>
              <span className="font-medium">Usar desempenho no assistente</span>
              <span className="block text-xs text-muted-foreground">Os textos de postagem recebem o que rendeu (preferências e até 3 exemplos).</span>
            </span>
            <Switch
              aria-label="Usar desempenho no assistente"
              checked={pp.usarDesempenho}
              disabled={!dono || busy !== null}
              onCheckedChange={(on) => void patch("perfil", pp, { usarDesempenho: on }, "desempenho", on ? "O assistente volta a usar o desempenho." : "O assistente deixa de usar o desempenho.")}
            />
          </label>
        </div>

        {niveis.map(({ nivel, p, rotulo }) => {
          const temasPref = Object.entries(p.temas ?? {});
          const vazio = temasPref.length === 0 && p.hashtagsEvitar.length === 0 && p.padroes.length === 0;
          return (
            <section key={nivel} aria-label={`Preferências: ${rotulo}`} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">
                  {rotulo} <span className="font-normal text-muted-foreground">· versão {p.version}</span>
                </h3>
                <Button type="button" size="sm" variant="ghost" onClick={() => setHistorico(nivel)} aria-label={`Histórico das preferências: ${rotulo}`}>
                  <History aria-hidden="true" />
                  Histórico
                </Button>
              </div>
              {vazio ? (
                <p className="text-sm text-muted-foreground">Nenhuma preferência ainda.</p>
              ) : (
                <ul className="flex flex-wrap gap-2" aria-label={`Itens das preferências: ${rotulo}`}>
                  {temasPref.map(([temaId, v]) => (
                    <Item
                      key={temaId}
                      texto={`${v === "ampliar" ? "Ampliar" : "Cortar"} tema ${nomeTema(temaId)}`}
                      dono={dono}
                      busy={busy === `tema:${temaId}`}
                      onRemover={() => {
                        const t = { ...p.temas };
                        delete t[temaId];
                        void patch(nivel, p, { temas: t }, `tema:${temaId}`, `Tema ${nomeTema(temaId)} voltou a neutro.`);
                      }}
                    />
                  ))}
                  {p.hashtagsEvitar.map((h) => (
                    <Item
                      key={h}
                      texto={`Evitar ${h}`}
                      dono={dono}
                      busy={busy === `h:${h}`}
                      onRemover={() => void patch(nivel, p, { hashtagsEvitar: p.hashtagsEvitar.filter((x) => x !== h) }, `h:${h}`, `${h} saiu das evitadas.`)}
                    />
                  ))}
                  {p.padroes.map((pd, i) => (
                    <Item
                      key={`${pd.tipo}:${i}`}
                      texto={`${pd.tipo === "gancho" ? "Gancho" : pd.tipo === "duracao" ? "Duração" : "Janela"}: ${pd.texto}`}
                      dono={dono}
                      busy={busy === `p:${i}`}
                      onRemover={() => void patch(nivel, p, { padroes: p.padroes.filter((_, j) => j !== i) }, `p:${i}`, "Padrão removido.")}
                    />
                  ))}
                </ul>
              )}
            </section>
          );
        })}
        {erro !== null && <ApiErrorAlert error={erro} onReload={() => void onMudou()} />}
      </div>
      {historico && (
        <HistoricoPreferencias
          perfilId={perfilId}
          contaId={historico === "conta" ? contaId : undefined}
          version={historico === "conta" ? (pc?.version ?? 0) : pp.version}
          nomeTema={nomeTema}
          titulo={historico === "conta" ? `Histórico das preferências de ${contaRotulo ?? "conta"}` : "Histórico das preferências do perfil"}
          onFechar={() => setHistorico(null)}
          onMudou={onMudou}
        />
      )}
    </HeaderCard>
  );
}

function Item({ texto, dono, busy, onRemover }: { texto: string; dono: boolean; busy: boolean; onRemover: () => void }) {
  return (
    <li className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-sm">
      {texto}
      {dono && (
        <button type="button" className="rounded-full p-0.5 hover:bg-background" aria-label={`Remover: ${texto}`} disabled={busy} onClick={onRemover}>
          {busy ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : <X className="size-3.5" aria-hidden="true" />}
        </button>
      )}
    </li>
  );
}

function HistoricoPreferencias({
  perfilId,
  contaId,
  version,
  nomeTema,
  titulo,
  onFechar,
  onMudou,
}: {
  perfilId: string;
  contaId?: string;
  version: number;
  nomeTema: (id: string) => string;
  titulo: string;
  onFechar: () => void;
  onMudou: () => Promise<unknown>;
}) {
  const versions = usePreferenciasVersions(perfilId, contaId);
  return (
    <HistoricoDialog
      aberto
      onFechar={onFechar}
      titulo={titulo}
      versions={versions.data?.items}
      carregando={versions.isPending}
      erro={versions.error}
      labels={prefLabels}
      formatValue={(campo, v) => {
        if (campo === "temas" && v && typeof v === "object") {
          const e = Object.entries(v as Record<string, string>);
          return e.length ? e.map(([id, x]) => `${x} ${nomeTema(id)}`).join(", ") : "—";
        }
        if (campo === "padroes" && Array.isArray(v)) return v.length ? v.map((p) => (p as { texto?: string }).texto ?? "").join("; ") : "—";
        return formatarValor(v);
      }}
      onRevert={async (toVersion) => {
        await api.aprendizado.preferencias.revert(perfilId, version, toVersion, contaId);
        await Promise.all([onMudou(), versions.refetch()]);
      }}
    />
  );
}
