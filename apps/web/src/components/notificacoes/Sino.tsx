/*
 * Sino de notificações da barra superior (spec 006, T052; R11).
 *
 * <Sino />   botão "Notificações" com a contagem de não lidas; abre a lista (as 30 mais recentes),
 *            "Marcar todas como lidas" e "Avisar também pelo navegador". Clicar numa notificação
 *            marca como lida e navega para o `link` dela.
 * O estado vem de useNotificacoes (polling de 20 s com a aba visível, 60 s em segundo plano).
 */
import { Bell, BellRing, CheckCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { errorText } from "@/lib/perfis";
import { tipoLabel, type NotificacaoTipo } from "@/lib/notificacoes";
import { formatAgo } from "@/lib/tz";
import { cn } from "@/lib/utils";
import { useNotificacoes } from "./useNotificacoes";

const tipoTone: Record<NotificacaoTipo, string> = {
  envio_pronto: "bg-success",
  envio_sem_clipes: "bg-warning",
  envio_falhou: "bg-destructive",
  envio_confirmar_qualidade: "bg-warning",
  envio_momentos: "bg-info",
  openshorts_fora: "bg-destructive",
  hora_de_postar: "bg-primary",
  cota_youtube: "bg-warning",
  canal_erro: "bg-destructive",
  aprovacao_pedida: "bg-warning",
  aprovacao_respondida: "bg-info",
  rascunho_criado: "bg-success",
  envio_publicado: "bg-success",
  envio_rede_falhou: "bg-destructive",
  envio_aguardando_vaga: "bg-warning",
  conexao_precisa_reconectar: "bg-destructive",
};

export function Sino() {
  const navigate = useNavigate();
  const { items, naoLidas, reload, marcarLidas, browser } = useNotificacoes();
  const label = naoLidas > 0 ? `Notificações (${naoLidas} não lidas)` : "Notificações";

  async function open(id: number, link: string, lida: boolean) {
    if (!lida) void marcarLidas({ ids: [id] }).catch(() => undefined);
    void navigate(link);
  }

  async function marcarTodas() {
    try {
      await marcarLidas({ todas: true });
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <DropdownMenu onOpenChange={(isOpen) => isOpen && void reload().catch(() => undefined)}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={label} className="relative">
          {naoLidas > 0 ? <BellRing className="size-5" aria-hidden="true" /> : <Bell className="size-5" aria-hidden="true" />}
          {naoLidas > 0 && (
            <span
              aria-hidden="true"
              className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[0.65rem] font-bold text-white"
            >
              {naoLidas > 99 ? "99+" : naoLidas}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(24rem,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <DropdownMenuLabel className="p-0 text-sm font-semibold">Notificações</DropdownMenuLabel>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            disabled={naoLidas === 0}
            onClick={() => void marcarTodas()}
          >
            <CheckCheck aria-hidden="true" />
            Marcar todas como lidas
          </Button>
        </div>
        <DropdownMenuSeparator className="my-0" />
        <div className="max-h-[min(24rem,60vh)] overflow-y-auto py-1" role="presentation">
          {items.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">Nenhuma notificação.</p>
          ) : (
            items.map((n) => (
              <DropdownMenuItem
                key={n.id}
                onSelect={() => void open(n.id, n.link, n.lida)}
                className={cn("mx-1 items-start gap-3 rounded-md px-2 py-2", !n.lida && "bg-accent/40")}
                aria-label={`${n.titulo}${n.lida ? "" : " (não lida)"}`}
              >
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.lida ? "bg-transparent" : tipoTone[n.tipo])} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className={cn("block text-sm break-words", !n.lida && "font-semibold")}>{n.titulo}</span>
                  {n.corpo && <span className="line-clamp-2 block text-xs text-muted-foreground">{n.corpo}</span>}
                  <span className="mt-0.5 block text-[0.7rem] text-muted-foreground">
                    {tipoLabel[n.tipo]} · <time dateTime={n.createdAt}>{formatAgo(n.createdAt)}</time>
                  </span>
                </span>
              </DropdownMenuItem>
            ))
          )}
        </div>
        {browser.supported && (
          <>
            <DropdownMenuSeparator className="my-0" />
            <DropdownMenuCheckboxItem
              checked={browser.on}
              disabled={browser.permission === "denied"}
              onSelect={(e) => {
                e.preventDefault();
                void browser.toggle();
              }}
              className="m-1"
            >
              <span className="text-sm">
                Avisar também pelo navegador
                <span className="block text-xs text-muted-foreground">
                  {browser.permission === "denied"
                    ? "Bloqueado nas permissões do navegador."
                    : "Só com o SociMan aberto (aba ou app instalado)."}
                </span>
              </span>
            </DropdownMenuCheckboxItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
