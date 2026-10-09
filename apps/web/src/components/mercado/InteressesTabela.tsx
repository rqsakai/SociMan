/*
 * Tabela de acompanhamentos (spec 026, US4), usada na aba Mercado do perfil e na aba
 * Acompanhamentos do cockpit: produto (link para o detalhe), perfil (ou "todos os perfis" na
 * vitrine), origem, situação, motivo/nota e as ações pausar / reativar / encerrar (AlertDialog),
 * todas de qualquer humano. Encerrar nunca apaga: a linha fica, com histórico.
 */
import type { MercadoInteresse } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { CirclePause, CirclePlay, Square } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatInteiro, invalidarInteresses, origemMercadoLabel, produtoMercadoPath, situacaoInteresseLabel, situacaoInteresseTone } from "@/lib/mercado";
import { formatDateTime } from "@/lib/tz";
import { Estimado } from "./Estimado";

const col = dataTableColumns<MercadoInteresse>();

function motivoTexto(i: MercadoInteresse): string {
  const m = i.motivo as Record<string, unknown>;
  if (i.origem === "ranking" && typeof m.posicao === "number") return `posição ${m.posicao} no ranking`;
  if ((i.origem === "loja" || i.origem === "categoria") && typeof m.vistoEm === "string") return `produto novo, visto em ${m.vistoEm}`;
  if (i.origem === "manual" && typeof m.url === "string") return "link colado";
  if (i.origem === "vitrine") return "vitrine do dono";
  return "";
}

export function InteressesTabela({
  itens,
  loading,
  perfis,
  mostrarPerfil = false,
  empty,
}: {
  itens: MercadoInteresse[] | undefined;
  loading: boolean;
  perfis?: { id: string; name: string }[];
  mostrarPerfil?: boolean;
  empty: React.ReactNode;
}) {
  const nomePerfil = useMemo(() => new Map((perfis ?? []).map((p) => [p.id, p.name])), [perfis]);
  const columns = useMemo(
    () =>
      col.columns([
        col.display({
          id: "produto",
          header: "Produto",
          cell: (c) => {
            const i = c.row.original;
            const p = i.produto;
            return (
              <div className="min-w-0">
                <Link to={produtoMercadoPath(i.mercadoProdutoId)} className="block truncate font-medium hover:underline">
                  {p?.titulo ?? p?.redeProdutoId ?? i.mercadoProdutoId}
                </Link>
                <p className="truncate text-xs text-muted-foreground">
                  {p?.loja?.nome ?? "—"}
                  {p ? ` · vendas no período: ` : ""}
                  {p && <Estimado numero={p.vendasPeriodo} formatar={formatInteiro} className="text-xs" />}
                </p>
              </div>
            );
          },
        }),
        ...(mostrarPerfil
          ? [
              col.accessor((i) => (i.todosOsPerfis ? "Todos os perfis" : (nomePerfil.get(i.perfilId ?? "") ?? "—")), {
                id: "perfil",
                header: "Perfil",
              }),
            ]
          : []),
        col.accessor((i) => origemMercadoLabel[i.origem], {
          id: "origem",
          header: "Origem",
          cell: (c) => (
            <div className="min-w-0">
              <span>{c.getValue()}</span>
              {c.row.original.todosOsPerfis && !mostrarPerfil && <Badge variant="outline" className="ml-1">todos os perfis</Badge>}
              <p className="text-xs text-muted-foreground">{motivoTexto(c.row.original)}</p>
            </div>
          ),
        }),
        col.accessor((i) => situacaoInteresseLabel[i.situacao], {
          id: "situacao",
          header: "Situação",
          cell: (c) => <Badge className={situacaoInteresseTone[c.row.original.situacao]}>{c.getValue()}</Badge>,
        }),
        col.accessor("nota", { header: "Nota", cell: (c) => <span className="line-clamp-2 text-xs">{c.getValue() || "—"}</span> }),
        col.accessor("createdAt", { header: "Desde", enableGlobalFilter: false, cell: (c) => <span className="whitespace-nowrap text-xs">{formatDateTime(c.getValue())}</span> }),
        col.display({ id: "acoes", header: () => <span className="sr-only">Ações</span>, cell: (c) => <Acoes interesse={c.row.original} /> }),
      ]),
    [mostrarPerfil, nomePerfil],
  );
  return <DataTable columns={columns} data={itens ?? []} loading={loading} getRowId={(r) => r.id} label="Acompanhamentos" empty={empty} />;
}

type Acao = "pausado" | "ativo" | "encerrado";

function Acoes({ interesse }: { interesse: MercadoInteresse }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<Acao | null>(null);
  const [error, setError] = useState<unknown>(null);
  if (interesse.situacao === "encerrado") return <span className="text-xs text-muted-foreground">encerrado{interesse.encerradoEm ? ` em ${formatDateTime(interesse.encerradoEm)}` : ""}</span>;

  async function mudar(situacao: Acao, msg: string) {
    setBusy(situacao);
    setError(null);
    try {
      await api.mercado.interesseEditar(interesse.id, { version: interesse.version, situacao });
      toast.success(msg);
      await invalidarInteresses(queryClient);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap justify-end gap-1" role="group" aria-label="Ações do acompanhamento">
        {interesse.situacao === "ativo" ? (
          <Button type="button" size="sm" variant="ghost" disabled={busy !== null} onClick={() => void mudar("pausado", "Acompanhamento pausado: o produto sai da fila deste perfil.")}>
            <CirclePause aria-hidden="true" />
            Pausar
          </Button>
        ) : (
          <Button type="button" size="sm" variant="ghost" disabled={busy !== null} onClick={() => void mudar("ativo", "Acompanhamento reativado: volta à fila hoje.")}>
            <CirclePlay aria-hidden="true" />
            Reativar
          </Button>
        )}
        <ConfirmButton
          label="Encerrar"
          icon={Square}
          size="sm"
          variant="ghost"
          busy={busy === "encerrado"}
          disabled={busy !== null}
          title="Encerrar este acompanhamento?"
          description="O produto e as fotos continuam no lago; só este perfil deixa de pedir coletas por ele. Para voltar, acompanhe de novo."
          onConfirm={() => mudar("encerrado", "Acompanhamento encerrado.")}
        />
      </div>
      {error !== null && <ApiErrorAlert error={error} onReload={() => void invalidarInteresses(queryClient)} />}
    </div>
  );
}
