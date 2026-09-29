// Vitrine dos componentes da base de UI (spec 005). SÓ EM DEV (rota /app/_showcase registrada
// com import.meta.env.DEV no App.tsx). Dados fictícios; não chama a API.
// /app/_showcase          → AppShell + MetricCards + HeaderCard + DataTable (cliente e externo)
// /app/_showcase?auth=1   → AuthShell de exemplo
import { Clock, LayoutGrid, Plus, ShieldCheck, Users, Video } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { AppShell, AuthShell, HeaderCard, MetricCard, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

interface PerfilFicticio {
  id: string;
  nome: string;
  nicho: string;
  plataformas: number;
  status: "ativo" | "arquivado";
  criadoEm: Date;
}

const NICHOS = ["Podcasts", "Futebol", "Finanças", "Culinária", "Games", "Ciência"];
const PERFIS: PerfilFicticio[] = Array.from({ length: 32 }, (_, i) => ({
  id: `p${i + 1}`,
  nome: `Cortes ${["Alfa", "Beta", "Gama", "Delta", "Épsilon", "Zeta", "Eta", "Teta"][i % 8]} ${i + 1}`,
  nicho: NICHOS[i % NICHOS.length]!,
  plataformas: (i % 3) + 1,
  status: i % 5 === 0 ? "arquivado" : "ativo",
  criadoEm: new Date(2026, 8, 28 - i),
}));

const col = dataTableColumns<PerfilFicticio>();
const columns = col.columns([
  col.accessor("nome", {
    header: "Perfil",
    cell: (c) => (
      <div className="flex items-center gap-3">
        <Avatar className="size-9">
          <AvatarFallback className="tone-dark text-xs text-dark-foreground">{c.getValue().slice(7, 9).toUpperCase()}</AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <p className="truncate font-semibold">{c.getValue()}</p>
          <p className="truncate text-xs text-muted-foreground">{c.row.original.nicho}</p>
        </div>
      </div>
    ),
  }),
  col.accessor("plataformas", {
    header: "Contas",
    meta: { className: "hidden sm:table-cell" },
  }),
  col.accessor("status", {
    header: "Status",
    cell: (c) =>
      c.getValue() === "ativo" ? (
        <Badge className="bg-success text-success-foreground uppercase">ativo</Badge>
      ) : (
        <Badge className="bg-dark text-dark-foreground uppercase">arquivado</Badge>
      ),
  }),
  col.accessor("criadoEm", {
    header: "Criado em",
    cell: (c) => c.getValue().toLocaleDateString("pt-BR"),
    enableGlobalFilter: false,
    meta: { className: "hidden md:table-cell" },
  }),
  col.display({
    id: "acoes",
    header: "",
    cell: () => (
      <Button variant="link" size="sm" className="h-auto p-0 text-xs font-bold uppercase">
        Editar
      </Button>
    ),
  }),
]);

interface EventoFicticio {
  id: string;
  tipo: string;
  quem: string;
}

const evCol = dataTableColumns<EventoFicticio>();
const eventoColumns = evCol.columns([
  evCol.accessor("tipo", { header: "Evento" }),
  evCol.accessor("quem", { header: "Usuário" }),
]);

function eventosAte(n: number): EventoFicticio[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `e${i}`,
    tipo: ["login", "logout", "senha trocada", "login falhou"][i % 4]!,
    quem: `pessoa${i % 3}@exemplo.com`,
  }));
}

function Painel() {
  usePageMeta({ title: "Vitrine", breadcrumbs: [{ label: "Dev" }] });
  const [loading, setLoading] = useState(false);
  const [eventos, setEventos] = useState(12);
  const eventosData = useMemo(() => eventosAte(eventos), [eventos]);

  return (
    <div className="space-y-8">
      <h1 className="sr-only">Vitrine de componentes</h1>
      <div className="grid gap-x-6 gap-y-10 pt-6 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={LayoutGrid}
          label="Perfis ativos"
          value={26}
          tone="dark"
          footer={
            <>
              <strong className="text-success">+3</strong> esta semana
            </>
          }
        />
        <MetricCard icon={Video} label="Contas ativas" value={58} tone="primary" footer="YouTube 31 · TikTok 27" />
        <MetricCard icon={Users} label="Usuários ativos" value={4} tone="success" footer="1 dono · 3 membros" />
        <MetricCard icon={ShieldCheck} label="Eventos (24 h)" value="—" tone="destructive" loading={loading} footer="Carregando…" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => toast.success("Perfil salvo.")}>Toast de sucesso</Button>
        <Button variant="outline" onClick={() => setLoading((v) => !v)}>
          Alternar carregando
        </Button>
      </div>

      <Alert variant="destructive">
        <AlertTitle>Conflito de versão</AlertTitle>
        <AlertDescription>Outra pessoa alterou este perfil. Recarregue para ver a versão atual.</AlertDescription>
      </Alert>

      <HeaderCard
        title="Perfis"
        description="Um nicho por perfil"
        actions={
          <Button variant="secondary" size="sm">
            <Plus aria-hidden="true" />
            Novo perfil
          </Button>
        }
        footer={
          <>
            <Clock aria-hidden="true" /> atualizado há 4 min
          </>
        }
      >
        <DataTable
          label="Perfis"
          columns={columns}
          data={PERFIS}
          loading={loading}
          getRowId={(p) => p.id}
          search={{ placeholder: "Filtrar perfis" }}
          initialSorting={[{ id: "nome", desc: false }]}
        />
      </HeaderCard>

      <HeaderCard title="Eventos de segurança" description="Paginação por cursor" tone="dark">
        <DataTable
          label="Eventos"
          columns={eventoColumns}
          data={eventosData}
          getRowId={(e) => e.id}
          pagination={{ hasMore: eventos < 30, onLoadMore: () => setEventos((n) => n + 10) }}
        />
      </HeaderCard>

      <HeaderCard title="Sem resultados" tone="info">
        <DataTable label="Vazia" columns={eventoColumns} data={[]} />
      </HeaderCard>
    </div>
  );
}

function AcessoExemplo() {
  return (
    <AuthShell
      title="Entrar"
      description="Acesso da agência"
      footer={
        <a href="#" className="font-semibold text-primary">
          Esqueci a senha
        </a>
      }
    >
      <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
        <div className="space-y-1.5">
          <Label htmlFor="sc-email">E-mail</Label>
          <Input id="sc-email" type="email" autoComplete="off" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sc-senha">Senha</Label>
          <Input id="sc-senha" type="password" autoComplete="off" />
        </div>
        <div className="flex items-center gap-2">
          <Switch id="sc-lembrar" />
          <Label htmlFor="sc-lembrar" className="font-normal text-muted-foreground">
            Lembrar de mim
          </Label>
        </div>
        <Button type="submit" className="tone-primary w-full text-xs font-bold tracking-wide uppercase">
          Entrar
        </Button>
      </form>
    </AuthShell>
  );
}

export default function Showcase() {
  const [params] = useSearchParams();
  const [busca, setBusca] = useState("");
  if (params.get("auth")) return <AcessoExemplo />;
  return (
    <AppShell search={{ value: busca, onChange: setBusca }}>
      <Painel />
    </AppShell>
  );
}
