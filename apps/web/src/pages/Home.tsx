import type { Platform, SecurityEvent } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CircleCheck, CircleX, LayoutGrid, Users, Video } from "lucide-react";
import { Link } from "react-router-dom";
import { HeaderCard, MetricCard } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeading } from "../components/PageHeading";
import { cn } from "@/lib/utils";
import { api } from "../lib/api";
import { useAuth } from "../lib/authStore";
import { platformLabel } from "../lib/perfis";
import { actorText, eventTypeLabel } from "../lib/securityEvents";

const RECENT_EVENTS = 8;
const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

// /app: métricas com os números reais que a API já expõe (FR-006) e, para o dono, os eventos de
// segurança mais recentes. Sem rota nova: soma a partir das listas de perfis e usuários.
export default function Home() {
  const isOwner = useAuth((s) => s.user?.role === "dono");

  // Mesma chave da lista de perfis sem filtros: reaproveita o cache.
  const perfis = useQuery({
    queryKey: ["perfis", { archived: false }],
    queryFn: () => api.perfis.list({ archived: false }),
  });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users.list(), enabled: isOwner });
  // Chave própria: a tela Segurança usa useInfiniteQuery (outro formato de cache).
  const events = useQuery({
    queryKey: ["security-events", "recentes"],
    queryFn: () => api.securityEvents.list({}),
    enabled: isOwner,
  });

  const perfisItems = perfis.data?.items ?? [];
  const perfisAtivos = perfisItems.filter((p) => p.status === "ativo").length;
  const emPreparacao = perfisItems.filter((p) => p.status === "em_preparacao").length;

  // `platforms` traz as plataformas das contas ativas; o perfil tem no máximo uma ativa por plataforma.
  const porPlataforma = new Map<Platform, number>();
  for (const perfil of perfisItems) {
    for (const platform of perfil.platforms) porPlataforma.set(platform, (porPlataforma.get(platform) ?? 0) + 1);
  }
  const contasAtivas = [...porPlataforma.values()].reduce((a, b) => a + b, 0);
  const contasResumo = [...porPlataforma.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([platform, n]) => `${platformLabel[platform]} ${n}`)
    .join(" · ");

  const userItems = users.data?.items ?? [];
  const ativos = userItems.filter((u) => u.isActive);
  const donos = ativos.filter((u) => u.role === "dono").length;
  const membros = ativos.length - donos;

  return (
    <div className="space-y-8">
      <PageHeading title="Início" description="Resumo da agência: perfis, contas e acessos." />

      {(perfis.isError || users.isError) && (
        <Alert variant="destructive">
          <AlertDescription>Não foi possível carregar alguns números do painel.</AlertDescription>
        </Alert>
      )}

      <div className={cn("grid gap-x-6 gap-y-10 pt-6 sm:grid-cols-2", isOwner && "xl:grid-cols-3")}>
        <MetricCard
          icon={LayoutGrid}
          label="Perfis ativos"
          value={perfisAtivos}
          tone="dark"
          loading={perfis.isPending}
          footer={
            perfis.data && (
              <>
                <strong className="text-foreground">{perfisItems.length}</strong> no total ·{" "}
                {emPreparacao} em preparação
              </>
            )
          }
        />
        <MetricCard
          icon={Video}
          label="Contas ativas"
          value={contasAtivas}
          tone="primary"
          loading={perfis.isPending}
          footer={perfis.data && (contasResumo || "Nenhuma conta ativa ainda")}
        />
        {isOwner && (
          <MetricCard
            icon={Users}
            label="Usuários ativos"
            value={ativos.length}
            tone="success"
            loading={users.isPending}
            footer={
              users.data && `${donos} ${donos === 1 ? "dono" : "donos"} · ${membros} ${membros === 1 ? "membro" : "membros"}`
            }
          />
        )}
      </div>

      {isOwner && (
        <HeaderCard
          title="Eventos recentes"
          description="Logins, trocas de senha e mudanças de acesso"
          tone="dark"
          className="max-w-3xl"
          actions={
            <Button asChild variant="secondary" size="sm">
              <Link to="/app/seguranca">
                Ver todos
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          }
        >
          {events.isError ? (
            <Alert variant="destructive">
              <AlertDescription>Não foi possível carregar os eventos.</AlertDescription>
            </Alert>
          ) : events.isPending ? (
            <div className="space-y-4 py-2">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : events.data.items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Nenhum evento ainda.</p>
          ) : (
            <Timeline events={events.data.items.slice(0, RECENT_EVENTS)} />
          )}
        </HeaderCard>
      )}
    </div>
  );
}

// Linha do tempo: ícone circular (verde = ok, vermelho = negado) ligado por uma linha vertical.
function Timeline({ events }: { events: SecurityEvent[] }) {
  return (
    <ol className="pt-2">
      {events.map((event, i) => {
        const ok = event.outcome === "ok";
        const Icon = ok ? CircleCheck : CircleX;
        const last = i === events.length - 1;
        return (
          <li key={event.id} className="relative flex gap-4 pb-5 last:pb-0">
            {!last && <span aria-hidden="true" className="absolute top-8 bottom-0 left-4 w-px -translate-x-1/2 bg-border" />}
            <span
              className={cn(
                "grid size-8 shrink-0 place-items-center rounded-full",
                ok ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive",
              )}
            >
              <Icon className="size-4" aria-label={ok ? "Ok" : "Negado"} />
            </span>
            <div className="min-w-0 pt-1">
              <p className="text-sm font-semibold">{eventTypeLabel[event.type] ?? event.type}</p>
              <p className="truncate text-xs text-muted-foreground">
                <time dateTime={event.occurredAt}>{dateFormat.format(new Date(event.occurredAt))}</time>
                {" · "}
                {actorText(event)}
                {event.subjectName && event.subjectName !== event.actorName && ` → ${event.subjectName}`}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
